from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .types import (
    booleans,
    country,
    currency,
    dates,
    email,
    enums,
    iban,
    names,
    numbers,
    phone,
    quantity,
    strings,
    vat,
)


@dataclass
class CanonicalResult:
    original: str
    canonical: Any | None
    errors: list[str] = field(default_factory=list)


Handler = Callable[[Any, str | None, dict | None], tuple[Any | None, list[str]]]


_REGISTRY: dict[str, tuple[Handler, str, dict]] = {
    "string": (strings.canon_string, "String", {}),
    "name": (names.canon_name, "Name", {}),
    "street": (names.canon_street, "Street", {}),
    "city": (names.canon_city, "City", {}),
    "zip": (strings.canon_zip, "ZIP / Postal code", {}),
    "country": (country.canon_country, "Country (ISO-3166 alpha-2)", {}),
    "email": (email.canon_email, "Email", {}),
    "phone": (
        phone.canon_phone,
        "Phone (E.164)",
        {"default_region": {"type": "string", "description": "Fallback region, e.g. 'DE'"}},
    ),
    "iban": (iban.canon_iban, "IBAN", {}),
    "vat_id": (vat.canon_vat, "VAT ID", {}),
    "uid": (vat.canon_vat, "VAT ID (alias 'uid')", {}),
    "int": (numbers.canon_int, "Integer", {}),
    "float": (numbers.canon_float, "Float", {}),
    "decimal": (
        numbers.canon_decimal,
        "Decimal (string)",
        {"precision": {"type": "int", "description": "Decimal places"}},
    ),
    "currency_amount": (
        currency.canon_currency_amount,
        "Currency amount",
        {"default_currency": {"type": "string", "description": "ISO-4217 fallback"}},
    ),
    "quantity": (quantity.canon_quantity, "Quantity (value+unit)", {}),
    "date": (dates.canon_date, "Date (YYYY-MM-DD)", {}),
    "datetime": (dates.canon_datetime, "Datetime (ISO-8601)", {}),
    "boolean": (booleans.canon_boolean, "Boolean", {}),
    "enum": (
        enums.canon_enum,
        "Enum (closed)",
        {"values": {"type": "list", "description": "[{id,label}, ...]"}},
    ),
    "open_enum": (
        enums.canon_open_enum,
        "Enum (open)",
        {"values": {"type": "list", "description": "[{id,label}, ...]"}},
    ),
}


def canonicalize(
    data_type: str,
    raw: Any,
    *,
    language: str | None = None,
    options: dict | None = None,
) -> CanonicalResult:
    original = "" if raw is None else str(raw)

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return CanonicalResult(original=original, canonical=None, errors=[])

    entry = _REGISTRY.get(data_type)
    if entry is None:
        return CanonicalResult(
            original=original,
            canonical=None,
            errors=[f"unknown data_type: {data_type!r}"],
        )

    handler = entry[0]
    try:
        canonical, errors = handler(raw, language, options or {})
    except Exception as exc:  # canonicalize never raises
        return CanonicalResult(original=original, canonical=None, errors=[str(exc)])

    return CanonicalResult(original=original, canonical=canonical, errors=list(errors))


def list_data_types() -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for key, (_, label, schema) in _REGISTRY.items():
        if label in seen:
            continue
        seen.add(label)
        out.append({"key": key, "label": label, "options_schema": schema})
    return out
