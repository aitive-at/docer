from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from . import numbers as _num

_SPLIT_RE = re.compile(r"^\s*([-+]?[\d][\d  .,']*)\s*(.*)$")


def canon_quantity(raw: Any, language: str | None, options: dict) -> tuple[dict | None, list[str]]:
    text = str(raw).strip()
    if not text:
        return None, ["empty quantity"]
    m = _SPLIT_RE.match(text)
    if not m:
        return None, [f"no numeric portion: {raw!r}"]
    number_text, unit = m.group(1), m.group(2).strip()
    norm = _num._normalize_number_string(number_text, language)
    try:
        dec = Decimal(norm)
    except (InvalidOperation, ValueError):
        return None, [f"cannot parse quantity: {raw!r}"]
    unit_norm = unit.lower().strip().rstrip(".")
    return {"value": format(dec, "f"), "unit": unit_norm}, []
