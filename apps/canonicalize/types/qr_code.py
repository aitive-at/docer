"""Canonicalizer for the `qr_code` data type.

The model is asked to decode the QR's payload and return the resulting text
(URL, vCard, payment string, plain text — whatever the QR encodes). The
canonical form is the decoded text preserved exactly: QR payloads often have
significant structure (newlines in vCards, query-string ordering in URLs)
that we must not collapse.
"""
from __future__ import annotations

from typing import Any


def canon_qr_code(raw: Any, language: str | None, options: dict) -> tuple[str, list[str]]:
    if raw is None:
        return "", []
    return str(raw), []
