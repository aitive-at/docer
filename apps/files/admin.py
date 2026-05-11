from django.contrib import admin

from .models import PageImage, StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "account", "mime", "page_count", "size", "created_at")
    search_fields = ("original_name", "sha256")


@admin.register(PageImage)
class PageImageAdmin(admin.ModelAdmin):
    list_display = ("stored_file", "index", "width", "height")
