from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from . import numbers as _num

_SYMBOL_TO_CODE: dict[str, str] = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "¥": "JPY",
    "₣": "CHF",
    "CHF": "CHF",
    "Fr.": "CHF",
    "kr": "SEK",
    "zł": "PLN",
    "Kč": "CZK",
}

_CODE_RE = re.compile(r"\b([A-Z]{3})\b")
_NUMBER_RE = re.compile(r"[-+]?[\d][\d  .,']*")


def _detect_currency(text: str, options: dict) -> tuple[str | None, str]:
    stripped = text.strip()

    code_match = _CODE_RE.search(stripped.upper())
    if code_match:
        code = code_match.group(1)
        cleaned = re.sub(rf"\b{code}\b", "", stripped, count=1, flags=re.IGNORECASE).strip()
        return code, cleaned

    for sym, code in sorted(_SYMBOL_TO_CODE.items(), key=lambda kv: -len(kv[0])):
        if sym in stripped:
            cleaned = stripped.replace(sym, "", 1).strip()
            return code, cleaned

    default = options.get("default_currency")
    if default:
        return str(default).upper(), stripped
    return None, stripped


def _currency_scale(code: str | None) -> int:
    """Return the number of decimal places (minor-unit power-of-ten) for a currency.

    Falls back to 2 when the currency is unknown or Babel can't resolve it.
    JPY -> 0, BHD -> 3, etc.
    """
    if not code:
        return 2
    try:
        from babel.numbers import get_currency_precision

        return int(get_currency_precision(code))
    except Exception:
        return 2


def canon_currency_amount(
    raw: Any, language: str | None, options: dict
) -> tuple[dict | None, list[str]]:
    """Canonicalize "1.234,56 EUR" -> {"amount": 123456, "currency": "EUR", "scale": 2}.

    The canonical `amount` is an integer in the currency's minor units (cents
    for EUR/USD, yen for JPY, fils for BHD). `scale` is `log10(major/minor)`.
    The original printed string is preserved separately on the ScanFieldResult
    row so display code can show "EUR 1.234,56" untouched. Downstream systems
    that compare amounts use `amount` directly, avoiding decimal-string drift.
    """
    text = str(raw).strip()
    if not text:
        return None, ["empty currency amount"]

    currency, remainder = _detect_currency(text, options)

    match = _NUMBER_RE.search(remainder)
    if not match:
        return None, [f"no numeric portion: {raw!r}"]
    number_text = match.group(0)

    norm = _num._normalize_number_string(number_text, language)
    try:
        dec = Decimal(norm)
    except (InvalidOperation, ValueError):
        return None, [f"cannot parse amount: {raw!r}"]

    scale = _currency_scale(currency)
    multiplier = Decimal(10) ** scale
    try:
        minor = int((dec * multiplier).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None, [f"cannot scale amount: {raw!r}"]

    errors: list[str] = []
    if currency is None:
        errors.append("currency could not be determined")
    return {"amount": minor, "currency": currency, "scale": scale}, errors
