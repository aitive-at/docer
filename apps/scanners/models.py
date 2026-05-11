from __future__ import annotations

from django.db import models
from slugify import slugify

from apps.accounts.models import Account


class Scanner(models.Model):
    """A configured document type that an account scans against."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="scanners")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80)
    description = models.TextField(blank=True)
    priming_prompt = models.TextField(blank=True)
    language_hint = models.CharField(max_length=10, blank=True)
    model_override = models.CharField(max_length=120, blank=True)
    schema_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "slug"], name="uniq_scanner_account_slug"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.account.slug}/{self.slug}"

    def make_unique_slug(self, base: str) -> str:
        candidate = slugify(base) or "scanner"
        candidate = candidate[:64]
        original = candidate
        n = 2
        qs = Scanner.objects.filter(account=self.account)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        while qs.filter(slug=candidate).exists():
            candidate = f"{original}-{n}"[:80]
            n += 1
        return candidate
