"""Tests for document-wide context hints in field-type prompts.

These hints steer the vision model to consult the whole document for fields
whose interpretation depends on locale (currency, country, dates, numbers,
addresses, phone numbers, quantities, VAT IDs).
"""
from __future__ import annotations

import pytest

from apps.extraction.prompt import build_extraction_prompt


def _field(name: str, data_type: str, **extra) -> dict:
    return {
        "kind": "field",
        "name": name,
        "label": name.replace("_", " ").title(),
        "data_type": data_type,
        "required": False,
        "description": "",
        "options": extra.get("options", {}),
    }


def _props(prompt) -> dict:
    return prompt.json_schema["properties"]


def test_system_preamble_tells_model_to_read_whole_document():
    p = build_extraction_prompt({"fields": []})
    assert "WHOLE DOCUMENT" in p.system
    # Mentions the kinds of context that matter
    sys_lower = p.system.lower()
    for kw in ("country", "language", "currency", "letterhead"):
        assert kw in sys_lower, f"system preamble should mention {kw!r}"


@pytest.mark.parametrize(
    "data_type, must_contain",
    [
        ("currency_amount", ["WHOLE document", "header", "totals", "minor units"]),
        ("country", ["letterhead", "IBAN", "VAT-ID", "postal-code"]),
        ("phone", ["country code", "letterhead", "IBAN"]),
        ("vat_id", ["country prefix", "letterhead"]),
        ("uid", ["country prefix", "letterhead"]),
        ("date", ["ambiguous", "language"]),
        ("datetime", ["ambiguous", "language"]),
        ("int", ["thousand separators", "language"]),
        ("float", ["thousand separators", "language"]),
        ("decimal", ["thousand separators", "language"]),
        ("quantity", ["unit", "column header"]),
        ("street", ["letterhead", "country"]),
        ("city", ["letterhead", "country"]),
        ("zip", ["letterhead", "country"]),
    ],
)
def test_field_description_includes_context_hint(data_type, must_contain):
    schema = {"fields": [_field("x", data_type)]}
    p = build_extraction_prompt(schema)
    desc = _props(p)["x"]["description"]
    for needle in must_contain:
        assert needle in desc, (
            f"data_type={data_type!r} description should mention {needle!r}; got:\n{desc}"
        )


@pytest.mark.parametrize(
    "data_type",
    ["string", "name", "email", "iban", "boolean"],
)
def test_field_description_unchanged_for_non_context_types(data_type):
    """Types that don't benefit from cross-context shouldn't get the extra noise."""
    schema = {"fields": [_field("x", data_type)]}
    p = build_extraction_prompt(schema)
    desc = _props(p)["x"]["description"]
    # None of the locale-context phrases we add elsewhere should appear here.
    assert "letterhead" not in desc
    assert "WHOLE document" not in desc
