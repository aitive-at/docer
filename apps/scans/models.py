from __future__ import annotations

from django.db import models

from apps.accounts.models import Account
from apps.files.models import StoredFile
from apps.scanners.models import Scanner


class Scan(models.Model):
    QUEUED = "queued"
    PREPARING = "preparing"
    EXTRACTING = "extracting"
    LOCATING = "locating"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    STATUS_CHOICES = [
        (QUEUED, "Queued"),
        (PREPARING, "Preparing"),
        (EXTRACTING, "Extracting"),
        (LOCATING, "Locating"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
        (PARTIAL, "Partial"),
    ]
    TERMINAL = {COMPLETED, FAILED, PARTIAL}

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="scans")
    scanner = models.ForeignKey(Scanner, on_delete=models.CASCADE, related_name="scans")
    file = models.ForeignKey(StoredFile, on_delete=models.PROTECT, related_name="scans")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    progress_pct = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=200, blank=True)

    extracted_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    pages_processed = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL


class ScanFieldResult(models.Model):
    """One row per leaf field that was extracted (or attempted)."""

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="field_results")
    path = models.CharField(max_length=400)
    data_type = models.CharField(max_length=40)
    original_value = models.TextField(blank=True)
    canonical_value = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    page_index = models.PositiveSmallIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    attempts = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["path"]
