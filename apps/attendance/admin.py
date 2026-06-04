from django.contrib import admin

from .models import AttendanceRecord, FaceCheckEvent


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "check_in", "check_out", "hours_worked", "is_absent")
    list_filter = ("is_absent", "date")
    search_fields = ("user__document_number", "user__first_name", "user__last_name")
    date_hierarchy = "date"
    autocomplete_fields = ("user", "registered_by")


@admin.register(FaceCheckEvent)
class FaceCheckEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "status", "user", "similarity")
    list_filter = ("status", "kind", "created_at")
    search_fields = ("user__document_number", "user__first_name", "user__last_name")
    date_hierarchy = "created_at"
    readonly_fields = (
        "created_at",
        "updated_at",
        "selfie",
        "similarity",
        "aws_face_id",
        "latitude",
        "longitude",
        "user_agent",
        "ip_address",
        "error_message",
    )
