from __future__ import annotations

from django.db import transaction

from .models import Account, Membership, User


@transaction.atomic
def create_personal_account(user: User, *, base_name: str | None = None) -> Account:
    name = base_name or (user.get_full_name() or user.email.split("@")[0])
    account = Account.objects.create(
        kind=Account.PERSONAL,
        name=name,
        slug=Account.make_unique_slug(name),
    )
    Membership.objects.create(account=account, user=user, role=Membership.OWNER)
    return account
