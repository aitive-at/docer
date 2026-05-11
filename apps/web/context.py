from __future__ import annotations

from django.http import HttpRequest


def brand(request: HttpRequest) -> dict:
    """Template context: brand identity + current account, if any."""
    return {
        "brand_name": "Docer",
        "brand_tagline": "// Vision · Extraction · Structured Data",
        "current_account": getattr(request, "account", None),
    }
