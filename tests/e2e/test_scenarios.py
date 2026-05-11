"""End-to-end smoke / regression tests driven by tests/data/scenarios.json.

Each scenario:
  1. Creates a fresh user + personal account
  2. Creates a scanner with the configured fields
  3. Uploads the bundled PDF
  4. Runs the scan synchronously (Huey immediate mode) via the same task
     code that runs in production
  5. Asserts canonical extracted values match the scenario's `expected` map

Adding a regression test requires no code change: drop a PDF in tests/data and
add a scenario row in tests/data/scenarios.json.

This test HARD-FAILS if Ollama or the configured model are unreachable. Per the
spec, the e2e is the contract that proves the system works.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.accounts.services import create_personal_account
from apps.files.services import ingest_upload
from apps.scanners.models import Scanner
from apps.scans.models import Scan, ScanFieldResult
from apps.scans.tasks import run_scan as run_scan_task

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"


def _load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))


def _scenario_id(scenario: dict) -> str:
    return scenario.get("name") or scenario["pdf"]


def _check_ollama_or_fail() -> None:
    host = settings.OLLAMA_HOST
    model = settings.DOCER_DEFAULT_MODEL
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{host}/api/tags")
            r.raise_for_status()
            tags = {m.get("name") for m in r.json().get("models", [])}
    except Exception as e:
        pytest.fail(
            f"E2E requires a reachable Ollama at {host} (got {e!r}). "
            f"Per spec, this hard-fails rather than skipping."
        )
    if model not in tags:
        pytest.fail(
            f"E2E requires the configured model '{model}' to be installed in Ollama. "
            f"Available: {sorted(tags)}"
        )


def _build_scanner(account, extractor: dict) -> Scanner:
    """Translate scenarios.json's flat 'fields' list into our schema_json format."""
    out_fields = []
    for f in extractor.get("fields", []):
        out_fields.append({
            "kind": "field",
            "name": f["name"],
            "label": f.get("label", f["name"]),
            "data_type": f.get("data_type", "string"),
            "required": bool(f.get("required", False)),
            "description": f.get("description", ""),
            "options": f.get("options", {}),
        })
    schema = {"fields": out_fields}
    scanner = Scanner.objects.create(
        account=account,
        name=extractor["name"],
        slug=Scanner(account=account).make_unique_slug(extractor["name"]),
        description=extractor.get("description", ""),
        priming_prompt=extractor.get("priming_prompt", ""),
        language_hint=extractor.get("language_hint", ""),
        model_override=extractor.get("model_override", ""),
        schema_json=schema,
    )
    return scanner


def _flatten(node, prefix=""):
    """Flatten a nested extracted_json into dotted paths."""
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten(v, f"{prefix}{k}." if not prefix else f"{prefix}{k}."))
    else:
        out[prefix.rstrip(".")] = node
    return out


def _value_for_assertion(field_result: ScanFieldResult):
    """Pick a single comparable value from a field result for assertion against scenario.expected."""
    cv = field_result.canonical_value
    if cv is None:
        return field_result.original_value
    if isinstance(cv, dict) and "display" in cv:
        return cv["display"]
    return cv


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("scenario", _load_scenarios(), ids=_scenario_id)
def test_e2e_scenario(scenario, settings):
    _check_ollama_or_fail()

    pdf_path = DATA_DIR / scenario["pdf"]
    assert pdf_path.exists(), f"Scenario PDF missing: {pdf_path}"

    user = User.objects.create_user(
        username=f"e2e-{scenario['pdf']}",
        email=f"e2e+{int(time.time()*1000)}@example.com",
        password="x" * 12,
    )
    account = create_personal_account(user, base_name=f"E2E {scenario.get('name','scan')}")

    scanner = _build_scanner(account, scenario["extractor"])

    pdf_bytes = pdf_path.read_bytes()
    uploaded = SimpleUploadedFile(scenario["pdf"], pdf_bytes, content_type="application/pdf")
    stored = ingest_upload(account, uploaded, original_name=scenario["pdf"], mime="application/pdf")

    scan = Scan.objects.create(account=account, scanner=scanner, file=stored)
    # In tests we bypass the Huey queue and call the task body in-process so
    # the scan finishes before we assert. Production code path still goes
    # through the @db_task wrapper.
    if hasattr(run_scan_task, "call_local"):
        run_scan_task.call_local(scan.id)
    else:
        run_scan_task(scan.id)

    scan.refresh_from_db()
    assert scan.status == Scan.COMPLETED, (
        f"Scan ended in status={scan.status}\n"
        f"error_message={scan.error_message}\n"
        f"field_results={[(fr.path, fr.original_value, fr.canonical_value, fr.error) for fr in scan.field_results.all()]}"
    )

    by_path = {fr.path: fr for fr in scan.field_results.all()}

    expected = scenario.get("expected", {})
    for key, exp_value in expected.items():
        # scenarios.json uses field name as key; we look it up by slug or label.
        field_results = list(scan.field_results.filter(path__iexact=key))
        if not field_results:
            slug = key.lower().replace(" ", "_").replace("-", "_")
            field_results = list(scan.field_results.filter(path__iexact=slug))
        if not field_results:
            for fr in scan.field_results.all():
                if fr.path.lower() == key.lower() or fr.path.replace("_", " ").lower() == key.lower():
                    field_results = [fr]
                    break
        assert field_results, f"No ScanFieldResult for expected key {key!r}. Available: {list(by_path)}"

        actual = _value_for_assertion(field_results[0])
        if isinstance(actual, str):
            assert exp_value.strip().lower() in actual.strip().lower() or \
                   actual.strip().lower() in exp_value.strip().lower() or \
                   actual.strip() == exp_value.strip(), (
                f"Field {key!r}: expected ~{exp_value!r}, got {actual!r}"
            )
        else:
            assert actual == exp_value, f"Field {key!r}: expected {exp_value!r}, got {actual!r}"
