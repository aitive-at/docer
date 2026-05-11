from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Account, Membership


def resolve_account_or_403(request, account_slug: str) -> Account:
    """Return the Account for the URL slug; require user to be a member.

    Works whether the user authenticated by session or by API key. API-key auth
    populates request.user (key.user). For API-key auth we additionally require
    that the key's account matches the URL slug.
    """
    account = get_object_or_404(Account, slug=account_slug)

    api_key = getattr(request, "api_key", None)
    if api_key is not None:
        if api_key.account_id != account.id:
            raise PermissionDenied("API key not authorized for this account.")
        return account

    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if not Membership.objects.filter(account=account, user=request.user).exists():
        raise PermissionDenied("Not a member of this account.")
    return account
