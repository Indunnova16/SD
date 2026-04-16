"""
Admin configuration for sync app.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import OfflinePackage, PackageDownload, SyncConflict, SyncLog


class SyncConflictInline(admin.TabularInline):
    """Inline for conflicts in sync log admin."""

    model = SyncConflict
    extra = 0
    readonly_fields = ["model_name", "record_id", "resolution", "resolved_at"]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    """Admin configuration for SyncLog model."""

    list_display = [
        "user",
        "device_id",
        "direction",
        "status",
        "records_uploaded",
        "records_downloaded",
        "created_at",
    ]
    list_filter = ["status", "direction", "created_at"]
    search_fields = ["user__email", "device_id", "device_name"]
    readonly_fields = [
        "created_at",
        "started_at",
        "completed_at",
        "server_timestamp",
    ]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    inlines = [SyncConflictInline]


@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    """Admin configuration for SyncConflict model."""

    list_display = [
        "sync_log",
        "model_name",
        "record_id",
        "resolution",
        "resolved_at",
    ]
    list_filter = ["resolution", "model_name", "created_at"]
    readonly_fields = ["created_at", "resolved_at"]
    raw_id_fields = ["sync_log", "resolved_by"]


@admin.register(OfflinePackage)
class OfflinePackageAdmin(admin.ModelAdmin):
    """Admin configuration for OfflinePackage model."""

    list_display = [
        "name",
        "course",
        "version",
        "status",
        "file_size_display",
        "created_at",
    ]
    list_filter = ["status", "includes_videos", "includes_assessments"]
    search_fields = ["name", "course__title"]
    readonly_fields = [
        "file_size",
        "checksum",
        "build_started_at",
        "build_completed_at",
        "created_at",
        "updated_at",
    ]
    autocomplete_fields = ["course"]

    @admin.display(description=_("Tamaño"))
    def file_size_display(self, obj):
        """Display file size in human readable format."""
        if not obj.file_size:
            return "-"
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@admin.register(PackageDownload)
class PackageDownloadAdmin(admin.ModelAdmin):
    """Admin configuration for PackageDownload model."""

    list_display = [
        "user",
        "package",
        "device_id",
        "download_completed",
        "downloaded_at",
    ]
    list_filter = ["download_completed", "downloaded_at"]
    search_fields = ["user__email", "device_id"]
    raw_id_fields = ["user"]
    readonly_fields = ["downloaded_at"]
