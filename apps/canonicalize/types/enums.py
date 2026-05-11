from __future__ import annotations

from typing import Any

from ._helpers import collapse_ws


def _match(raw: Any, options: dict) -> str | None:
    values = options.get("values") or []
    if not isinstance(values, (list, tuple)):
        return None
    text = collapse_ws(str(raw))
    if not text:
        return None
    text_lower = text.lower()
    for entry in values:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id")) == text:
            return str(entry["id"])
    for entry in values:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        if label is None:
            continue
        if str(label) == text:
            return str(entry["id"])
    for entry in values:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        if label is None:
            continue
        if str(label).lower() == text_lower:
            return str(entry["id"])
        if str(entry.get("id", "")).lower() == text_lower:
            return str(entry["id"])
    return None


def canon_enum(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    if not options or "values" not in options:
        return None, ["enum requires options.values"]
    matched = _match(raw, options)
    if matched is None:
        return None, [f"no enum match for {str(raw)!r}"]
    return matched, []


def canon_open_enum(raw: Any, language: str | None, options: dict) -> tuple[Any, list[str]]:
    options = options or {}
    matched = _match(raw, options)
    if matched is not None:
        return matched, []
    proposed = collapse_ws(str(raw))
    return {"id": None, "proposed_label": proposed}, []
