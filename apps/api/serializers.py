from __future__ import annotations

from rest_framework import serializers

from apps.scanners.models import Scanner
from apps.scans.models import Scan, ScanFieldResult


class ScannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scanner
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "priming_prompt",
            "schema_json",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class ScanFieldResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanFieldResult
        fields = [
            "path",
            "data_type",
            "original_value",
            "canonical_value",
            "confidence",
            "page_index",
            "bbox",
            "attempts",
            "error",
        ]


class ScanSerializer(serializers.ModelSerializer):
    field_results = ScanFieldResultSerializer(many=True, read_only=True)
    scanner_slug = serializers.CharField(source="scanner.slug", read_only=True)
    file_sha256 = serializers.CharField(source="file.sha256", read_only=True)

    class Meta:
        model = Scan
        fields = [
            "id",
            "scanner_slug",
            "file_sha256",
            "status",
            "progress_pct",
            "progress_message",
            "extracted_json",
            "error_message",
            "pages_processed",
            "created_at",
            "started_at",
            "finished_at",
            "field_results",
        ]
