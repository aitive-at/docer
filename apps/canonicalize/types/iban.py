from __future__ import annotations

from typing import Any


def canon_iban(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    from stdnum import iban as stdnum_iban
    from stdnum.exceptions import ValidationError

    text = str(raw).strip()
    try:
        compact = stdnum_iban.validate(text)
    except ValidationError as exc:
        return None, [f"invalid IBAN: {exc}"]
    return compact.upper(), []
