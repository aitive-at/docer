from __future__ import annotations

from typing import Any

_TRUE = {
    "true", "t", "yes", "y", "1",
    "ja", "j", "wahr",
    "oui", "o", "vrai",
    "si", "verdadero", "verdad",
    "sì", "vero",
    "tak",
    "on",
}
_FALSE = {
    "false", "f", "no", "n", "0",
    "nein", "falsch",
    "non", "faux",
    "falso",
    "nie",
    "off",
}


def canon_boolean(raw: Any, language: str | None, options: dict) -> tuple[bool | None, list[str]]:
    if isinstance(raw, bool):
        return raw, []
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw), []
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True, []
    if text in _FALSE:
        return False, []
    return None, [f"cannot parse boolean: {raw!r}"]
