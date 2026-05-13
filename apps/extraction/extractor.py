"""Scan orchestrator.

Walks a Scan through preparing -> extracting -> locating -> terminal, writing
ScanFieldResult rows along the way. The two LLM passes are isolated so a
flaky locate pass cannot fail an otherwise successful extraction.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.canonicalize import canonicalize
from apps.files.services import absolute_page_path, ensure_page_images, page_image_bytes
from apps.scans.models import Scan, ScanFieldResult

from .ollama_client import (
    OllamaClient,
    OllamaError,
    OllamaModelMissing,
    OllamaUnavailable,
    encode_image_b64,
)
from .prompt import build_extraction_prompt, build_locator_prompt

logger = logging.getLogger(__name__)


def _set_status(scan: Scan, status: str, *, pct: int | None = None, message: str = "") -> None:
    fields = ["status"]
    scan.status = status
    if pct is not None:
        scan.progress_pct = pct
        fields.append("progress_pct")
    if message is not None:
        scan.progress_message = message[:200]
        fields.append("progress_message")
    scan.save(update_fields=fields)


def _resolve_model(scan: Scan) -> str:
    return scan.scanner.model_override or settings.DOCER_DEFAULT_MODEL


def _walk_paths(node: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Yield (path, leaf-value-or-marker) for every leaf in the extracted JSON.

    We only recurse into dicts and lists. Leaf paths use list indices like
    `order_lines[0].qty` so they line up with field_index template paths.
    """
    out: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            sub = f"{prefix}.{k}" if prefix else k
            out.extend(_walk_paths(v, sub))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_walk_paths(v, f"{prefix}[{i}]"))
    else:
        out.append((prefix, node))
    return out


def _template_path(real_path: str) -> str:
    """Convert real path with indices into the prompt's template path with [].

    `order_lines[2].qty` -> `order_lines[].qty`
    """
    out = []
    for ch in real_path:
        out.append(ch)
    s = "".join(out)
    import re
    return re.sub(r"\[\d+\]", "[]", s)


def run_extraction(scan: Scan) -> None:
    """Run the full extraction pipeline against `scan`. Updates DB in place."""
    scan.started_at = timezone.now()
    scan.error_message = ""
    scan.save(update_fields=["started_at", "error_message"])
    _set_status(scan, Scan.PREPARING, pct=2, message="rasterizing pages")

    pages = ensure_page_images(scan.file)
    if not pages:
        _set_status(scan, Scan.FAILED, pct=100, message="no pages produced from file")
        scan.error_message = "no pages produced from file"
        scan.finished_at = timezone.now()
        scan.save(update_fields=["error_message", "finished_at"])
        return

    model = _resolve_model(scan)
    client = OllamaClient()
    try:
        client.health()
    except OllamaUnavailable as exc:
        _set_status(scan, Scan.FAILED, pct=100, message=f"ollama unreachable: {exc}")
        scan.error_message = f"ollama unreachable: {exc}"
        scan.finished_at = timezone.now()
        scan.save(update_fields=["error_message", "finished_at"])
        return
    if not client.has_model(model):
        _set_status(scan, Scan.FAILED, pct=100, message=f"model not installed: {model}")
        scan.error_message = f"model not installed: {model}"
        scan.finished_at = timezone.now()
        scan.save(update_fields=["error_message", "finished_at"])
        return

    prompt = build_extraction_prompt(
        scan.scanner.schema_json,
        priming_prompt=scan.scanner.priming_prompt,
        language_hint=scan.scanner.language_hint,
    )

    page_b64 = [encode_image_b64(absolute_page_path(p)) for p in pages]

    _set_status(scan, Scan.EXTRACTING, pct=15, message="thinking")
    extract_attempts: list[dict] = []
    extracted_json: Any = None
    last_error: str = ""

    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.user, "images": page_b64},
    ]

    max_attempts = max(1, int(getattr(settings, "DOCER_EXTRACTION_MAX_ATTEMPTS", 3)))
    for attempt_no in range(1, max_attempts + 1):
        try:
            t0 = time.monotonic()
            result = client.chat(
                model=model,
                messages=messages,
                format=prompt.json_schema,
                options={"temperature": 0.1},
            )
            dt = int((time.monotonic() - t0) * 1000)
        except (OllamaError, OllamaModelMissing) as exc:
            extract_attempts.append({"attempt": attempt_no, "error": repr(exc)})
            last_error = repr(exc)
            continue

        if result.json is None:
            extract_attempts.append({
                "attempt": attempt_no,
                "raw_excerpt": (result.raw or "")[:800],
                "error": "non-json response",
                "duration_ms": dt,
            })
            messages.append({"role": "user",
                             "content": "Your previous reply was not valid JSON. Reply with ONLY a JSON object matching the schema. No prose."})
            continue

        extracted_json = result.json
        extract_attempts.append({
            "attempt": attempt_no,
            "duration_ms": dt,
            "model": result.model,
        })
        break

    if extracted_json is None:
        scan.extracted_json = None
        scan.error_message = last_error or "extraction failed: model did not return JSON"
        _set_status(scan, Scan.FAILED, pct=100, message="extraction failed")
        scan.finished_at = timezone.now()
        scan.pages_processed = len(pages)
        scan.save(update_fields=["extracted_json", "error_message", "finished_at", "pages_processed"])
        return

    _persist_field_results(scan, prompt.field_index, extracted_json, extract_attempts)
    scan.extracted_json = extracted_json
    scan.pages_processed = len(pages)
    scan.save(update_fields=["extracted_json", "pages_processed"])

    _set_status(scan, Scan.LOCATING, pct=70, message="locating fields on page")
    try:
        _run_locate_pass(client, model, scan, page_b64)
    except Exception as exc:
        logger.warning("locate pass errored for scan %s: %r", scan.id, exc)

    # Post-locate decoders refine specific field types using pixel-level
    # local decoding (e.g. cv2.QRCodeDetector for qr_code). The LLM is good
    # at finding things; not so good at decoding codec'd content like QR
    # bytes — so we delegate to purpose-built libraries once we know the
    # region. See apps/extraction/decoders.py.
    try:
        _run_post_locate_decoders(scan, pages)
    except Exception as exc:
        logger.warning("post-locate decode errored for scan %s: %r", scan.id, exc)

    failure_reasons = _compute_failure_reasons(
        scan=scan,
        scanner_schema=scan.scanner.schema_json,
        field_index=prompt.field_index,
        extracted=extracted_json,
    )
    if failure_reasons:
        scan.error_message = "\n".join(failure_reasons)
        _set_status(scan, Scan.FAILED, pct=100, message=failure_reasons[0][:200])
    else:
        _set_status(scan, Scan.COMPLETED, pct=100, message="done")
    scan.finished_at = timezone.now()
    scan.save(update_fields=["finished_at", "error_message"])

    with transaction.atomic():
        acct = scan.account
        type(acct).objects.filter(pk=acct.pk).update(
            documents_scanned_total=acct.documents_scanned_total + 1,
            pages_scanned_total=acct.pages_scanned_total + len(pages),
        )


def _list_min_items(scanner_schema: dict) -> list[tuple[str, int]]:
    """Walk the scanner schema and yield (template_path_to_list, min_items) pairs."""
    out: list[tuple[str, int]] = []

    def walk(node: dict, path: str) -> None:
        kind = node.get("kind") or "field"
        if kind == "field":
            return
        if kind == "object":
            for child in node.get("fields") or []:
                key = _slug_for(child.get("name") or child.get("label") or "field")
                walk(child, f"{path}.{key}" if path else key)
            return
        if kind == "list":
            options = node.get("options") or {}
            try:
                mi = int(options.get("min_items") or 0)
            except (TypeError, ValueError):
                mi = 0
            if mi > 0:
                out.append((path, mi))
            for child in (node.get("item") or {}).get("fields") or []:
                key = _slug_for(child.get("name") or child.get("label") or "field")
                walk(child, f"{path}[].{key}")
            return

    for child in (scanner_schema or {}).get("fields") or []:
        key = _slug_for(child.get("name") or child.get("label") or "field")
        walk(child, key)
    return out


def _slug_for(name: str) -> str:
    """Mirror prompt._slug to keep schema paths and field_index keys in sync."""
    from .prompt import _slug
    return _slug(name)


def _count_at_path(extracted: Any, dotted_path: str) -> int | None:
    """Resolve a dotted path with a trailing list and return its length, or None if missing."""
    cursor: Any = extracted
    for part in dotted_path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
        if cursor is None:
            return None
    if isinstance(cursor, list):
        return len(cursor)
    return None


def _compute_failure_reasons(
    *,
    scan: Scan,
    scanner_schema: dict,
    field_index: dict[str, dict],
    extracted: Any,
) -> list[str]:
    """Return a list of human-readable reasons the scan should be marked FAILED.

    A required leaf is "failed" if it is missing from the extraction or if its
    canonicalization errored. Lists with min_items > 0 fail when the extracted
    array is shorter than the threshold. All field-level data is preserved in
    ScanFieldResult regardless, so partial output is still visible to the user.
    """
    reasons: list[str] = []

    field_results_by_path = {fr.path: fr for fr in scan.field_results.all()}

    for tmpl_path, meta in field_index.items():
        if not meta.get("required"):
            continue
        if "[]" in tmpl_path:
            continue  # list-item required-ness is governed by min_items on the list
        fr = field_results_by_path.get(tmpl_path)
        if fr is None:
            reasons.append(f"required field '{tmpl_path}' missing from extraction")
            continue
        if fr.error:
            reasons.append(f"required field '{tmpl_path}' had error: {fr.error}")
            continue
        if (fr.canonical_value in (None, "", [])) and not fr.original_value:
            reasons.append(f"required field '{tmpl_path}' is empty")

    for list_path, mi in _list_min_items(scanner_schema):
        actual = _count_at_path(extracted, list_path)
        if actual is None:
            reasons.append(f"required list '{list_path}' missing from extraction (need at least {mi})")
        elif actual < mi:
            reasons.append(f"list '{list_path}' has {actual} item(s); at least {mi} required")

    return reasons


def _persist_field_results(
    scan: Scan,
    field_index: dict[str, dict],
    extracted: Any,
    extract_attempts: list[dict],
) -> None:
    """Walk the extracted JSON, canonicalize each leaf, and write ScanFieldResult rows."""
    leaves = _walk_paths(extracted)
    seen_paths: set[str] = set()

    for real_path, raw_value in leaves:
        tmpl_path = _template_path(real_path)
        meta = field_index.get(tmpl_path)
        if meta is None:
            continue
        seen_paths.add(real_path)

        data_type = meta.get("data_type", "string")
        options = meta.get("options") or {}
        language = meta.get("language") or scan.scanner.language_hint or None

        original_str = "" if raw_value is None else str(raw_value)
        cr = canonicalize(data_type, original_str, language=language, options=options)
        attempts_blob = list(extract_attempts) if extract_attempts else []

        ScanFieldResult.objects.create(
            scan=scan,
            path=real_path,
            data_type=data_type,
            original_value=cr.original or "",
            canonical_value=cr.canonical,
            confidence=None,
            page_index=None,
            bbox=None,
            attempts=attempts_blob,
            error="; ".join(cr.errors) if cr.errors else "",
        )

    for tmpl_path, meta in field_index.items():
        if "[]" in tmpl_path:
            continue
        if tmpl_path in seen_paths:
            continue
        if not meta.get("required"):
            continue
        ScanFieldResult.objects.create(
            scan=scan,
            path=tmpl_path,
            data_type=meta.get("data_type", "string"),
            original_value="",
            canonical_value=None,
            attempts=list(extract_attempts) if extract_attempts else [],
            error="required field missing from extraction",
        )


def _run_locate_pass(client: OllamaClient, model: str, scan: Scan, page_b64: list[str]) -> None:
    """For each ScanFieldResult that has an original_value, ask the model where it is on each page."""
    field_results = list(scan.field_results.exclude(original_value="").only(
        "id", "path", "original_value", "data_type"
    ))
    if not field_results or not page_b64:
        return

    # Progress slice 70%→95% gets divided across the per-field work so the bar
    # actually moves during the slow locate pass (especially noticeable with
    # cloud-hosted models where each call is 5-20s).
    total = len(field_results)
    for i, fr in enumerate(field_results):
        pct = 70 + int(25 * (i / total)) if total else 70
        _set_status(
            scan,
            Scan.LOCATING,
            pct=pct,
            message=f"locating field {i + 1}/{total}: {fr.path}",
        )
        sys_prompt, user_prompt = build_locator_prompt(
            field_path=fr.path,
            field_label=fr.path.split(".")[-1],
            original_value=fr.original_value,
            page_index=0,
        )
        best_bbox = None
        best_page = None
        for idx, b64 in enumerate(page_b64):
            try:
                result = client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt, "images": [b64]},
                    ],
                    format="json",
                    options={"temperature": 0.0},
                )
            except OllamaError as exc:
                fr.attempts = (fr.attempts or []) + [{"locate_error": repr(exc), "page": idx}]
                continue

            data = result.json or {}
            bb = data.get("bbox")
            if isinstance(bb, list) and len(bb) == 4 and all(isinstance(x, (int, float)) for x in bb):
                best_bbox = bb
                best_page = idx
                break

        if best_bbox is not None:
            fr.bbox = best_bbox
            fr.page_index = best_page
            fr.save(update_fields=["bbox", "page_index"])


def _run_post_locate_decoders(scan: Scan, pages) -> None:
    """For field results whose data_type has a registered post-locate decoder
    (e.g. qr_code), crop the page image at the located bbox and run the
    decoder. Overwrite original_value with the decoded text and re-canonicalize.

    Decoders work on raw page PNG bytes — they have no Ollama dependency
    and run synchronously in this process. See apps/extraction/decoders.py.
    """
    from .decoders import get_decoder

    pages_by_idx = {p.index: p for p in pages}
    field_results = list(
        scan.field_results.exclude(data_type="").only(
            "id", "path", "data_type", "original_value", "bbox", "page_index", "error"
        )
    )
    decodable = [
        fr for fr in field_results
        if get_decoder(fr.data_type) is not None
    ]
    if not decodable:
        return

    total = len(decodable)
    for i, fr in enumerate(decodable):
        decoder = get_decoder(fr.data_type)
        # Progress slice 95%→99% so the user sees movement during decode too.
        _set_status(
            scan,
            Scan.LOCATING,
            pct=95 + int(4 * (i / total)),
            message=f"decoding {fr.data_type} field {i + 1}/{total}: {fr.path}",
        )
        page = pages_by_idx.get(fr.page_index) if fr.page_index is not None else None
        if page is None:
            continue
        try:
            img_bytes = page_image_bytes(page)
        except Exception as exc:
            logger.warning("could not read page bytes for fr %s: %r", fr.id, exc)
            continue
        bbox = tuple(fr.bbox) if fr.bbox and len(fr.bbox) == 4 else None
        try:
            decoded = decoder(img_bytes, bbox)
        except Exception as exc:
            logger.warning("decoder failed for fr %s (%s): %r", fr.id, fr.data_type, exc)
            fr.error = (fr.error or "") + f" [decoder error: {exc!r}]"
            fr.save(update_fields=["error"])
            continue
        if not decoded:
            # Decoder didn't recognize anything. Leave LLM's marker as a hint
            # that something was visually present, plus a soft error.
            fr.error = (fr.error or "") + " [decoder found nothing in bbox]"
            fr.save(update_fields=["error"])
            continue
        fr.original_value = decoded
        result = canonicalize(fr.data_type, decoded, language=scan.scanner.language_hint or None)
        fr.canonical_value = result.canonical
        fr.error = (fr.error or "") + (f" [canon: {'; '.join(result.errors)}]" if result.errors else "")
        fr.save(update_fields=["original_value", "canonical_value", "error"])
