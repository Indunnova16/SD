"""
Admin configuration for assessments app.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Answer, Assessment, AssessmentAttempt, AttemptAnswer, Question


class AnswerInline(admin.TabularInline):
    """Inline for answers in question admin."""

    model = Answer
    extra = 4
    ordering = ["order"]


class QuestionInline(admin.TabularInline):
    """Inline for questions in assessment admin."""

    model = Question
    extra = 1
    ordering = ["order"]
    fields = ["question_type", "text", "points", "order"]


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    """Admin configuration for Assessment model."""

    list_display = [
        "title",
        "assessment_type",
        "course",
        "passing_score",
        "total_questions",
        "status",
        "created_at",
    ]
    list_filter = ["assessment_type", "status", "created_at"]
    search_fields = ["title", "description", "course__title"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [QuestionInline]
    autocomplete_fields = ["course", "lesson"]

    fieldsets = [
        (
            None,
            {
                "fields": ["title", "description", "assessment_type"],
            },
        ),
        (
            _("Asociación"),
            {
                "fields": ["course", "lesson"],
            },
        ),
        (
            _("Configuración"),
            {
                "fields": [
                    "passing_score",
                    "time_limit",
                    "max_attempts",
                    "shuffle_questions",
                    "shuffle_answers",
                    "show_correct_answers",
                ],
            },
        ),
        (
            _("Estado"),
            {
                "fields": ["status", "created_by"],
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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin configuration for Question model."""

    list_display = ["text_preview", "assessment", "question_type", "points", "order"]
    list_filter = ["question_type", "assessment"]
    search_fields = ["text", "assessment__title"]
    inlines = [AnswerInline]

    @admin.display(description=_("Pregunta"))
    def text_preview(self, obj):
        return obj.text[:100] + "..." if len(obj.text) > 100 else obj.text


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    """Admin configuration for AssessmentAttempt model."""

    list_display = [
        "user",
        "assessment",
        "attempt_number",
        "status",
        "score",
        "passed",
        "started_at",
    ]
    list_filter = ["status", "passed", "started_at"]
    search_fields = ["user__email", "assessment__title"]
    readonly_fields = [
        "started_at",
        "submitted_at",
        "graded_at",
        "ip_address",
        "user_agent",
    ]
    raw_id_fields = ["user", "graded_by"]


@admin.register(AttemptAnswer)
class AttemptAnswerAdmin(admin.ModelAdmin):
    """Admin configuration for AttemptAnswer model."""

    list_display = [
        "attempt",
        "question",
        "is_correct",
        "points_awarded",
        "answered_at",
    ]
    list_filter = ["is_correct", "answered_at"]
    raw_id_fields = ["attempt", "question"]
