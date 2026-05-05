"""
Learning path models for SD LMS.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class LearningPath(models.Model):
    """
    Learning path defining a sequence of courses.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        ACTIVE = "active", _("Activo")
        ARCHIVED = "archived", _("Archivado")

    class Country(models.TextChoices):
        COLOMBIA = "CO", _("Colombia")
        PANAMA = "PA", _("Panamá")
        PERU = "PE", _("Perú")

    name = models.CharField(_("Nombre"), max_length=200)
    description = models.TextField(_("Descripción"))
    target_profiles = models.JSONField(
        verbose_name=_("Perfiles objetivo"),
        help_text=_("Lista de perfiles ocupacionales para esta ruta"),
        default=list,
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    is_mandatory = models.BooleanField(
        _("Obligatorio"),
        default=False,
        help_text=_("Si es obligatorio para los perfiles objetivo"),
    )
    country = models.CharField(
        _("País"),
        max_length=2,
        choices=Country.choices,
        default=Country.COLOMBIA,
        help_text=_("País donde aplica esta ruta"),
    )
    estimated_duration = models.PositiveIntegerField(
        _("Duración estimada (días)"),
        help_text=_("Tiempo estimado para completar la ruta"),
    )
    thumbnail = models.ImageField(
        _("Imagen"),
        upload_to="learning_paths/",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="learning_paths_created",
        verbose_name=_("Creado por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_paths"
        verbose_name = _("Ruta de aprendizaje")
        verbose_name_plural = _("Rutas de aprendizaje")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def total_courses(self):
        return self.path_courses.count()

    @property
    def total_duration(self):
        """Calculate total duration from all courses (in minutes)."""
        from django.db.models import F, Sum

        result = self.path_courses.aggregate(
            total=Sum(F("course__total_duration"), output_field=models.IntegerField())
        )
        return result["total"] or 0


class PathCourse(models.Model):
    """
    Course within a learning path with order and dependencies.
    """

    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name="path_courses",
        verbose_name=_("Ruta"),
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="path_inclusions",
        verbose_name=_("Curso"),
    )
    order = models.PositiveIntegerField(_("Orden"), default=0)
    is_required = models.BooleanField(_("Requerido"), default=True)
    unlock_after = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unlocks",
        verbose_name=_("Desbloquear después de"),
        help_text=_("Curso que debe completarse antes de desbloquear este"),
    )

    class Meta:
        db_table = "path_courses"
        verbose_name = _("Curso en ruta")
        verbose_name_plural = _("Cursos en ruta")
        ordering = ["order"]
        unique_together = [["learning_path", "course"]]

    def __str__(self):
        return f"{self.learning_path.name} - {self.course.title}"


class PathAssignment(models.Model):
    """
    Assignment of a learning path to a user.
    """

    class Status(models.TextChoices):
        ASSIGNED = "assigned", _("Asignado")
        IN_PROGRESS = "in_progress", _("En progreso")
        COMPLETED = "completed", _("Completado")
        OVERDUE = "overdue", _("Vencido")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="path_assignments",
        verbose_name=_("Usuario"),
    )
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("Ruta"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.ASSIGNED,
    )
    progress = models.DecimalField(
        _("Progreso (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    due_date = models.DateField(_("Fecha límite"), null=True, blank=True)
    started_at = models.DateTimeField(_("Fecha de inicio"), null=True, blank=True)
    completed_at = models.DateTimeField(_("Fecha de completado"), null=True, blank=True)
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="path_assignments_assigned",
        verbose_name=_("Asignado por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "path_assignments"
        verbose_name = _("Asignación de ruta")
        verbose_name_plural = _("Asignaciones de ruta")
        unique_together = [["user", "learning_path"]]

    def __str__(self):
        return f"{self.user} - {self.learning_path}"
