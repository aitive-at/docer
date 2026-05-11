from django.contrib import admin

from .models import Scan, ScanFieldResult


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "scanner", "status", "progress_pct", "created_at", "finished_at")
    list_filter = ("status",)
    raw_id_fields = ("file",)


@admin.register(ScanFieldResult)
class ScanFieldResultAdmin(admin.ModelAdmin):
    list_display = ("scan", "path", "data_type", "original_value", "page_index")
