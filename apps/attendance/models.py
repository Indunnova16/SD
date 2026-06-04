"""
Modelos de asistencia con reconocimiento facial para SD LMS.

Portado desde Indunnova16/Logisticacargues (app `attendance`), retargeteado
al modelo `accounts.User` de SD (el personal operativo ya vive ahí: cédula =
`document_number`, foto de referencia = `User.photo`).

- `AttendanceRecord`: registro diario de entrada/salida por usuario.
- `FaceCheckEvent`: auditoría de cada intento de marcación facial (kiosko móvil).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class AttendanceRecord(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("usuario"),
    )
    date = models.DateField(_("fecha"), db_index=True)
    check_in = models.TimeField(_("entrada"), null=True, blank=True)
    check_out = models.TimeField(_("salida"), null=True, blank=True)
    hours_worked = models.DecimalField(
        _("horas trabajadas"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    is_absent = models.BooleanField(_("ausente"), default=False)
    absence_reason = models.CharField(_("motivo ausencia"), max_length=200, blank=True)
    notes = models.TextField(_("notas"), blank=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_registered",
        verbose_name=_("registrado por"),
    )

    class Meta:
        verbose_name = _("Registro de asistencia")
        verbose_name_plural = _("Registros de asistencia")
        unique_together = ["user", "date"]
        ordering = ["-date", "user"]

    def __str__(self):
        return f"{self.user} - {self.date}"


class FaceCheckEvent(BaseModel):
    KIND_CHECK_IN = "check_in"
    KIND_CHECK_OUT = "check_out"
    KIND_CHOICES = [
        (KIND_CHECK_IN, _("Entrada")),
        (KIND_CHECK_OUT, _("Salida")),
    ]

    STATUS_MATCHED = "matched"
    STATUS_LOW_CONFIDENCE = "low_confidence"
    STATUS_NO_MATCH = "no_match"
    STATUS_NO_FACE = "no_face"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_MATCHED, _("Identificado")),
        (STATUS_LOW_CONFIDENCE, _("Confianza baja")),
        (STATUS_NO_MATCH, _("Sin coincidencia")),
        (STATUS_NO_FACE, _("Sin rostro detectado")),
        (STATUS_ERROR, _("Error del servicio")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_events",
        verbose_name=_("usuario"),
    )
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_events",
        verbose_name=_("registro asistencia"),
    )
    kind = models.CharField(_("tipo"), max_length=10, choices=KIND_CHOICES)
    status = models.CharField(_("estado"), max_length=20, choices=STATUS_CHOICES)
    selfie = models.ImageField(_("selfie"), upload_to="attendance/selfies/%Y/%m/%d/")
    similarity = models.DecimalField(
        _("similitud (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Similaridad con la foto de referencia según Rekognition."),
    )
    aws_face_id = models.CharField(_("AWS face ID detectado"), max_length=64, blank=True)
    latitude = models.DecimalField(
        _("latitud"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitud"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    user_agent = models.CharField(_("user agent"), max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)
    error_message = models.CharField(_("mensaje de error"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Evento de reconocimiento facial")
        verbose_name_plural = _("Eventos de reconocimiento facial")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        who = str(self.user) if self.user else "desconocido"
        return f"{self.get_kind_display()} {who} ({self.get_status_display()})"
