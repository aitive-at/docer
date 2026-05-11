from __future__ import annotations

import hashlib
import secrets
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone
from slugify import slugify


class User(AbstractUser):
    """Custom user model so we can extend later without painful migrations."""

    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["username"]

    def __str__(self) -> str:
        return self.email or self.username


class Account(models.Model):
    PERSONAL = "personal"
    ORG = "organization"
    KIND_CHOICES = [(PERSONAL, "Personal"), (ORG, "Organization")]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=PERSONAL)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    pages_scanned_total = models.PositiveIntegerField(default=0)
    documents_scanned_total = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    @classmethod
    def make_unique_slug(cls, base: str) -> str:
        candidate = slugify(base) or "account"
        candidate = candidate[:64]
        original = candidate
        n = 2
        while cls.objects.filter(slug=candidate).exists():
            candidate = f"{original}-{n}"[:80]
            n += 1
        return candidate


class Membership(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(OWNER, "Owner"), (ADMIN, "Admin"), (MEMBER, "Member")]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "user"], name="uniq_membership_account_user"),
        ]


class ApiKey(models.Model):
    """Per-account API key. Plaintext returned only at creation time."""

    PREFIX_LEN = 8
    KEY_BYTES = 32

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="api_keys")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="api_keys")
    name = models.CharField(max_length=80)
    key_prefix = models.CharField(max_length=PREFIX_LEN, db_index=True)
    key_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def hash_key(cls, plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    @classmethod
    @transaction.atomic
    def issue(cls, *, account: Account, user: User, name: str) -> tuple["ApiKey", str]:
        plaintext = "dk_" + secrets.token_urlsafe(cls.KEY_BYTES)
        record = cls.objects.create(
            account=account,
            user=user,
            name=name,
            key_prefix=plaintext[: cls.PREFIX_LEN],
            key_hash=cls.hash_key(plaintext),
        )
        return record, plaintext

    @classmethod
    def find_active(cls, plaintext: str) -> "ApiKey | None":
        if not plaintext:
            return None
        prefix = plaintext[: cls.PREFIX_LEN]
        digest = cls.hash_key(plaintext)
        return cls.objects.filter(
            key_prefix=prefix, key_hash=digest, revoked_at__isnull=True
        ).select_related("account", "user").first()

    def touch(self) -> None:
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])
