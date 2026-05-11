"""Resolve `<account>` URL kwarg to `request.account` and verify membership."""
from __future__ import annotations

from django.http import Http404
from django.urls import resolve

from .models import Account, Membership


class AccountResolverMiddleware:
    """If the matched URL has a kwarg named `account_slug`, resolve it.

    Sets:
        request.account            -> Account or None
        request.account_membership -> Membership or None (if user authenticated)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.account = None
        request.account_membership = None
        try:
            match = resolve(request.path_info)
        except Exception:
            match = None

        if match is not None:
            slug = match.kwargs.get("account_slug")
            if slug:
                try:
                    account = Account.objects.get(slug=slug)
                except Account.DoesNotExist as exc:
                    raise Http404("Account not found") from exc
                request.account = account
                if request.user.is_authenticated:
                    request.account_membership = Membership.objects.filter(
                        account=account, user=request.user
                    ).first()
        return self.get_response(request)
