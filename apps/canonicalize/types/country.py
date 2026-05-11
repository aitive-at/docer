from __future__ import annotations

from typing import Any

from ._helpers import collapse_ws, fold_diacritics

_BUILTIN: dict[str, str] = {
    "de": "DE", "deutschland": "DE", "germany": "DE", "allemagne": "DE",
    "at": "AT", "oesterreich": "AT", "austria": "AT", "autriche": "AT",
    "ch": "CH", "schweiz": "CH", "switzerland": "CH", "suisse": "CH",
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "gb": "GB", "great britain": "GB", "united kingdom": "GB", "england": "GB",
    "fr": "FR", "france": "FR", "frankreich": "FR",
    "it": "IT", "italy": "IT", "italia": "IT", "italien": "IT",
    "es": "ES", "spain": "ES", "espana": "ES", "spanien": "ES",
    "nl": "NL", "netherlands": "NL", "niederlande": "NL", "holland": "NL",
    "be": "BE", "belgium": "BE", "belgien": "BE", "belgique": "BE",
    "lu": "LU", "luxembourg": "LU", "luxemburg": "LU",
    "pl": "PL", "poland": "PL", "polen": "PL",
    "cz": "CZ", "czech republic": "CZ", "czechia": "CZ", "tschechien": "CZ",
    "se": "SE", "sweden": "SE", "schweden": "SE",
    "no": "NO", "norway": "NO", "norwegen": "NO",
    "dk": "DK", "denmark": "DK", "daenemark": "DK",
    "fi": "FI", "finland": "FI", "finnland": "FI",
}


def _from_babel(text_norm: str) -> str | None:
    try:
        from babel import Locale
    except Exception:
        return None
    candidates: list[str] = []
    for loc_code in ("en", "de", "fr", "es", "it"):
        try:
            loc = Locale.parse(loc_code)
        except Exception:
            continue
        for code, name in loc.territories.items():
            if not isinstance(code, str) or len(code) != 2 or not code.isalpha():
                continue
            normalized = collapse_ws(fold_diacritics(name).lower())
            if normalized == text_norm:
                candidates.append(code.upper())
    if candidates:
        return candidates[0]
    return None


def canon_country(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    text = collapse_ws(str(raw))
    norm = collapse_ws(fold_diacritics(text).lower())
    if norm in _BUILTIN:
        return _BUILTIN[norm], []
    if len(text) == 2 and text.isalpha():
        return text.upper(), []
    code = _from_babel(norm)
    if code:
        return code, []
    return None, [f"unknown country: {text!r}"]
