"""
Certification models for SD LMS.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.validators import (
    validate_certificate_template_extension,
    validate_https_url,
    validate_image_extension,
    validate_percentage,
)


class CertificateTemplate(models.Model):
    """
    Template for generating certificates.
    """

    name = models.CharField(_("Nombre"), max_length=200)
    description = models.TextField(_("Descripción"), blank=True)
    template_file = models.FileField(
        _("Archivo de plantilla"),
        upload_to="certificates/templates/",
        help_text=_(
            "Archivo HTML/PDF de la plantilla (opcional -- una plantilla "
            "puede definir solo logo/firma y usar la plantilla HTML por "
            "defecto del sistema, SD#59 A2)"
        ),
        blank=True,
        validators=[validate_certificate_template_extension],
    )
    background_image = models.ImageField(
        _("Imagen de fondo"),
        upload_to="certificates/backgrounds/",
        blank=True,
        null=True,
        validators=[validate_image_extension],
    )
    logo = models.ImageField(
        _("Logo"),
        upload_to="certificates/logos/",
        blank=True,
        null=True,
        validators=[validate_image_extension],
    )
    signature_image = models.ImageField(
        _("Imagen de firma"),
        upload_to="certificates/signatures/",
        blank=True,
        null=True,
        validators=[validate_image_extension],
    )
    signer_name = models.CharField(
        _("Nombre del firmante"),
        max_length=200,
        blank=True,
    )
    signer_title = models.CharField(
        _("Cargo del firmante"),
        max_length=200,
        blank=True,
    )
    is_active = models.BooleanField(_("Activo"), default=True)
    metadata = models.JSONField(_("Metadatos"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "certificate_templates"
        verbose_name = _("Plantilla de certificado")
        verbose_name_plural = _("Plantillas de certificado")

    def __str__(self):
        return self.name


class Certificate(models.Model):
    """
    Issued certificate for a user.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        ISSUED = "issued", _("Emitido")
        REVOKED = "revoked", _("Revocado")
        EXPIRED = "expired", _("Vencido")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="certificates",
        verbose_name=_("Usuario"),
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="certificates",
        verbose_name=_("Curso"),
    )
    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name="certificates",
        verbose_name=_("Plantilla"),
    )
    certificate_number = models.CharField(
        _("Número de certificado"),
        max_length=50,
        unique=True,
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    score = models.DecimalField(
        _("Puntaje (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[validate_percentage],
    )
    certificate_file = models.FileField(
        _("Archivo de certificado"),
        upload_to="certificates/issued/",
        blank=True,
        null=True,
    )
    issued_at = models.DateTimeField(_("Fecha de emisión"), null=True, blank=True)
    expires_at = models.DateTimeField(_("Fecha de vencimiento"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("Fecha de revocación"), null=True, blank=True)
    revoked_reason = models.TextField(_("Motivo de revocación"), blank=True)
    verification_url = models.URLField(
        _("URL de verificación"),
        blank=True,
        validators=[validate_https_url],
    )
    qr_code = models.ImageField(
        _("Código QR"),
        upload_to="certificates/qr/",
        blank=True,
        null=True,
    )
    metadata = models.JSONField(_("Metadatos"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "certificates"
        verbose_name = _("Certificado")
        verbose_name_plural = _("Certificados")
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.certificate_number} - {self.user}"


class CertificateVerification(models.Model):
    """
    Log of certificate verification attempts.
    """

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="verifications",
        verbose_name=_("Certificado"),
    )
    verified_at = models.DateTimeField(_("Fecha de verificación"), auto_now_add=True)
    ip_address = models.GenericIPAddressField(_("Dirección IP"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    is_valid = models.BooleanField(_("Válido"), default=True)

    class Meta:
        db_table = "certificate_verifications"
        verbose_name = _("Verificación de certificado")
        verbose_name_plural = _("Verificaciones de certificado")
        ordering = ["-verified_at"]

    def __str__(self):
        return f"{self.certificate} - {self.verified_at}"
