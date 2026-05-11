"""DRF authentication backend that accepts account-scoped API keys."""
from __future__ import annotations

from rest_framework import authentication, exceptions

from apps.accounts.models import ApiKey


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header:
            return None
        parts = header.split(" ", 1)
        if len(parts) != 2 or parts[0] != self.keyword:
            return None
        plaintext = parts[1].strip()
        record = ApiKey.find_active(plaintext)
        if not record:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")
        record.touch()
        request.api_key = record
        request.api_account = record.account
        if record.user is None:
            raise exceptions.AuthenticationFailed("API key has no associated user.")
        return (record.user, record)

    def authenticate_header(self, request):
        return self.keyword
