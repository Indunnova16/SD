"""
Reusable validators for SD LMS.

This module provides custom validators for model fields across the application.
"""

import os
import re

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    URLValidator,
)
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

# =============================================================================
# Percentage Validators
# =============================================================================


def validate_percentage(value):
    """
    Validate that a value is between 0 and 100 (inclusive).

    Usage:
        passing_score = models.PositiveIntegerField(validators=[validate_percentage])
    """
    if value < 0 or value > 100:
        raise ValidationError(
            _("%(value)s no es un porcentaje válido. Debe estar entre 0 y 100."),
            params={"value": value},
            code="invalid_percentage",
        )


# Validators for percentage fields (reusable instances)
percentage_min_validator = MinValueValidator(0, message=_("El valor debe ser mayor o igual a 0."))
percentage_max_validator = MaxValueValidator(
    100, message=_("El valor debe ser menor o igual a 100.")
)


# =============================================================================
# Duration Validators
# =============================================================================

positive_duration_validator = MinValueValidator(
    0, message=_("La duración debe ser mayor o igual a 0.")
)


def validate_positive_duration(value):
    """
    Validate that duration is non-negative.

    Usage:
        duration = models.PositiveIntegerField(validators=[validate_positive_duration])
    """
    if value < 0:
        raise ValidationError(
            _("La duración debe ser un valor positivo."),
            code="invalid_duration",
        )


# =============================================================================
# Date Range Validators
# =============================================================================


def validate_date_range(start_date, end_date, field_names=("start_date", "end_date")):
    """
    Validate that start_date is before end_date.

    This is a helper function to be used in model clean() methods.

    Usage in model:
        def clean(self):
            super().clean()
            validate_date_range(self.start_date, self.end_date)
    """
    if start_date and end_date and end_date < start_date:
        raise ValidationError(
            {field_names[1]: _("La fecha de fin debe ser posterior a la fecha de inicio.")}
        )


class DateRangeValidator:
    """
    Mixin class for models with start_date and end_date fields.

    Add this to your model and call super().clean() in your clean method.

    Usage:
        class MyModel(DateRangeValidator, models.Model):
            start_date = models.DateTimeField()
            end_date = models.DateTimeField()

            def clean(self):
                super().clean()
    """

    start_date_field = "start_date"
    end_date_field = "end_date"

    def clean(self):
        super().clean()
        start = getattr(self, self.start_date_field, None)
        end = getattr(self, self.end_date_field, None)

        if start and end and end < start:
            raise ValidationError(
                {self.end_date_field: _("La fecha de fin debe ser posterior a la fecha de inicio.")}
            )


# =============================================================================
# JSON Schema Validators
# =============================================================================


@deconstructible
class JSONSchemaValidator:
    """
    Validator for JSON fields that checks against a schema definition.

    Supports basic type checking and required field validation.

    Usage:
        profile_schema = {
            "type": "list",
            "items": {"type": "string"}
        }
        target_profiles = models.JSONField(validators=[JSONSchemaValidator(profile_schema)])
    """

    def __init__(self, schema, message=None):
        self.schema = schema
        self.message = message or _("El formato JSON no es válido.")

    def __call__(self, value):
        try:
            self._validate(value, self.schema)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                self.message,
                code="invalid_json_schema",
            ) from e

    def _validate(self, value, schema):
        """Validate value against schema."""
        expected_type = schema.get("type")

        if expected_type == "list":
            if not isinstance(value, list):
                raise ValidationError(
                    _("Se esperaba una lista."),
                    code="invalid_type",
                )
            items_schema = schema.get("items")
            if items_schema:
                for i, item in enumerate(value):
                    try:
                        self._validate(item, items_schema)
                    except ValidationError as e:
                        raise ValidationError(
                            _("Error en el elemento %(index)s: %(error)s"),
                            params={"index": i, "error": str(e.message)},
                            code="invalid_item",
                        ) from e

        elif expected_type == "dict" or expected_type == "object":
            if not isinstance(value, dict):
                raise ValidationError(
                    _("Se esperaba un diccionario/objeto."),
                    code="invalid_type",
                )

            # Check required fields
            required = schema.get("required", [])
            for field in required:
                if field not in value:
                    raise ValidationError(
                        _("El campo '%(field)s' es requerido."),
                        params={"field": field},
                        code="missing_field",
                    )

            # Check properties
            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                if key in value:
                    try:
                        self._validate(value[key], prop_schema)
                    except ValidationError as e:
                        raise ValidationError(
                            _("Error en '%(key)s': %(error)s"),
                            params={"key": key, "error": str(e.message)},
                            code="invalid_property",
                        ) from e

        elif expected_type == "string":
            if not isinstance(value, str):
                raise ValidationError(
                    _("Se esperaba un texto/string."),
                    code="invalid_type",
                )

        elif expected_type == "number" or expected_type == "integer":
            if not isinstance(value, int | float):
                raise ValidationError(
                    _("Se esperaba un número."),
                    code="invalid_type",
                )

        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValidationError(
                    _("Se esperaba un booleano."),
                    code="invalid_type",
                )

    def __eq__(self, other):
        return (
            isinstance(other, JSONSchemaValidator)
            and self.schema == other.schema
            and self.message == other.message
        )


# Predefined JSON schemas for common use cases

# Schema for target_profiles field (list of strings)
TARGET_PROFILES_SCHEMA = {"type": "list", "items": {"type": "string"}}

# Schema for assessment settings
ASSESSMENT_SETTINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "show_timer": {"type": "boolean"},
        "allow_review": {"type": "boolean"},
        "randomize_questions": {"type": "boolean"},
        "randomize_answers": {"type": "boolean"},
        "show_feedback": {"type": "boolean"},
        "pass_percentage": {"type": "number"},
    },
}

# Schema for notification metadata
NOTIFICATION_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "course_id": {"type": "number"},
        "lesson_id": {"type": "number"},
        "assessment_id": {"type": "number"},
        "certificate_id": {"type": "number"},
    },
}

# Validator instances for direct use
validate_target_profiles = JSONSchemaValidator(
    TARGET_PROFILES_SCHEMA, message=_("target_profiles debe ser una lista de strings.")
)

validate_assessment_settings = JSONSchemaValidator(
    ASSESSMENT_SETTINGS_SCHEMA, message=_("settings debe ser un objeto con la estructura correcta.")
)

validate_notification_metadata = JSONSchemaValidator(
    NOTIFICATION_METADATA_SCHEMA,
    message=_("metadata debe ser un objeto con la estructura correcta."),
)


# =============================================================================
# File Extension Validators
# =============================================================================


@deconstructible
class FileExtensionValidator:
    """
    Validator that checks file extension against allowed extensions.

    Usage:
        allowed = ['pdf', 'doc', 'docx']
        content_file = models.FileField(validators=[FileExtensionValidator(allowed)])
    """

    def __init__(self, allowed_extensions, message=None):
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in allowed_extensions]
        self.message = message

    def __call__(self, value):
        if not value:
            return

        ext = os.path.splitext(value.name)[1].lower().lstrip(".")

        if ext not in self.allowed_extensions:
            raise ValidationError(
                self.message
                or _("Extensión de archivo no permitida. Extensiones válidas: %(allowed)s"),
                params={"allowed": ", ".join(self.allowed_extensions)},
                code="invalid_extension",
            )

    def __eq__(self, other):
        return isinstance(other, FileExtensionValidator) and set(self.allowed_extensions) == set(
            other.allowed_extensions
        )


# Predefined file extension validators

# Document extensions
DOCUMENT_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"]
validate_document_extension = FileExtensionValidator(
    DOCUMENT_EXTENSIONS, message=_("Solo se permiten documentos: %(allowed)s")
)

# Image extensions
IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp", "svg"]
validate_image_extension = FileExtensionValidator(
    IMAGE_EXTENSIONS, message=_("Solo se permiten imágenes: %(allowed)s")
)

# Video extensions
VIDEO_EXTENSIONS = ["mp4", "webm", "mov", "avi", "mkv"]
validate_video_extension = FileExtensionValidator(
    VIDEO_EXTENSIONS, message=_("Solo se permiten videos: %(allowed)s")
)

# Audio extensions
AUDIO_EXTENSIONS = ["mp3", "wav", "ogg", "m4a", "aac"]
validate_audio_extension = FileExtensionValidator(
    AUDIO_EXTENSIONS, message=_("Solo se permiten archivos de audio: %(allowed)s")
)

# SCORM package extensions
SCORM_EXTENSIONS = ["zip"]
validate_scorm_extension = FileExtensionValidator(
    SCORM_EXTENSIONS, message=_("Los paquetes SCORM deben ser archivos ZIP.")
)

# Certificate template extensions
CERTIFICATE_TEMPLATE_EXTENSIONS = ["html", "htm", "pdf"]
validate_certificate_template_extension = FileExtensionValidator(
    CERTIFICATE_TEMPLATE_EXTENSIONS,
    message=_("Las plantillas de certificado deben ser HTML o PDF."),
)

# Course content extensions (all media types)
CONTENT_EXTENSIONS = (
    DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS + SCORM_EXTENSIONS
)
validate_content_extension = FileExtensionValidator(
    CONTENT_EXTENSIONS, message=_("Tipo de archivo no permitido.")
)


# =============================================================================
# URL Validators
# =============================================================================


@deconstructible
class SafeURLValidator(URLValidator):
    """
    Extended URL validator that also checks for safe schemes.

    By default, only allows https URLs. Can be configured to allow http as well.

    Usage:
        video_url = models.URLField(validators=[SafeURLValidator()])
    """

    def __init__(self, schemes=None, allow_http=False, **kwargs):
        if schemes is None:
            schemes = ["https"]
            if allow_http:
                schemes.append("http")
        super().__init__(schemes=schemes, **kwargs)
        self.allow_http = allow_http

    def __eq__(self, other):
        return isinstance(other, SafeURLValidator) and self.schemes == other.schemes


# Validator instances
validate_https_url = SafeURLValidator(schemes=["https"], message=_("La URL debe usar HTTPS."))

validate_url = SafeURLValidator(allow_http=True, message=_("Ingrese una URL válida."))


# =============================================================================
# Hex Color Validator
# =============================================================================


@deconstructible
class HexColorValidator:
    """
    Validator for hexadecimal color values.

    Usage:
        color = models.CharField(validators=[HexColorValidator()])
    """

    regex = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
    message = _("Ingrese un color hexadecimal válido (ej: #3B82F6).")
    code = "invalid_hex_color"

    def __call__(self, value):
        if not self.regex.match(value):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other):
        return isinstance(other, HexColorValidator)


validate_hex_color = HexColorValidator()


# =============================================================================
# Slug Validator (enhanced)
# =============================================================================


@deconstructible
class EnhancedSlugValidator:
    """
    Enhanced slug validator that checks for minimum length and pattern.

    Usage:
        slug = models.SlugField(validators=[EnhancedSlugValidator(min_length=3)])
    """

    regex = re.compile(r"^[-a-zA-Z0-9_]+$")

    def __init__(self, min_length=1, max_length=None, message=None):
        self.min_length = min_length
        self.max_length = max_length
        self.message = message

    def __call__(self, value):
        if len(value) < self.min_length:
            raise ValidationError(
                self.message or _("El slug debe tener al menos %(min_length)s caracteres."),
                params={"min_length": self.min_length},
                code="slug_too_short",
            )

        if self.max_length and len(value) > self.max_length:
            raise ValidationError(
                self.message or _("El slug no puede tener más de %(max_length)s caracteres."),
                params={"max_length": self.max_length},
                code="slug_too_long",
            )

        if not self.regex.match(value):
            raise ValidationError(
                self.message
                or _("El slug solo puede contener letras, números, guiones y guiones bajos."),
                code="invalid_slug",
            )

    def __eq__(self, other):
        return (
            isinstance(other, EnhancedSlugValidator)
            and self.min_length == other.min_length
            and self.max_length == other.max_length
        )


# =============================================================================
# Certificate Number Validator
# =============================================================================


@deconstructible
class CertificateNumberValidator:
    """
    Validator for certificate numbers format.

    Expected format: CERT-YYYYMMDD-XXXXX (e.g., CERT-20240115-00001)

    Usage:
        certificate_number = models.CharField(validators=[CertificateNumberValidator()])
    """

    regex = re.compile(r"^CERT-\d{8}-\d{5}$")
    message = _("El número de certificado debe tener el formato CERT-YYYYMMDD-XXXXX")
    code = "invalid_certificate_number"

    def __call__(self, value):
        if not self.regex.match(value):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other):
        return isinstance(other, CertificateNumberValidator)


validate_certificate_number = CertificateNumberValidator()
