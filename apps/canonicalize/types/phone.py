from __future__ import annotations

from typing import Any


def _region_from_language(language: str | None) -> str | None:
    if not language:
        return None
    lang = language.replace("-", "_")
    if "_" in lang:
        tail = lang.split("_", 1)[1]
        if len(tail) == 2 and tail.isalpha():
            return tail.upper()
    if len(lang) == 2 and lang.isalpha():
        return lang.upper()
    return None


def canon_phone(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    import phonenumbers

    text = str(raw).strip()
    region = options.get("default_region") or _region_from_language(language)
    try:
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException as exc:
        return None, [f"invalid phone: {exc}"]
    if not phonenumbers.is_valid_number(parsed):
        return None, ["invalid phone number"]
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), []
