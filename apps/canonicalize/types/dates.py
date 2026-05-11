from __future__ import annotations

from datetime import date, datetime
from typing import Any

_DAYFIRST_LANGS = {"de", "at", "ch", "fr", "it", "es", "pt", "nl", "pl", "cz", "sk", "ru"}


def _dayfirst(language: str | None) -> bool:
    if not language:
        return False
    base = language.replace("-", "_").split("_")[0].lower()
    return base in _DAYFIRST_LANGS


def _try_babel_date(text: str, language: str | None) -> date | None:
    if not language:
        return None
    try:
        from babel.dates import parse_date
    except Exception:
        return None
    try:
        return parse_date(text, locale=language.replace("-", "_"))
    except Exception:
        return None


def canon_date(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    if isinstance(raw, datetime):
        return raw.date().isoformat(), []
    if isinstance(raw, date):
        return raw.isoformat(), []
    text = str(raw).strip()

    parsed = _try_babel_date(text, language)
    if parsed is not None:
        return parsed.isoformat(), []

    try:
        from dateutil import parser as du_parser
    except Exception:
        return None, ["dateutil unavailable"]
    try:
        dt = du_parser.parse(text, dayfirst=_dayfirst(language), fuzzy=False)
    except (ValueError, OverflowError, TypeError) as exc:
        return None, [f"cannot parse date: {exc}"]
    return dt.date().isoformat(), []


def canon_datetime(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    if isinstance(raw, datetime):
        return raw.isoformat(), []
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day).isoformat(), []
    text = str(raw).strip()
    try:
        from dateutil import parser as du_parser
    except Exception:
        return None, ["dateutil unavailable"]
    try:
        dt = du_parser.parse(text, dayfirst=_dayfirst(language), fuzzy=False)
    except (ValueError, OverflowError, TypeError) as exc:
        return None, [f"cannot parse datetime: {exc}"]
    return dt.isoformat(), []
