from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Account, ApiKey, Membership, User


@admin.register(User)
class DocerUserAdmin(UserAdmin):
    pass


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "documents_scanned_total", "pages_scanned_total", "created_at")
    search_fields = ("name", "slug")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("account", "user", "role", "created_at")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("account", "name", "key_prefix", "created_at", "revoked_at")
    readonly_fields = ("key_prefix", "key_hash", "created_at", "last_used_at")
