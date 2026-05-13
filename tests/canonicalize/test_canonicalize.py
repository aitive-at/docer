from __future__ import annotations

import pytest

from apps.canonicalize import CanonicalResult, canonicalize, list_data_types


def test_list_data_types_contains_core_types():
    keys = {entry["key"] for entry in list_data_types()}
    for k in (
        "string", "name", "street", "city", "zip", "country",
        "email", "phone", "iban", "vat_id",
        "int", "float", "decimal", "currency_amount", "quantity",
        "date", "datetime", "boolean", "enum", "open_enum",
        "qr_code",
    ):
        assert k in keys


def test_qr_code_preserves_payload_verbatim():
    """QR payloads often have meaningful structure (newlines in vCards, query
    strings in URLs). Canonicalization must not collapse them."""
    r = canonicalize("qr_code", "BEGIN:VCARD\nVERSION:3.0\nFN:Alice\nEND:VCARD")
    assert r.canonical == "BEGIN:VCARD\nVERSION:3.0\nFN:Alice\nEND:VCARD"
    assert r.errors == []


def test_unknown_type_returns_error():
    r = canonicalize("not_a_type", "anything")
    assert r.canonical is None
    assert r.errors


def test_empty_input_no_value_no_errors():
    for raw in (None, "", "   "):
        r = canonicalize("string", raw)
        assert r.canonical is None
        assert r.errors == []


def test_canonicalize_never_raises_on_garbage():
    r = canonicalize("int", "complete-garbage")
    assert isinstance(r, CanonicalResult)
    assert r.canonical is None
    assert r.errors


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  hello   world  ", "hello world"),
        ("multi\nline\ttext", "multi line text"),
        ("plain", "plain"),
    ],
)
def test_string(raw, expected):
    r = canonicalize("string", raw)
    assert r.canonical == expected
    assert r.errors == []


@pytest.mark.parametrize(
    "raw,display,comparable",
    [
        ("maria müller", "Maria Müller", "maria muller"),
        ("HANS-PETER schmidt", "Hans-Peter Schmidt", "hans-peter schmidt"),
        ("john o'brien", "John O'brien", "john o'brien"),
        ("ludwig van beethoven", "Ludwig van Beethoven", "ludwig van beethoven"),
    ],
)
def test_name(raw, display, comparable):
    r = canonicalize("name", raw)
    assert r.canonical == {"display": display, "comparable": comparable}


def test_street_keeps_numbers():
    r = canonicalize("street", "  hauptstraße   12a  ")
    assert r.canonical["display"] == "Hauptstraße 12a"
    assert r.canonical["comparable"] == "hauptstrasse 12a"


def test_city():
    r = canonicalize("city", "münchen")
    assert r.canonical == {"display": "München", "comparable": "munchen"}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  1010 ", "1010"),
        ("sw1a 1aa", "SW1A1AA"),
        ("a-1010", "A-1010"),
    ],
)
def test_zip(raw, expected):
    r = canonicalize("zip", raw)
    assert r.canonical == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("DE", "DE"),
        ("de", "DE"),
        ("Deutschland", "DE"),
        ("Germany", "DE"),
        ("Österreich", "AT"),
        ("austria", "AT"),
        ("USA", "US"),
        ("United Kingdom", "GB"),
        ("uk", "GB"),
    ],
)
def test_country_known(raw, expected):
    r = canonicalize("country", raw)
    assert r.canonical == expected
    assert r.errors == []


def test_country_unknown():
    r = canonicalize("country", "Atlantis")
    assert r.canonical is None
    assert r.errors


def test_email_valid():
    r = canonicalize("email", "Foo.Bar+tag@Example.COM")
    assert r.canonical == "foo.bar+tag@example.com"
    assert r.errors == []


def test_email_invalid():
    r = canonicalize("email", "not-an-email")
    assert r.canonical is None
    assert r.errors


def test_phone_with_language_hint():
    r = canonicalize("phone", "030 12345678", language="de")
    assert r.canonical == "+493012345678"


def test_phone_with_default_region_option():
    r = canonicalize("phone", "030 12345678", options={"default_region": "DE"})
    assert r.canonical == "+493012345678"


def test_phone_already_e164():
    r = canonicalize("phone", "+493012345678")
    assert r.canonical == "+493012345678"


def test_phone_invalid():
    r = canonicalize("phone", "abc")
    assert r.canonical is None
    assert r.errors


def test_iban_valid_compact():
    r = canonicalize("iban", "DE89 3704 0044 0532 0130 00")
    assert r.canonical == "DE89370400440532013000"


def test_iban_invalid():
    r = canonicalize("iban", "DE00 0000 0000 0000 0000 00")
    assert r.canonical is None
    assert r.errors


def test_vat_valid():
    r = canonicalize("vat_id", "ATU13585627")
    assert r.canonical == "ATU13585627"


def test_vat_alias_uid():
    r = canonicalize("uid", "ATU13585627")
    assert r.canonical == "ATU13585627"


def test_vat_invalid():
    r = canonicalize("vat_id", "AT0000000")
    assert r.canonical is None
    assert r.errors


@pytest.mark.parametrize(
    "raw,language,expected",
    [
        ("1234", None, 1234),
        ("1.234", "de", 1234),
        ("1,234", "en", 1234),
        ("1 234", "fr", 1234),
        (-7, None, -7),
        ("EUR 42", None, 42),
    ],
)
def test_int(raw, language, expected):
    r = canonicalize("int", raw, language=language)
    assert r.canonical == expected
    assert r.errors == []


def test_int_rejects_non_integral():
    r = canonicalize("int", "1.5")
    assert r.canonical is None
    assert r.errors


@pytest.mark.parametrize(
    "raw,language,expected",
    [
        ("1.234,56", "de", 1234.56),
        ("1,234.56", "en", 1234.56),
        ("1234.56", None, 1234.56),
        ("0,5", "de", 0.5),
    ],
)
def test_float(raw, language, expected):
    r = canonicalize("float", raw, language=language)
    assert r.canonical == pytest.approx(expected)


def test_float_invalid():
    r = canonicalize("float", "not a number")
    assert r.canonical is None
    assert r.errors


def test_decimal_string_with_precision():
    r = canonicalize("decimal", "1.234,5", language="de", options={"precision": 2})
    assert r.canonical == "1234.50"


def test_decimal_no_precision():
    r = canonicalize("decimal", "1.234,567", language="de")
    assert r.canonical == "1234.567"


@pytest.mark.parametrize(
    "raw,language,minor,currency,scale",
    [
        ("EUR 1.234,56", "de", 123456, "EUR", 2),
        ("1234,56 €", "de", 123456, "EUR", 2),
        ("$1,234.56", "en", 123456, "USD", 2),
        ("1234.56 USD", "en", 123456, "USD", 2),
        ("£10", "en", 1000, "GBP", 2),
    ],
)
def test_currency_amount(raw, language, minor, currency, scale):
    r = canonicalize("currency_amount", raw, language=language)
    assert r.canonical == {"amount": minor, "currency": currency, "scale": scale}
    assert r.errors == []


def test_currency_amount_jpy_zero_decimals():
    r = canonicalize("currency_amount", "¥1234", language="en")
    assert r.canonical == {"amount": 1234, "currency": "JPY", "scale": 0}
    assert r.errors == []


def test_currency_amount_no_symbol_uses_default():
    r = canonicalize(
        "currency_amount",
        "1234.56",
        language="en",
        options={"default_currency": "USD"},
    )
    assert r.canonical == {"amount": 123456, "currency": "USD", "scale": 2}


def test_currency_amount_ambiguous_no_default():
    r = canonicalize("currency_amount", "1234.56", language="en")
    assert r.canonical["amount"] == 123456
    assert r.canonical["currency"] is None
    assert r.canonical["scale"] == 2
    assert r.errors


@pytest.mark.parametrize(
    "raw,language,value,unit",
    [
        ("12 pcs", None, "12", "pcs"),
        ("1.5 kg", None, "1.5", "kg"),
        ("3 stk", "de", "3", "stk"),
        ("1.234,5 m", "de", "1234.5", "m"),
    ],
)
def test_quantity(raw, language, value, unit):
    r = canonicalize("quantity", raw, language=language)
    assert r.canonical == {"value": value, "unit": unit}


@pytest.mark.parametrize(
    "raw,language,expected",
    [
        ("2024-01-15", None, "2024-01-15"),
        ("15.01.2024", "de", "2024-01-15"),
        ("01/15/2024", "en", "2024-01-15"),
        ("15/01/2024", "fr", "2024-01-15"),
        ("Jan 15, 2024", "en", "2024-01-15"),
        # Multilingual month names (the original bug-report case + others).
        ("8. Mai 2026", "de", "2026-05-08"),
        ("8. Mai 2026", None, "2026-05-08"),  # auto-detect German
        ("15. März 2024", "de", "2024-03-15"),
        ("1er janvier 2024", "fr", "2024-01-01"),
        ("8 de mayo de 2026", "es", "2026-05-08"),
        ("15 marzo 2024", "it", "2024-03-15"),
        # Ordinal English
        ("January 1st, 2024", None, "2024-01-01"),
        # Ambiguous numeric — language hint disambiguates DMY vs MDY.
        ("03/04/2024", "de", "2024-04-03"),
        ("03/04/2024", "en", "2024-03-04"),
    ],
)
def test_date(raw, language, expected):
    r = canonicalize("date", raw, language=language)
    assert r.canonical == expected, f"input={raw!r} lang={language!r}"
    assert r.errors == []


def test_date_invalid():
    r = canonicalize("date", "not-a-date")
    assert r.canonical is None
    assert r.errors


def test_datetime_iso():
    r = canonicalize("datetime", "2024-01-15T10:30:00")
    assert r.canonical == "2024-01-15T10:30:00"


def test_datetime_german():
    r = canonicalize("datetime", "15.01.2024 10:30", language="de")
    assert r.canonical.startswith("2024-01-15T10:30")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("yes", True), ("Yes", True), ("true", True), ("1", True),
        ("ja", True), ("oui", True), ("si", True),
        ("no", False), ("false", False), ("0", False),
        ("nein", False), ("non", False),
        (True, True), (False, False),
    ],
)
def test_boolean(raw, expected):
    r = canonicalize("boolean", raw)
    assert r.canonical is expected


def test_boolean_invalid():
    r = canonicalize("boolean", "maybe")
    assert r.canonical is None
    assert r.errors


_ENUM_VALUES = {
    "values": [
        {"id": "draft", "label": "Draft"},
        {"id": "sent", "label": "Sent"},
        {"id": "paid", "label": "Paid"},
    ]
}


def test_enum_match_by_id():
    r = canonicalize("enum", "sent", options=_ENUM_VALUES)
    assert r.canonical == "sent"


def test_enum_match_by_label_case_insensitive():
    r = canonicalize("enum", "SENT", options=_ENUM_VALUES)
    assert r.canonical == "sent"


def test_enum_match_by_label_exact():
    r = canonicalize("enum", "Paid", options=_ENUM_VALUES)
    assert r.canonical == "paid"


def test_enum_no_match():
    r = canonicalize("enum", "rejected", options=_ENUM_VALUES)
    assert r.canonical is None
    assert r.errors


def test_enum_missing_options():
    r = canonicalize("enum", "sent")
    assert r.canonical is None
    assert r.errors


def test_open_enum_matches_existing():
    r = canonicalize("open_enum", "Draft", options=_ENUM_VALUES)
    assert r.canonical == "draft"
    assert r.errors == []


def test_open_enum_proposes_new():
    r = canonicalize("open_enum", "  Cancelled  ", options=_ENUM_VALUES)
    assert r.canonical == {"id": None, "proposed_label": "Cancelled"}
    assert r.errors == []


def test_open_enum_without_options_proposes():
    r = canonicalize("open_enum", "anything")
    assert r.canonical == {"id": None, "proposed_label": "anything"}


def test_canonical_result_preserves_original():
    r = canonicalize("int", "  1.234  ", language="de")
    assert r.original == "  1.234  "
    assert r.canonical == 1234
