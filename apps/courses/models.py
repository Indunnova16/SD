"""
Course and content models for SD LMS.
"""

import re
from urllib.parse import parse_qs, urlparse

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.validators import (
    validate_content_extension,
    validate_hex_color,
    validate_percentage,
    validate_scorm_extension,
    validate_target_profiles,
    validate_url,
)


def convert_youtube_url_to_embed(url: str, use_nocookie: bool = False) -> str:
    """Convierte URLs de YouTube normales a URLs de embed.

    Args:
        url: URL de YouTube
        use_nocookie: Si True, usa youtube-nocookie.com (útil para videos age-restricted)

    Returns:
        URL de embed funcional
    """
    if not url:
        return url

    # Patrones de URLs de YouTube
    patterns = [
        # youtube.com/watch?v=xxxxx
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        # youtu.be/xxxxx
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        # youtube.com/embed/xxxxx (ya es URL de embed)
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        # youtube-nocookie.com/embed/xxxxx
        r"youtube-nocookie\.com/embed/([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            if use_nocookie:
                return f"https://www.youtube-nocookie.com/embed/{video_id}?modestbranding=1"
            return f"https://www.youtube.com/embed/{video_id}"

    return url


class JobProfileType(models.Model):
    """
    Dynamic job profile types for course targeting.
    Replaces hardcoded choices for target_profiles in course forms.
    """

    code = models.CharField(
        _("Codigo"),
        max_length=50,
        unique=True,
        help_text=_("Identificador unico (ej: LINIERO, TECNICO)"),
    )
    name = models.CharField(_("Nombre"), max_length=100)
    description = models.TextField(_("Descripcion"), blank=True)
    is_active = models.BooleanField(_("Activo"), default=True)
    order = models.PositiveIntegerField(_("Orden"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_profile_types"
        verbose_name = _("Tipo de Perfil Ocupacional")
        verbose_name_plural = _("Tipos de Perfiles Ocupacionales")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class CourseManager(models.Manager):
    """Custom manager for Course model."""

    def published(self):
        return self.filter(status="published")

    def draft(self):
        return self.filter(status="draft")

    def for_profile(self, profile):
        return self.filter(target_profiles__contains=[profile])

    def with_modules(self):
        return self.prefetch_related("modules__lessons")


class EnrollmentManager(models.Manager):
    """Custom manager for Enrollment model."""

    def active(self):
        return self.filter(status__in=["enrolled", "in_progress"])

    def completed(self):
        return self.filter(status="completed")

    def for_user(self, user):
        return self.filter(user=user)

    def for_course(self, course):
        return self.filter(course=course)


class Category(models.Model):
    """
    Category for organizing courses by theme/topic.
    """

    name = models.CharField(_("Nombre"), max_length=100)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    description = models.TextField(_("Descripción"), blank=True)
    icon = models.CharField(
        _("Ícono"),
        max_length=50,
        blank=True,
        help_text=_("Clase de ícono CSS (ej: heroicons)"),
    )
    color = models.CharField(
        _("Color"),
        max_length=7,
        default="#3B82F6",
        help_text=_("Color en formato hexadecimal"),
        validators=[validate_hex_color],
    )
    order = models.PositiveIntegerField(_("Orden"), default=0)
    is_active = models.BooleanField(_("Activa"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "course_categories"
        verbose_name = _("Categoría")
        verbose_name_plural = _("Categorías")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @property
    def full_path(self):
        """Get full category path."""
        return self.name


class Course(models.Model):
    """
    Course model representing a training course.
    """

    class Type(models.TextChoices):
        MANDATORY = "mandatory", _("Obligatorio")
        OPTIONAL = "optional", _("Opcional")
        REFRESHER = "refresher", _("Refuerzo")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        PUBLISHED = "published", _("Publicado")
        ARCHIVED = "archived", _("Archivado")

    class Country(models.TextChoices):
        COLOMBIA = "CO", _("Colombia")
        PANAMA = "PA", _("Panamá")
        PERU = "PE", _("Perú")

    class ActivityType(models.TextChoices):
        CHARLA = "charla", _("Charla")
        CAPACITACION = "capacitacion", _("Capacitación")
        SIMULACRO = "simulacro", _("Simulacro")
        SOCIALIZACION = "socializacion", _("Socialización")
        OTRA = "otra", _("Otra")

    code = models.CharField(_("Código"), max_length=50, unique=True)
    title = models.CharField(_("Título"), max_length=200)
    description = models.TextField(_("Descripción"))
    objectives = models.TextField(_("Objetivos"), blank=True)
    # duration is now calculated as total_duration property (sum of lesson durations)
    course_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=Type.choices,
        default=Type.MANDATORY,
    )
    thumbnail = models.ImageField(
        _("Imagen miniatura"),
        upload_to="courses/thumbnails/",
        blank=True,
        null=True,
    )
    banner_image = models.ImageField(
        _("Imagen de portada"),
        upload_to="courses/banners/",
        blank=True,
        null=True,
        help_text=_("Imagen grande que se muestra en el encabezado del curso"),
    )
    theme_color = models.CharField(
        _("Color del tema"),
        max_length=7,
        blank=True,
        default="",
        help_text=_("Color hexadecimal del tema del curso (ej: #3B82F6)"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    version = models.PositiveIntegerField(_("Versión"), default=1)
    target_profiles = models.JSONField(
        verbose_name=_("Perfiles objetivo"),
        help_text=_("Lista de perfiles ocupacionales para este curso"),
        default=list,
        validators=[validate_target_profiles],
    )
    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="required_for",
        verbose_name=_("Prerrequisitos"),
    )
    validity_months = models.PositiveIntegerField(
        _("Validez (meses)"),
        null=True,
        blank=True,
        help_text=_("Meses de validez de la certificación (null = sin vencimiento)"),
    )
    country = models.CharField(
        _("País"),
        max_length=2,
        choices=Country.choices,
        default=Country.COLOMBIA,
        help_text=_("País donde aplica este curso"),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
        verbose_name=_("Categoría"),
    )
    # SD#63: campos para el reporte de asistencia por curso (formato
    # FT-HSEQ-60). blank=True (y null=True para instructor, FK) para no
    # romper los cursos reales ya existentes al migrar -- ninguno de los 3
    # es obligatorio a nivel de modelo, el gate de A5 los exige solo al
    # intentar exportar el PDF.
    project_name = models.CharField(
        _("Proyecto"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("Proyecto/obra al que pertenece la actividad (formato FT-HSEQ-60)"),
    )
    activity_type = models.CharField(
        _("Tipo de actividad"),
        max_length=20,
        choices=ActivityType.choices,
        blank=True,
        default="",
    )
    instructor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses_as_instructor",
        verbose_name=_("Instructor"),
        help_text=_("Instructor responsable de la actividad (firma en el reporte de asistencia)"),
    )
    contracts = models.ManyToManyField(
        "accounts.Contract",
        blank=True,
        related_name="courses",
        verbose_name=_("Contratos aplicables"),
        help_text=_("Contratos donde aplica este curso"),
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="courses_created",
        verbose_name=_("Creado por"),
    )
    published_at = models.DateTimeField(_("Fecha de publicación"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CourseManager()

    class Meta:
        db_table = "courses"
        verbose_name = _("Curso")
        verbose_name_plural = _("Cursos")
        ordering = ["title"]

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def total_duration(self):
        """Calculate total duration including all lessons."""
        from django.db.models import Sum

        result = self.modules.aggregate(total=Sum("lessons__duration"))
        return result["total"] or 0

    @property
    def duration_hours(self):
        """Total course duration in hours (rounded to 1 decimal).

        `total_duration` (Lesson.duration, PositiveIntegerField) is stored in
        MINUTES, not seconds: confirmed by the "min" labels rendered in
        templates/courses/course_list.html:115 and course_detail.html:22/166,
        the lesson form's "Minutos" placeholder (apps/courses/forms.py:352),
        and templates/courses/lesson_view.html:483
        (`{{ lesson.duration }} * 60 // Convert minutes to seconds`). This is
        the value certificate templates should use (SD#43: the template
        previously referenced `course.estimated_duration`, an attribute
        removed from this model, which silently rendered blank).
        """
        return round(self.total_duration / 60, 1)


class Module(models.Model):
    """
    Course module containing lessons.
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="modules",
        verbose_name=_("Curso"),
    )
    title = models.CharField(_("Título"), max_length=200)
    description = models.TextField(_("Descripción"), blank=True)
    cover_image = models.ImageField(
        _("Imagen de portada"),
        upload_to="courses/modules/",
        blank=True,
        null=True,
        help_text=_("Imagen que se muestra al inicio del módulo"),
    )
    order = models.PositiveIntegerField(_("Orden"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "modules"
        verbose_name = _("Módulo")
        verbose_name_plural = _("Módulos")
        ordering = ["order"]
        unique_together = ["course", "order"]
        indexes = [
            models.Index(fields=["course", "order"]),
        ]

    def __str__(self):
        return f"{self.course.code} - {self.title}"

    @property
    def duration_hours(self):
        """Module duration in hours (rounded to 1 decimal), analogous to
        Course.duration_hours (SD#62 A3). `Lesson.duration` is stored in
        minutes."""
        from django.db.models import Sum

        result = self.lessons.aggregate(total=Sum("duration"))
        total_minutes = result["total"] or 0
        return round(total_minutes / 60, 1)


class Lesson(models.Model):
    """
    Individual lesson within a module.
    """

    class Type(models.TextChoices):
        VIDEO = "video", _("Video")
        PDF = "pdf", _("PDF")
        SCORM = "scorm", _("SCORM")
        INTERACTIVE = "interactive", _("Interactivo")
        AUDIO = "audio", _("Audio")
        QUIZ = "quiz", _("Evaluación")
        TEXT = "text", _("Texto")
        PRESENTIAL = "presential", _("Presencial")
        ATTENDANCE = "attendance", _("Asistencia")

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name=_("Módulo"),
    )
    title = models.CharField(_("Título"), max_length=200)
    description = models.TextField(_("Descripción"), blank=True)
    lesson_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=Type.choices,
    )
    content = models.TextField(_("Contenido"), blank=True, help_text=_("Contenido HTML o texto"))
    content_file = models.FileField(
        _("Archivo de contenido"),
        upload_to="courses/content/",
        blank=True,
        null=True,
        validators=[validate_content_extension],
    )
    video_url = models.URLField(_("URL del video"), blank=True, validators=[validate_url])
    duration = models.PositiveIntegerField(
        _("Duración (minutos)"),
        default=0,
        validators=[MinValueValidator(0)],
    )
    order = models.PositiveIntegerField(_("Orden"), default=0)
    is_mandatory = models.BooleanField(_("Obligatorio"), default=True)
    is_offline_available = models.BooleanField(_("Disponible offline"), default=True)
    is_presential = models.BooleanField(
        _("Presencial"),
        default=False,
        help_text=_("Si la lección requiere asistencia presencial"),
    )
    scheduled_date = models.DateTimeField(
        _("Fecha y hora agendada"),
        null=True,
        blank=True,
        help_text=_("Solo para lecciones de Asistencia"),
    )
    metadata = models.JSONField(_("Metadatos"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lessons"
        verbose_name = _("Lección")
        verbose_name_plural = _("Lecciones")
        ordering = ["order"]
        indexes = [
            models.Index(fields=["module", "order"]),
        ]

    def save(self, *args, **kwargs):
        if self.video_url and self.lesson_type == "video":
            self.video_url = convert_youtube_url_to_embed(self.video_url)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.module.title} - {self.title}"


class MediaAsset(models.Model):
    """
    Media files used in courses.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        PROCESSING = "processing", _("Procesando")
        READY = "ready", _("Listo")
        ERROR = "error", _("Error")

    class Type(models.TextChoices):
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        IMAGE = "image", _("Imagen")
        DOCUMENT = "document", _("Documento")
        SCORM = "scorm", _("Paquete SCORM")

    filename = models.CharField(_("Nombre de archivo"), max_length=255)
    original_name = models.CharField(_("Nombre original"), max_length=255)
    file = models.FileField(_("Archivo"), upload_to="media_assets/")
    file_type = models.CharField(_("Tipo"), max_length=20, choices=Type.choices)
    mime_type = models.CharField(_("MIME type"), max_length=100)
    size = models.PositiveBigIntegerField(_("Tamaño (bytes)"))
    thumbnail = models.ImageField(
        _("Miniatura"),
        upload_to="media_assets/thumbnails/",
        blank=True,
        null=True,
    )
    compressed_file = models.FileField(
        _("Archivo comprimido (offline)"),
        upload_to="media_assets/offline/",
        blank=True,
        null=True,
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    processing_error = models.TextField(_("Error de procesamiento"), blank=True)
    duration = models.PositiveIntegerField(_("Duración (segundos)"), null=True, blank=True)
    metadata = models.JSONField(_("Metadatos"), default=dict, blank=True)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_assets",
        verbose_name=_("Subido por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "media_assets"
        verbose_name = _("Recurso multimedia")
        verbose_name_plural = _("Recursos multimedia")
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


class CourseVersion(models.Model):
    """
    Versioned snapshot of a course for auditing and rollback.
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Curso"),
    )
    version_number = models.PositiveIntegerField(_("Número de versión"))
    snapshot = models.JSONField(
        _("Snapshot"),
        help_text=_("Complete course data snapshot"),
    )
    changelog = models.TextField(_("Cambios"), blank=True)
    is_major_version = models.BooleanField(_("Versión mayor"), default=False)
    published_at = models.DateTimeField(_("Fecha de publicación"), null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="course_versions_created",
        verbose_name=_("Creado por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "course_versions"
        verbose_name = _("Versión de curso")
        verbose_name_plural = _("Versiones de curso")
        ordering = ["-version_number"]
        unique_together = ["course", "version_number"]

    def __str__(self):
        return f"{self.course.code} v{self.version_number}"

    @classmethod
    def create_snapshot(cls, course, user, changelog="", is_major=False):
        """Create a new version snapshot of the course."""
        # Get the latest version number
        latest = cls.objects.filter(course=course).order_by("-version_number").first()
        new_version = (latest.version_number + 1) if latest else 1

        # Create snapshot data
        snapshot = {
            "title": course.title,
            "description": course.description,
            "objectives": course.objectives,
            "duration": course.total_duration,
            "course_type": course.course_type,
            "target_profiles": course.target_profiles,
            "validity_months": course.validity_months,
            "modules": [],
        }

        for module in course.modules.all():
            module_data = {
                "id": module.id,
                "title": module.title,
                "description": module.description,
                "order": module.order,
                "lessons": [],
            }
            for lesson in module.lessons.all():
                module_data["lessons"].append(
                    {
                        "id": lesson.id,
                        "title": lesson.title,
                        "description": lesson.description,
                        "lesson_type": lesson.lesson_type,
                        "duration": lesson.duration,
                        "order": lesson.order,
                        "is_mandatory": lesson.is_mandatory,
                    }
                )
            snapshot["modules"].append(module_data)

        return cls.objects.create(
            course=course,
            version_number=new_version,
            snapshot=snapshot,
            changelog=changelog,
            is_major_version=is_major,
            created_by=user,
        )


class ScormPackage(models.Model):
    """
    SCORM package for e-learning content.
    """

    class Version(models.TextChoices):
        SCORM_12 = "1.2", _("SCORM 1.2")
        SCORM_2004 = "2004", _("SCORM 2004")
        XAPI = "xapi", _("xAPI/TinCan")

    class Status(models.TextChoices):
        UPLOADED = "uploaded", _("Subido")
        EXTRACTING = "extracting", _("Extrayendo")
        VALIDATING = "validating", _("Validando")
        READY = "ready", _("Listo")
        ERROR = "error", _("Error")

    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="scorm_package",
        verbose_name=_("Lección"),
    )
    package_file = models.FileField(
        _("Paquete SCORM"),
        upload_to="scorm_packages/",
        validators=[validate_scorm_extension],
    )
    extracted_path = models.CharField(
        _("Ruta extraída"),
        max_length=500,
        blank=True,
    )
    entry_point = models.CharField(
        _("Punto de entrada"),
        max_length=255,
        blank=True,
        help_text=_("HTML de inicio del paquete"),
    )
    scorm_version = models.CharField(
        _("Versión SCORM"),
        max_length=10,
        choices=Version.choices,
        default=Version.SCORM_12,
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    manifest_data = models.JSONField(
        _("Datos del manifiesto"),
        default=dict,
        blank=True,
    )
    error_message = models.TextField(_("Mensaje de error"), blank=True)
    file_size = models.PositiveBigIntegerField(_("Tamaño (bytes)"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scorm_packages"
        verbose_name = _("Paquete SCORM")
        verbose_name_plural = _("Paquetes SCORM")

    def __str__(self):
        return f"SCORM: {self.lesson.title}"

    @property
    def launch_url(self):
        """Get the URL to launch the SCORM content."""
        if self.entry_point and self.extracted_path:
            return f"/media/{self.extracted_path}/{self.entry_point}"
        return None


class ScormAttempt(models.Model):
    """
    Track SCORM interactions and progress.
    """

    class Status(models.TextChoices):
        NOT_ATTEMPTED = "not attempted", _("No iniciado")
        INCOMPLETE = "incomplete", _("Incompleto")
        COMPLETED = "completed", _("Completado")
        PASSED = "passed", _("Aprobado")
        FAILED = "failed", _("Reprobado")

    enrollment = models.ForeignKey(
        "Enrollment",
        on_delete=models.CASCADE,
        related_name="scorm_attempts",
        verbose_name=_("Inscripción"),
    )
    scorm_package = models.ForeignKey(
        ScormPackage,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name=_("Paquete SCORM"),
    )
    attempt_number = models.PositiveIntegerField(_("Número de intento"), default=1)
    lesson_status = models.CharField(
        _("Estado de lección"),
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_ATTEMPTED,
    )
    score_raw = models.DecimalField(
        _("Puntuación"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    score_min = models.DecimalField(
        _("Puntuación mínima"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    score_max = models.DecimalField(
        _("Puntuación máxima"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    session_time = models.DurationField(
        _("Tiempo de sesión"),
        null=True,
        blank=True,
    )
    total_time = models.DurationField(
        _("Tiempo total"),
        null=True,
        blank=True,
    )
    suspend_data = models.TextField(
        _("Datos de suspensión"),
        blank=True,
        help_text=_("Datos para continuar la sesión"),
    )
    location = models.CharField(
        _("Ubicación"),
        max_length=255,
        blank=True,
        help_text=_("Última ubicación en el contenido"),
    )
    interactions = models.JSONField(
        _("Interacciones"),
        default=list,
        blank=True,
    )
    cmi_data = models.JSONField(
        _("Datos CMI"),
        default=dict,
        blank=True,
        help_text=_("Todos los datos CMI del intento"),
    )
    started_at = models.DateTimeField(_("Inicio"), auto_now_add=True)
    last_accessed_at = models.DateTimeField(_("Último acceso"), auto_now=True)
    completed_at = models.DateTimeField(_("Completado"), null=True, blank=True)

    class Meta:
        db_table = "scorm_attempts"
        verbose_name = _("Intento SCORM")
        verbose_name_plural = _("Intentos SCORM")
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.enrollment.user} - {self.scorm_package.lesson.title} (Intento {self.attempt_number})"


class ResourceLibrary(models.Model):
    """
    Shared resource library for reusable content.
    """

    class Type(models.TextChoices):
        IMAGE = "image", _("Imagen")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        DOCUMENT = "document", _("Documento")
        TEMPLATE = "template", _("Plantilla")
        INFOGRAPHIC = "infographic", _("Infografía")

    name = models.CharField(_("Nombre"), max_length=200)
    description = models.TextField(_("Descripción"), blank=True)
    resource_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=Type.choices,
    )
    file = models.FileField(_("Archivo"), upload_to="resource_library/")
    thumbnail = models.ImageField(
        _("Miniatura"),
        upload_to="resource_library/thumbnails/",
        blank=True,
        null=True,
    )
    file_size = models.PositiveBigIntegerField(_("Tamaño (bytes)"), default=0)
    mime_type = models.CharField(_("MIME type"), max_length=100, blank=True)
    tags = models.JSONField(
        verbose_name=_("Etiquetas"),
        default=list,
        blank=True,
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources",
        verbose_name=_("Categoría"),
    )
    usage_count = models.PositiveIntegerField(_("Veces usado"), default=0)
    is_public = models.BooleanField(_("Público"), default=True)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="library_resources",
        verbose_name=_("Subido por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_library"
        verbose_name = _("Recurso de biblioteca")
        verbose_name_plural = _("Recursos de biblioteca")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    """
    User enrollment in a course.
    """

    class Status(models.TextChoices):
        ENROLLED = "enrolled", _("Inscrito")
        IN_PROGRESS = "in_progress", _("En progreso")
        COMPLETED = "completed", _("Completado")
        EXPIRED = "expired", _("Vencido")
        DROPPED = "dropped", _("Abandonado")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("Usuario"),
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("Curso"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.ENROLLED,
    )
    progress = models.DecimalField(
        _("Progreso (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[validate_percentage],
    )
    started_at = models.DateTimeField(_("Fecha de inicio"), null=True, blank=True)
    completed_at = models.DateTimeField(_("Fecha de completado"), null=True, blank=True)
    due_date = models.DateField(_("Fecha límite"), null=True, blank=True)
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="enrollments_assigned",
        verbose_name=_("Asignado por"),
    )
    completion_signature = models.ImageField(
        _("Firma de finalización"),
        upload_to="enrollments/signatures/%Y/%m/",
        null=True,
        blank=True,
    )
    completion_signed_at = models.DateTimeField(
        _("Fecha de firma de finalización"),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EnrollmentManager()

    class Meta:
        db_table = "enrollments"
        verbose_name = _("Inscripción")
        verbose_name_plural = _("Inscripciones")
        unique_together = ["user", "course"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["course", "status"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.course}"

    @property
    def days_until_due(self):
        """Return number of days until due_date, or None if no due_date."""
        if not self.due_date:
            return None
        from datetime import date

        return (self.due_date - date.today()).days

    @property
    def is_expiring_soon(self):
        """True if due_date is within 3 days and not completed/expired."""
        days = self.days_until_due
        if days is None:
            return False
        return 0 <= days <= 3 and self.status not in (self.Status.COMPLETED, self.Status.EXPIRED)


class LessonProgress(models.Model):
    """
    Track user progress on individual lessons.
    """

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="lesson_progress",
        verbose_name=_("Inscripción"),
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="user_progress",
        verbose_name=_("Lección"),
    )
    is_completed = models.BooleanField(_("Completado"), default=False)
    progress_percent = models.DecimalField(
        _("Progreso (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[validate_percentage],
    )
    time_spent = models.PositiveIntegerField(
        _("Tiempo empleado (segundos)"),
        default=0,
    )
    last_position = models.JSONField(
        _("Última posición"),
        default=dict,
        blank=True,
        help_text=_("Posición del video/contenido para continuar"),
    )
    completed_at = models.DateTimeField(_("Fecha de completado"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lesson_progress"
        verbose_name = _("Progreso de lección")
        verbose_name_plural = _("Progreso de lecciones")
        unique_together = ["enrollment", "lesson"]
        indexes = [
            models.Index(fields=["enrollment"]),
        ]

    def __str__(self):
        return f"{self.enrollment.user} - {self.lesson}"


class CompletionRecord(models.Model):
    """
    Permanent record of course completions.

    Enrollments can be reset (e.g., when a user is reactivated),
    but this table preserves a permanent audit trail of every
    time a user completed a course.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="completion_records",
        verbose_name=_("Usuario"),
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="completion_records",
        verbose_name=_("Curso"),
    )
    completed_at = models.DateTimeField(_("Fecha de completado"))
    progress = models.DecimalField(
        _("Progreso alcanzado (%)"),
        max_digits=5,
        decimal_places=2,
        default=100,
    )
    reset_reason = models.CharField(
        _("Motivo del reinicio"),
        max_length=100,
        default="Reactivación de usuario",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "completion_records"
        verbose_name = _("Registro de completación")
        verbose_name_plural = _("Registros de completación")
        ordering = ["-completed_at"]
        indexes = [
            models.Index(fields=["user", "course"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.course} ({self.completed_at:%d/%m/%Y})"


class LessonEvidence(models.Model):
    """
    Evidence uploaded for presential lessons (CUR-07).

    Used to record attendance, photos, and other evidence of
    in-person training completion.
    """

    class EvidenceType(models.TextChoices):
        PHOTO = "photo", _("Fotografía")
        ATTENDANCE = "attendance", _("Lista de Asistencia")
        CERTIFICATE = "certificate", _("Certificado")
        OTHER = "other", _("Otro")

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="evidences",
        verbose_name=_("Lección"),
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="lesson_evidences",
        verbose_name=_("Usuario"),
    )
    evidence_type = models.CharField(
        _("Tipo de evidencia"),
        max_length=20,
        choices=EvidenceType.choices,
        default=EvidenceType.PHOTO,
    )
    file = models.FileField(
        _("Archivo"),
        upload_to="lesson_evidences/%Y/%m/",
    )
    description = models.TextField(
        _("Descripción"),
        blank=True,
    )
    verified = models.BooleanField(
        _("Verificado"),
        default=False,
        help_text=_("Si la evidencia ha sido verificada por un supervisor"),
    )
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidences_verified",
        verbose_name=_("Verificado por"),
    )
    verified_at = models.DateTimeField(
        _("Fecha de verificación"),
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    signature = models.ImageField(
        _("Firma"),
        upload_to="lesson_evidences/signatures/%Y/%m/",
        null=True,
        blank=True,
    )
    signed_at = models.DateTimeField(
        _("Fecha de firma"),
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "lesson_evidences"
        verbose_name = _("Evidencia de lección")
        verbose_name_plural = _("Evidencias de lección")
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["lesson", "user"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.lesson.title} ({self.get_evidence_type_display()})"


class AttendanceSignature(models.Model):
    """
    Firma de asistencia para lecciones de tipo "Asistencia".
    """

    class SignatureType(models.TextChoices):
        STUDENT = "student", _("Firma de Estudiante")
        INSTRUCTOR = "instructor", _("Firma del Instructor")

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="attendance_signatures",
        verbose_name=_("Lección"),
        limit_choices_to={"lesson_type": "attendance"},
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="attendance_signatures",
        verbose_name=_("Usuario"),
    )
    signature_image = models.ImageField(
        _("Imagen de firma"),
        upload_to="signatures/%Y/%m/",
    )
    signature_type = models.CharField(
        _("Tipo de firma"),
        max_length=20,
        choices=SignatureType.choices,
        default=SignatureType.STUDENT,
    )
    instructor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instructor_attendances",
        verbose_name=_("Instructor asignado"),
    )
    signed_at = models.DateTimeField(
        _("Fecha y hora de firma"),
        auto_now_add=True,
    )
    ip_address = models.GenericIPAddressField(
        _("Dirección IP"),
        null=True,
        blank=True,
    )
    device_info = models.JSONField(
        _("Información del dispositivo"),
        default=dict,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_signatures"
        verbose_name = _("Firma de Asistencia")
        verbose_name_plural = _("Firmas de Asistencia")
        ordering = ["-signed_at"]
        indexes = [
            models.Index(fields=["lesson", "user"]),
            models.Index(fields=["lesson", "signed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "user"],
                name="unique_attendance_signature",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.lesson.title} ({self.get_signature_type_display()})"
