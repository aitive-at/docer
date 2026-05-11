from __future__ import annotations

from typing import Any

from stdnum.exceptions import ValidationError


def canon_vat(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    from stdnum.eu import vat as eu_vat

    text = "".join(str(raw).split()).upper()
    try:
        compact = eu_vat.validate(text)
        return compact.upper(), []
    except ValidationError:
        pass

    if len(text) >= 2 and text[:2].isalpha():
        prefix = text[:2]
        rest = text[2:]
        country_compact = _try_country_specific(prefix, rest)
        if country_compact is not None:
            return f"{prefix}{country_compact}", []

    return None, [f"invalid VAT id: {raw!r}"]


def _try_country_specific(prefix: str, rest: str) -> str | None:
    try:
        from stdnum.util import get_cc_module
    except Exception:
        return None
    module = get_cc_module(prefix.lower(), "vat")
    if module is None:
        return None
    try:
        return module.validate(rest)
    except ValidationError:
        return None
    except Exception:
        return None
