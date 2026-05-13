"""Canonicalize date / datetime fields to ISO-8601 strings.

The LLM returns dates *as printed* in the source document — e.g.
"8. Mai 2026", "1er janvier 2024", "8 de mayo de 2026", "Mar 8, 2024".
Our job is to normalize all of those to "2026-05-08" / "2024-01-01" /
"2026-05-08" / "2024-03-08" regardless of source language.

Parsing stack (first that succeeds wins):
  1. `dateparser` — handles natural-language month names in many locales,
     ordinal markers ("1er", "1.", "1st"), and "de mayo de"-style
     prepositions. Driven by an optional language hint + DMY/MDY order.
  2. `babel.dates.parse_date` — strict locale-aware numeric formats.
  3. `dateutil.parser.parse` — English-language fallback.

The chain is intentionally permissive: if the LLM occasionally returns
something weird (e.g. an ISO string when we asked for the original) we
still parse correctly. The cost of an extra parser attempt is microseconds.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Locales where DD-comes-before-MM is the printed convention. Used when the
# language hint is provided but dateparser still needs DMY/MDY guidance for
# numeric-only formats like "03/04/2024".
_DAYFIRST_LANGS = {"de", "at", "ch", "fr", "it", "es", "pt", "nl", "pl", "cz", "sk", "ru"}


def _normalize_lang(language: str | None) -> str | None:
    if not language:
        return None
    return language.replace("-", "_").split("_")[0].lower()


def _dayfirst(language: str | None) -> bool:
    base = _normalize_lang(language)
    return base in _DAYFIRST_LANGS if base else False


def _try_dateparser(text: str, language: str | None) -> datetime | None:
    """Parse via the `dateparser` library — multilingual + format-tolerant."""
    try:
        import dateparser
    except Exception:
        return None
    base = _normalize_lang(language)
    languages = [base] if base else None
    settings: dict = {"PREFER_DAY_OF_MONTH": "first"}
    if _dayfirst(language):
        settings["DATE_ORDER"] = "DMY"
    try:
        return dateparser.parse(text, languages=languages, settings=settings)
    except Exception:
        return None


def _try_babel(text: str, language: str | None) -> date | None:
    base = _normalize_lang(language)
    if not base:
        return None
    try:
        from babel.dates import parse_date
    except Exception:
        return None
    try:
        return parse_date(text, locale=base)
    except Exception:
        return None


def _try_dateutil(text: str, language: str | None) -> datetime | None:
    try:
        from dateutil import parser as du_parser
    except Exception:
        return None
    try:
        return du_parser.parse(text, dayfirst=_dayfirst(language), fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        return None


def canon_date(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    if isinstance(raw, datetime):
        return raw.date().isoformat(), []
    if isinstance(raw, date):
        return raw.isoformat(), []
    text = str(raw).strip()
    if not text:
        return None, []

    parsed = _try_dateparser(text, language)
    if parsed is not None:
        return parsed.date().isoformat(), []

    babel_parsed = _try_babel(text, language)
    if babel_parsed is not None:
        return babel_parsed.isoformat(), []

    du_parsed = _try_dateutil(text, language)
    if du_parsed is not None:
        return du_parsed.date().isoformat(), []

    return None, [f"cannot parse date: {text!r}"]


def canon_datetime(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    if isinstance(raw, datetime):
        return raw.isoformat(), []
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day).isoformat(), []
    text = str(raw).strip()
    if not text:
        return None, []

    parsed = _try_dateparser(text, language)
    if parsed is not None:
        return parsed.isoformat(), []

    du_parsed = _try_dateutil(text, language)
    if du_parsed is not None:
        return du_parsed.isoformat(), []

    return None, [f"cannot parse datetime: {text!r}"]
