"""Unit tests for orchestrator failure-status computation."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from apps.extraction.extractor import (
    _compute_failure_reasons,
    _count_at_path,
    _list_min_items,
)


def test_list_min_items_extracts_paths_with_thresholds():
    schema = {
        "fields": [
            {"kind": "field", "name": "id", "label": "ID", "data_type": "string"},
            {"kind": "list", "name": "lines", "label": "Lines",
             "options": {"min_items": 2},
             "item": {"kind": "object", "fields": [
                {"kind": "field", "name": "qty", "data_type": "int"},
             ]}},
            {"kind": "object", "name": "buyer", "label": "Buyer", "fields": [
                {"kind": "list", "name": "phones", "label": "Phones",
                 "options": {"min_items": 1},
                 "item": {"kind": "object", "fields": [
                    {"kind": "field", "name": "number", "data_type": "phone"},
                 ]}},
            ]},
        ]
    }
    pairs = dict(_list_min_items(schema))
    assert pairs == {"lines": 2, "buyer.phones": 1}


def test_count_at_path_resolves_nested_lists():
    extracted = {"lines": [1, 2, 3], "buyer": {"phones": []}, "id": "x"}
    assert _count_at_path(extracted, "lines") == 3
    assert _count_at_path(extracted, "buyer.phones") == 0
    assert _count_at_path(extracted, "missing") is None
    assert _count_at_path(extracted, "id") is None  # not a list


def _mk_field_result(path, *, error="", canonical=None, original=""):
    fr = Mock()
    fr.path = path
    fr.error = error
    fr.canonical_value = canonical
    fr.original_value = original
    return fr


def _scan_with_results(rows):
    scan = Mock()
    qs = Mock()
    qs.all.return_value = rows
    scan.field_results = qs
    return scan


def test_required_missing_field_is_a_failure_reason():
    field_index = {
        "rechnungs_nummer": {"required": True, "data_type": "string", "options": {}, "label": "..."},
    }
    scan = _scan_with_results([])  # nothing extracted
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema={"fields": []}, field_index=field_index, extracted={},
    )
    assert any("rechnungs_nummer" in r and "missing" in r for r in reasons)


def test_required_field_with_canonical_error_is_a_failure_reason():
    field_index = {
        "iban": {"required": True, "data_type": "iban", "options": {}, "label": "IBAN"},
    }
    scan = _scan_with_results([_mk_field_result("iban", error="invalid IBAN", original="GARBAGE")])
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema={"fields": []}, field_index=field_index, extracted={},
    )
    assert any("iban" in r and "invalid IBAN" in r for r in reasons)


def test_required_field_with_value_passes():
    field_index = {
        "iban": {"required": True, "data_type": "iban", "options": {}, "label": "IBAN"},
    }
    scan = _scan_with_results([_mk_field_result("iban", canonical="DE89370400440532013000", original="DE89 3704 0044 0532 0130 00")])
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema={"fields": []}, field_index=field_index, extracted={"iban": "..."},
    )
    assert reasons == []


def test_optional_field_missing_does_not_fail_scan():
    field_index = {
        "memo": {"required": False, "data_type": "string", "options": {}, "label": "Memo"},
    }
    scan = _scan_with_results([])
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema={"fields": []}, field_index=field_index, extracted={},
    )
    assert reasons == []


def test_list_under_min_items_is_a_failure_reason():
    schema = {"fields": [{"kind": "list", "name": "lines", "label": "Lines",
                          "options": {"min_items": 2},
                          "item": {"kind": "object", "fields": [
                            {"kind": "field", "name": "qty", "data_type": "int", "required": False},
                          ]}}]}
    field_index = {
        "lines[].qty": {"required": False, "data_type": "int", "options": {}, "label": "Qty"},
    }
    scan = _scan_with_results([])
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema=schema, field_index=field_index, extracted={"lines": [{"qty": "1"}]},
    )
    assert any("lines" in r and "1 item" in r for r in reasons)


def test_list_meeting_min_items_passes():
    schema = {"fields": [{"kind": "list", "name": "lines", "label": "Lines",
                          "options": {"min_items": 2},
                          "item": {"kind": "object", "fields": [
                            {"kind": "field", "name": "qty", "data_type": "int", "required": False},
                          ]}}]}
    field_index = {"lines[].qty": {"required": False, "data_type": "int", "options": {}, "label": "Qty"}}
    scan = _scan_with_results([])
    reasons = _compute_failure_reasons(
        scan=scan, scanner_schema=schema, field_index=field_index,
        extracted={"lines": [{"qty": "1"}, {"qty": "2"}]},
    )
    assert reasons == []
