"""
Admin de diagnóstico interno para el portal de feedback (apps.feedback).

No expuesto al público (el portal es la superficie pública real, vía
`apps/feedback/views.py`) — esto es solo para que el equipo Indunnova
pueda inspeccionar tickets/adjuntos y su estado de sincronización con
GitHub directamente desde `/admin/`.
"""

from django.contrib import admin

from apps.feedback.models import FeedbackAttachment, FeedbackTicket


@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    """Admin de diagnóstico para FeedbackTicket."""

    list_display = [
        "id",
        "asunto",
        "nombre_reportante",
        "estado",
        "sincronizado_github",
        "created_at",
        "ip_reportante",
    ]
    list_filter = ["estado", "sincronizado_github", "created_at"]
    search_fields = ["asunto", "nombre_reportante", "descripcion"]
    readonly_fields = [
        "github_issue_number",
        "github_url",
        "sincronizado_github",
        "error_sincronizacion",
        "resuelto_por",
        "resuelto_at",
        "created_at",
        "updated_at",
        "ip_reportante",
    ]


@admin.register(FeedbackAttachment)
class FeedbackAttachmentAdmin(admin.ModelAdmin):
    """Admin de diagnóstico para FeedbackAttachment."""

    list_display = ["id", "ticket", "tipo", "nombre_original", "mime_type", "created_at"]
    list_filter = ["tipo", "created_at"]
    search_fields = ["nombre_original", "ticket__asunto"]
    readonly_fields = ["created_at"]
