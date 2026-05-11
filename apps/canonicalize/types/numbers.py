from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER_EXTRACT_RE = re.compile(
    r"[-+]?\d[\d\s.,'   ]*"
)


def _strip_units(text: str) -> str:
    m = _NUMBER_EXTRACT_RE.search(text)
    if not m:
        return ""
    return m.group(0).strip()


def _normalize_number_string(text: str, language: str | None) -> str:
    raw = _strip_units(text)
    if not raw:
        return raw
    raw = raw.replace(" ", "").replace(" ", "").replace(" ", "")
    raw = raw.replace(" ", "").replace("'", "")

    if not raw:
        return raw

    try:
        from babel.core import Locale, UnknownLocaleError
        from babel.numbers import parse_decimal as babel_parse

        locales: list[str] = []
        if language:
            locales.append(language.replace("-", "_"))
        locales.append("en")
        for code in locales:
            try:
                Locale.parse(code)
            except (UnknownLocaleError, Exception):
                continue
            try:
                value = babel_parse(raw, locale=code, strict=False)
                return str(value)
            except Exception:
                continue
    except Exception:
        pass

    cleaned = raw
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        last = cleaned.rfind(",")
        tail = cleaned[last + 1 :]
        if len(tail) == 3 and cleaned.count(",") > 1:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    else:
        if cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "")
    return cleaned


def canon_int(raw: Any, language: str | None, options: dict) -> tuple[int | None, list[str]]:
    if isinstance(raw, bool):
        return None, ["boolean is not int"]
    if isinstance(raw, int):
        return raw, []
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw), []
        return None, ["non-integer float"]
    text = str(raw).strip()
    norm = _normalize_number_string(text, language)
    if not norm:
        return None, [f"cannot parse int: {raw!r}"]
    try:
        dec = Decimal(norm)
    except InvalidOperation:
        return None, [f"cannot parse int: {raw!r}"]
    if dec != dec.to_integral_value():
        return None, [f"value is not integral: {raw!r}"]
    return int(dec), []


def canon_float(raw: Any, language: str | None, options: dict) -> tuple[float | None, list[str]]:
    if isinstance(raw, bool):
        return None, ["boolean is not float"]
    if isinstance(raw, (int, float)):
        return float(raw), []
    text = str(raw).strip()
    norm = _normalize_number_string(text, language)
    if not norm:
        return None, [f"cannot parse float: {raw!r}"]
    try:
        return float(Decimal(norm)), []
    except InvalidOperation:
        return None, [f"cannot parse float: {raw!r}"]


def canon_decimal(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    precision = options.get("precision")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            dec = Decimal(str(raw))
        except InvalidOperation:
            return None, [f"cannot parse decimal: {raw!r}"]
    else:
        text = str(raw).strip()
        norm = _normalize_number_string(text, language)
        if not norm:
            return None, [f"cannot parse decimal: {raw!r}"]
        try:
            dec = Decimal(norm)
        except InvalidOperation:
            return None, [f"cannot parse decimal: {raw!r}"]
    if precision is not None:
        try:
            quant = Decimal(10) ** -int(precision)
            dec = dec.quantize(quant)
        except (InvalidOperation, ValueError):
            return None, [f"invalid precision: {precision!r}"]
    return format(dec, "f"), []
