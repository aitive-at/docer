from __future__ import annotations

from typing import Any


def canon_email(raw: Any, language: str | None, options: dict) -> tuple[str | None, list[str]]:
    from email_validator import EmailNotValidError, validate_email

    text = str(raw).strip()
    try:
        info = validate_email(text, check_deliverability=False)
    except EmailNotValidError as exc:
        return None, [f"invalid email: {exc}"]
    return info.normalized.lower(), []
