"""
Admin configuration for courses app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    Course,
    CourseSchedule,
    Enrollment,
    JobProfileType,
    Lesson,
    LessonEvidence,
    LessonProgress,
    MediaAsset,
    Module,
    ScheduleAssignment,
)


@admin.register(JobProfileType)
class JobProfileTypeAdmin(admin.ModelAdmin):
    """Admin configuration for JobProfileType model."""

    list_display = ["code", "name", "is_active", "order"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    ordering = ["order"]


class ModuleInline(admin.TabularInline):
    """Inline for modules in course admin."""

    model = Module
    extra = 1
    ordering = ["order"]
    fields = ["title", "order", "description"]


class LessonInline(admin.TabularInline):
    """Inline for lessons in module admin."""

    model = Lesson
    extra = 1
    ordering = ["order"]
    fields = ["title", "lesson_type", "duration", "order", "is_mandatory"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """Admin configuration for Course model."""

    list_display = [
        "code",
        "title",
        "course_type",
        "status",
        "version",
        "get_total_duration",
        "created_at",
    ]
    list_filter = ["status", "course_type", "created_at"]
    search_fields = ["code", "title", "description"]
    readonly_fields = ["created_at", "updated_at", "published_at", "get_total_duration"]
    date_hierarchy = "created_at"
    inlines = [ModuleInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["code", "title", "description", "objectives"],
            },
        ),
        (
            _("Configuración"),
            {
                "fields": [
                    "course_type",
                    "validity_months",
                    "version",
                    "get_total_duration",
                ],
            },
        ),
        (
            _("Asignación"),
            {
                "fields": ["target_profiles", "prerequisites"],
            },
        ),
        (
            _("Media"),
            {
                "fields": ["thumbnail"],
                "classes": ["collapse"],
            },
        ),
        (
            _("Estado"),
            {
                "fields": ["status", "published_at", "created_by"],
            },
        ),
        (
            _("Auditoría"),
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    @admin.display(description=_("Duración total"))
    def get_total_duration(self, obj):
        """Display total duration calculated from lessons."""
        return f"{obj.total_duration} min"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """Admin configuration for Module model."""

    list_display = ["title", "course", "order", "lesson_count", "created_at"]
    list_filter = ["course", "created_at"]
    search_fields = ["title", "description", "course__title"]
    ordering = ["course", "order"]
    inlines = [LessonInline]

    @admin.display(description=_("Lecciones"))
    def lesson_count(self, obj):
        return obj.lessons.count()


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    """Admin configuration for Lesson model."""

    list_display = [
        "title",
        "module",
        "lesson_type",
        "duration",
        "order",
        "is_mandatory",
        "is_presential",
        "is_offline_available",
    ]
    list_filter = [
        "lesson_type",
        "is_mandatory",
        "is_presential",
        "is_offline_available",
        "created_at",
    ]
    search_fields = ["title", "description", "module__title"]
    ordering = ["module", "order"]
    readonly_fields = ["video_preview"]

    fieldsets = [
        (
            None,
            {
                "fields": ["module", "title", "description", "lesson_type"],
            },
        ),
        (
            _("Contenido"),
            {
                "fields": ["content", "content_file", "video_url", "video_preview"],
            },
        ),
        (
            _("Configuración"),
            {
                "fields": [
                    "duration",
                    "order",
                    "is_mandatory",
                    "is_presential",
                    "is_offline_available",
                ],
            },
        ),
        (
            _("Metadatos"),
            {
                "fields": ["metadata"],
                "classes": ["collapse"],
            },
        ),
    ]

    @admin.display(description=_("Vista previa de video"))
    def video_preview(self, obj):
        """Display YouTube video preview in admin."""
        if obj.lesson_type == "video" and obj.video_url:
            embed_url = obj.video_url
            return format_html(
                '<iframe style="width: 100%; height: 400px; border-radius: 8px;" '
                'src="{}" title="{}" allowfullscreen loading="lazy" '
                'referrerpolicy="strict-origin-when-cross-origin" '
                'sandbox="allow-same-origin allow-scripts allow-popups allow-presentation">'
                "</iframe>",
                embed_url,
                obj.title,
            )
        return "-"


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    """Admin configuration for MediaAsset model."""

    list_display = [
        "original_name",
        "file_type",
        "size_display",
        "status",
        "uploaded_by",
        "created_at",
    ]
    list_filter = ["file_type", "status", "created_at"]
    search_fields = ["filename", "original_name"]
    readonly_fields = ["filename", "mime_type", "size", "created_at", "updated_at"]
    date_hierarchy = "created_at"

    @admin.display(description=_("Tamaño"))
    def size_display(self, obj):
        """Display file size in human readable format."""
        size = obj.size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """Admin configuration for Enrollment model."""

    list_display = [
        "user",
        "course",
        "status",
        "progress_display",
        "due_date",
        "assigned_by",
        "created_at",
    ]
    list_filter = ["status", "created_at", "due_date"]
    search_fields = ["user__email", "user__first_name", "course__title"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"
    raw_id_fields = ["user", "course", "assigned_by"]

    @admin.display(description=_("Progreso"))
    def progress_display(self, obj):
        """Display progress as a colored bar."""
        color = "green" if obj.progress >= 100 else "blue" if obj.progress >= 50 else "orange"
        return format_html(
            '<div style="width:100px;background:#eee;border-radius:3px;">'
            '<div style="width:{}%;background:{};height:20px;border-radius:3px;text-align:center;color:white;">'
            "{}%</div></div>",
            min(obj.progress, 100),
            color,
            obj.progress,
        )


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    """Admin configuration for LessonProgress model."""

    list_display = [
        "enrollment",
        "lesson",
        "is_completed",
        "progress_percent",
        "time_spent_display",
        "completed_at",
    ]
    list_filter = ["is_completed", "created_at"]
    search_fields = ["enrollment__user__email", "lesson__title"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["enrollment", "lesson"]

    @admin.display(description=_("Tiempo"))
    def time_spent_display(self, obj):
        """Display time spent in human readable format."""
        minutes = obj.time_spent // 60
        seconds = obj.time_spent % 60
        return f"{minutes}m {seconds}s"


@admin.register(LessonEvidence)
class LessonEvidenceAdmin(admin.ModelAdmin):
    """Admin configuration for LessonEvidence model."""

    list_display = [
        "lesson",
        "user",
        "evidence_type",
        "verified",
        "verified_by",
        "uploaded_at",
    ]
    list_filter = ["evidence_type", "verified", "uploaded_at"]
    search_fields = ["lesson__title", "user__first_name", "user__last_name", "description"]
    readonly_fields = ["uploaded_at"]
    raw_id_fields = ["lesson", "user", "verified_by"]
    date_hierarchy = "uploaded_at"

    fieldsets = [
        (
            None,
            {
                "fields": ["lesson", "user", "evidence_type", "file", "description"],
            },
        ),
        (
            _("Verificación"),
            {
                "fields": ["verified", "verified_by", "verified_at"],
            },
        ),
    ]


class ScheduleAssignmentInline(admin.TabularInline):
    """Convocados de una programación (SD#73)."""

    model = ScheduleAssignment
    extra = 0
    autocomplete_fields = ["user"]
    readonly_fields = ["created_at"]


@admin.register(CourseSchedule)
class CourseScheduleAdmin(admin.ModelAdmin):
    """Programaciones de curso (SD#73)."""

    list_display = ["name", "course", "responsable", "suggested_end_date", "created_at"]
    list_filter = ["course", "suggested_end_date", "created_at"]
    search_fields = ["name", "course__title", "course__code"]
    autocomplete_fields = ["responsable", "created_by"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ScheduleAssignmentInline]


@admin.register(ScheduleAssignment)
class ScheduleAssignmentAdmin(admin.ModelAdmin):
    """Convocados a programaciones (SD#73)."""

    list_display = ["user", "schedule", "source", "created_at"]
    list_filter = ["source", "schedule"]
    search_fields = ["user__first_name", "user__last_name", "user__document_number"]
    autocomplete_fields = ["user", "schedule", "enrollment"]
    readonly_fields = ["created_at"]
