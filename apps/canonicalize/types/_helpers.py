from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


_FOLD_MAP = {
    "ß": "ss",
    "Ø": "O",
    "ø": "o",
    "Æ": "AE",
    "æ": "ae",
    "Œ": "OE",
    "œ": "oe",
    "Ł": "L",
    "ł": "l",
    "Ð": "D",
    "ð": "d",
    "Þ": "Th",
    "þ": "th",
}


def fold_diacritics(text: str) -> str:
    text = "".join(_FOLD_MAP.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_locale(language: str | None) -> str:
    if not language:
        return "en"
    return language.replace("-", "_")
