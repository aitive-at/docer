from __future__ import annotations

from django.db import models

from apps.accounts.models import Account


class StoredFile(models.Model):
    """Per-account, content-addressed storage of an uploaded document."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="files")
    sha256 = models.CharField(max_length=64, db_index=True)
    mime = models.CharField(max_length=80)
    size = models.PositiveBigIntegerField()
    blob_path = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255)
    page_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "sha256"], name="uniq_file_account_sha256"),
        ]

    def __str__(self) -> str:
        return f"{self.original_name} ({self.sha256[:8]})"


class PageImage(models.Model):
    """Cached rasterized page image for a stored file."""

    stored_file = models.ForeignKey(StoredFile, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveSmallIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    image_path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["stored_file", "index"], name="uniq_page_per_file"),
        ]
        ordering = ["index"]
