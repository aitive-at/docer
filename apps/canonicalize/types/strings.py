from __future__ import annotations

from typing import Any

from ._helpers import collapse_ws


def canon_string(raw: Any, language: str | None, options: dict) -> tuple[str, list[str]]:
    return collapse_ws(str(raw)), []


def canon_zip(raw: Any, language: str | None, options: dict) -> tuple[str, list[str]]:
    text = str(raw).replace(" ", "").replace("\t", "")
    return text.upper(), []
