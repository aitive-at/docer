from django.contrib import admin

from .models import Scanner


@admin.register(Scanner)
class ScannerAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "account", "language_hint", "updated_at")
    search_fields = ("name", "slug")
    list_filter = ("account",)
