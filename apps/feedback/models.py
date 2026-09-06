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

    ESTADO_ABIERTO = "abierto"
    ESTADO_RESUELTO = "resuelto"
    ESTADO_CHOICES = [
        (ESTADO_ABIERTO, _("🔵 Abierto")),
        (ESTADO_RESUELTO, _("🟢 Resuelto")),
    ]

    nombre_reportante = models.CharField(_("Nombre del reportante"), max_length=120)
    asunto = models.CharField(_("Asunto"), max_length=200)
    descripcion = models.TextField(_("Descripción"))

    estado = models.CharField(
        _("Estado"),
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_ABIERTO,
    )
    resuelto_por = models.CharField(_("Resuelto por"), max_length=120, blank=True)
    resuelto_at = models.DateTimeField(_("Resuelto el"), null=True, blank=True)

    github_issue_number = models.IntegerField(
        _("Número de issue en GitHub"),
        null=True,
        blank=True,
        unique=True,
    )
    github_url = models.URLField(_("URL del issue en GitHub"), blank=True)
    sincronizado_github = models.BooleanField(_("Sincronizado con GitHub"), default=False)
    error_sincronizacion = models.TextField(_("Error de sincronización"), blank=True)

    # Issue #71 ronda 4: el reportante ya tenía fecha/hora automática desde
    # v1.0 (`created_at`, abajo). La IP nunca se capturaba — la auditoría del
    # revisor (2026-08-01) pidió confirmarlo/asegurarlo. Se puebla en
    # `nuevo_view` best-effort (nunca bloquea la creación del ticket).
    ip_reportante = models.GenericIPAddressField(_("IP del reportante"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Ticket de feedback")
        verbose_name_plural = _("Tickets de feedback")

    def __str__(self):
        return self.asunto

    @property
    def esta_resuelto(self):
        return self.estado == self.ESTADO_RESUELTO


class FeedbackAttachment(models.Model):
    """
    Adjunto de un `FeedbackTicket`, subido desde el portal público.

    Desde el issue #71 ronda 2 acepta **imagen, audio y video** (el cliente
    pidió poder grabar audio/video desde el portal), no solo imágenes. Por
    eso el campo es un `FileField` genérico (`archivo`) + `tipo`/`mime_type`
    derivados del MIME, en vez del `ImageField` de v1.0: un `ImageField`
    rechaza cualquier cosa que Pillow no pueda abrir.

    NOTA (ver services.py): al crearse fuera de un ModelForm, este modelo NO
    ejecuta `full_clean()` automáticamente — la validación real (prefijo MIME
    permitido, tamaño, y para imágenes `PIL.verify()`) vive en la capa de
    servicio, no depende de los validadores nativos del field.
    """

    TIPO_IMAGEN = "imagen"
    TIPO_AUDIO = "audio"
    TIPO_VIDEO = "video"
    TIPO_CHOICES = [
        (TIPO_IMAGEN, _("🖼 Imagen")),
        (TIPO_AUDIO, _("🔊 Audio")),
        (TIPO_VIDEO, _("🎬 Video")),
    ]

    ticket = models.ForeignKey(
        FeedbackTicket,
        on_delete=models.CASCADE,
        related_name="adjuntos",
        verbose_name=_("Ticket"),
    )
    archivo = models.FileField(_("Archivo"), upload_to="feedback/adjuntos/%Y/%m/")
    tipo = models.CharField(_("Tipo"), max_length=10, choices=TIPO_CHOICES, default=TIPO_IMAGEN)
    mime_type = models.CharField(_("MIME type"), max_length=120, blank=True)
    nombre_original = models.CharField(_("Nombre original del archivo"), max_length=255, blank=True)
    transcripcion_ia = models.TextField(
        _("Transcripción IA"),
        blank=True,
        default="",
        help_text=_(
            "Texto generado por Gemini (apps.feedback.gemini_client) a partir "
            "del contenido del adjunto — issue #71 ronda 3. Vacío si "
            "GEMINI_API_KEY no está configurado o la transcripción falló "
            "(best-effort, nunca bloquea la creación del ticket)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Adjunto de feedback")
        verbose_name_plural = _("Adjuntos de feedback")

    def __str__(self):
        return self.nombre_original or f"Adjunto #{self.pk} de ticket #{self.ticket_id}"

    @staticmethod
    def inferir_tipo(mime):
        """Deriva `tipo` del MIME type. Default `imagen` (v1.0 solo imágenes)."""
        m = (mime or "").lower()
        if m.startswith("audio/"):
            return FeedbackAttachment.TIPO_AUDIO
        if m.startswith("video/"):
            return FeedbackAttachment.TIPO_VIDEO
        return FeedbackAttachment.TIPO_IMAGEN
