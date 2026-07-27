"""
Modelos del portal público de feedback/tickets ("portal de SD - Cursos").

Superficie pública/anónima (sin login) donde cualquier usuario reporta un
problema o sugerencia. Cada ticket se sincroniza (best-effort, sin perder
el reporte ante fallos) como un GitHub Issue en Indunnova16/SD.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class FeedbackTicket(models.Model):
    """
    Ticket reportado desde el portal público de feedback.

    Se sincroniza de forma síncrona (best-effort) hacia GitHub como un
    issue en Indunnova16/SD (label `portal-web`, assignee `Indunnova`).
    Un fallo de sincronización NO borra el ticket: queda registrado con
    `sincronizado_github=False` y `error_sincronizacion` poblado para que
    el reporte del usuario nunca se pierda.
    """

    nombre_reportante = models.CharField(_("Nombre del reportante"), max_length=120)
    asunto = models.CharField(_("Asunto"), max_length=200)
    descripcion = models.TextField(_("Descripción"))

    github_issue_number = models.IntegerField(
        _("Número de issue en GitHub"),
        null=True,
        blank=True,
        unique=True,
    )
    github_url = models.URLField(_("URL del issue en GitHub"), blank=True)
    sincronizado_github = models.BooleanField(
        _("Sincronizado con GitHub"), default=False
    )
    error_sincronizacion = models.TextField(_("Error de sincronización"), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Ticket de feedback")
        verbose_name_plural = _("Tickets de feedback")

    def __str__(self):
        return self.asunto


class FeedbackAttachment(models.Model):
    """
    Imagen adjunta a un `FeedbackTicket`, subida desde el portal público.

    NOTA (ver services.py de A4): al crearse fuera de un ModelForm, este
    modelo NO ejecuta `full_clean()` automáticamente — la validación real
    de que el contenido es una imagen (Pillow) vive en la capa de servicio,
    no depende de los validadores nativos de `ImageField`.
    """

    ticket = models.ForeignKey(
        FeedbackTicket,
        on_delete=models.CASCADE,
        related_name="adjuntos",
        verbose_name=_("Ticket"),
    )
    imagen = models.ImageField(
        _("Imagen"), upload_to="feedback/adjuntos/%Y/%m/"
    )
    nombre_original = models.CharField(
        _("Nombre original del archivo"), max_length=255, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Adjunto de feedback")
        verbose_name_plural = _("Adjuntos de feedback")

    def __str__(self):
        return self.nombre_original or f"Adjunto #{self.pk} de ticket #{self.ticket_id}"
