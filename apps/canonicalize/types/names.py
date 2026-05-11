from __future__ import annotations

import re
from typing import Any

from ._helpers import collapse_ws, fold_diacritics

_HAS_DIGIT_RE = re.compile(r"\d")
_LOWER_PARTICLES = {"von", "van", "de", "der", "den", "del", "di", "da", "le", "la"}


def _smart_title(text: str) -> str:
    parts = []
    for raw in text.split(" "):
        if not raw:
            parts.append(raw)
            continue
        if _HAS_DIGIT_RE.search(raw):
            parts.append(raw)
            continue
        if "-" in raw:
            parts.append("-".join(_title_word(w) for w in raw.split("-")))
        else:
            parts.append(_title_word(raw))
    fixed = []
    for idx, p in enumerate(parts):
        low = p.lower()
        if idx > 0 and low in _LOWER_PARTICLES:
            fixed.append(low)
        else:
            fixed.append(p)
    return " ".join(fixed)


def _title_word(word: str) -> str:
    if not word:
        return word
    if word.startswith("Mc") and len(word) > 2:
        return "Mc" + word[2].upper() + word[3:].lower()
    if word.lower().startswith("mac") and len(word) > 3:
        return "Mac" + word[3].upper() + word[4:].lower()
    if word[0].isalpha():
        return word[0].upper() + word[1:].lower()
    return word


def canon_name(raw: Any, language: str | None, options: dict) -> tuple[dict, list[str]]:
    text = collapse_ws(str(raw))
    display = _smart_title(text)
    comparable = collapse_ws(fold_diacritics(display).lower())
    return {"display": display, "comparable": comparable}, []


def canon_street(raw: Any, language: str | None, options: dict) -> tuple[dict, list[str]]:
    text = collapse_ws(str(raw))
    display = _smart_title(text)
    comparable = collapse_ws(fold_diacritics(display).lower())
    return {"display": display, "comparable": comparable}, []


def canon_city(raw: Any, language: str | None, options: dict) -> tuple[dict, list[str]]:
    text = collapse_ws(str(raw))
    display = _smart_title(text)
    comparable = collapse_ws(fold_diacritics(display).lower())
    return {"display": display, "comparable": comparable}, []
