"""
Assessment models for SD LMS.
"""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.validators import validate_0_5_scale


class AssessmentManager(models.Manager):
    """Custom manager for Assessment model."""

    def published(self):
        return self.filter(status="published")

    def for_course(self, course):
        return self.filter(course=course)

    def with_questions(self):
        return self.prefetch_related("questions__answers")


class Assessment(models.Model):
    """
    Assessment/Quiz model.
    """

    class Type(models.TextChoices):
        QUIZ = "quiz", _("Evaluación")
        EXAM = "exam", _("Examen")
        PRACTICE = "practice", _("Práctica")
        SURVEY = "survey", _("Encuesta")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        PUBLISHED = "published", _("Publicado")
        ARCHIVED = "archived", _("Archivado")

    title = models.CharField(_("Título"), max_length=200)
    description = models.TextField(_("Descripción"), blank=True)
    assessment_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=Type.choices,
        default=Type.QUIZ,
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name=_("Curso"),
        null=True,
        blank=True,
    )
    lesson = models.ForeignKey(
        "courses.Lesson",
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name=_("Lección"),
        null=True,
        blank=True,
    )
    passing_score = models.DecimalField(
        _("Puntaje mínimo"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.50"),
        help_text=_("Puntaje mínimo para aprobar (escala 0-5)"),
        validators=[validate_0_5_scale],
    )
    time_limit = models.PositiveIntegerField(
        _("Tiempo límite (minutos)"),
        null=True,
        blank=True,
    )
    max_attempts = models.PositiveIntegerField(
        _("Intentos máximos"),
        default=0,
        help_text=_("0 = intentos ilimitados"),
    )
    shuffle_questions = models.BooleanField(
        _("Mezclar preguntas"),
        default=True,
    )
    shuffle_answers = models.BooleanField(
        _("Mezclar respuestas"),
        default=True,
    )
    show_correct_answers = models.BooleanField(
        _("Mostrar respuestas correctas"),
        default=True,
        help_text=_("Mostrar respuestas correctas al finalizar"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="assessments_created",
        verbose_name=_("Creado por"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AssessmentManager()

    class Meta:
        db_table = "assessments"
        verbose_name = _("Evaluación")
        verbose_name_plural = _("Evaluaciones")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def total_questions(self):
        return self.questions.count()

    @property
    def total_points(self):
        from django.db.models import Sum

        result = self.questions.aggregate(total=Sum("points"))
        return result["total"] or Decimal("0.00")


class Question(models.Model):
    """
    Question in an assessment.
    """

    class Type(models.TextChoices):
        SINGLE_CHOICE = "single_choice", _("Selección única")
        MULTIPLE_CHOICE = "multiple_choice", _("Selección múltiple")
        TRUE_FALSE = "true_false", _("Verdadero/Falso")
        SHORT_ANSWER = "short_answer", _("Respuesta corta")
        ESSAY = "essay", _("Ensayo")
        MATCHING = "matching", _("Emparejamiento")
        ORDERING = "ordering", _("Ordenamiento")

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Evaluación"),
    )
    question_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=Type.choices,
        default=Type.SINGLE_CHOICE,
    )
    text = models.TextField(_("Pregunta"))
    explanation = models.TextField(
        _("Explicación"),
        blank=True,
        help_text=_("Explicación de la respuesta correcta"),
    )
    points = models.DecimalField(
        _("Puntos"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
    )
    order = models.PositiveIntegerField(_("Orden"), default=0)
    image = models.ImageField(
        _("Imagen"),
        upload_to="assessments/questions/",
        blank=True,
        null=True,
    )
    metadata = models.JSONField(_("Metadatos"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "questions"
        verbose_name = _("Pregunta")
        verbose_name_plural = _("Preguntas")
        ordering = ["order"]
        indexes = [
            models.Index(fields=["assessment", "order"]),
        ]

    def __str__(self):
        return f"{self.assessment.title} - Q{self.order}"


class Answer(models.Model):
    """
    Answer option for a question.
    """

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name=_("Pregunta"),
    )
    text = models.TextField(_("Respuesta"))
    is_correct = models.BooleanField(_("Es correcta"), default=False)
    order = models.PositiveIntegerField(_("Orden"), default=0)
    feedback = models.TextField(
        _("Retroalimentación"),
        blank=True,
        help_text=_("Retroalimentación específica para esta respuesta"),
    )

    class Meta:
        db_table = "answers"
        verbose_name = _("Respuesta")
        verbose_name_plural = _("Respuestas")
        ordering = ["order"]

    def __str__(self):
        return f"{self.question} - {self.text[:50]}"


class AssessmentAttempt(models.Model):
    """
    User attempt at an assessment.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("En progreso")
        SUBMITTED = "submitted", _("Enviado")
        GRADED = "graded", _("Calificado")
        EXPIRED = "expired", _("Expirado")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="assessment_attempts",
        verbose_name=_("Usuario"),
    )
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name=_("Evaluación"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    attempt_number = models.PositiveIntegerField(_("Número de intento"), default=1)
    score = models.DecimalField(
        _("Puntaje"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    points_earned = models.DecimalField(
        _("Puntos obtenidos"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    passed = models.BooleanField(_("Aprobado"), null=True, blank=True)
    time_spent = models.PositiveIntegerField(
        _("Tiempo empleado (segundos)"),
        default=0,
    )
    started_at = models.DateTimeField(_("Fecha de inicio"), auto_now_add=True)
    submitted_at = models.DateTimeField(_("Fecha de envío"), null=True, blank=True)
    graded_at = models.DateTimeField(_("Fecha de calificación"), null=True, blank=True)
    graded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts_graded",
        verbose_name=_("Calificado por"),
    )
    ip_address = models.GenericIPAddressField(
        _("Dirección IP"),
        null=True,
        blank=True,
    )
    user_agent = models.TextField(_("User Agent"), blank=True)

    class Meta:
        db_table = "assessment_attempts"
        verbose_name = _("Intento de evaluación")
        verbose_name_plural = _("Intentos de evaluación")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "assessment"]),
            models.Index(fields=["status", "user"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.assessment} (Intento {self.attempt_number})"


class AttemptAnswer(models.Model):
    """
    User's answer to a question in an attempt.
    """

    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
        verbose_name=_("Intento"),
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
        verbose_name=_("Pregunta"),
    )
    selected_answers = models.ManyToManyField(
        Answer,
        blank=True,
        related_name="selections",
        verbose_name=_("Respuestas seleccionadas"),
    )
    text_answer = models.TextField(
        _("Respuesta de texto"),
        blank=True,
        help_text=_("Para preguntas de respuesta corta o ensayo"),
    )
    is_correct = models.BooleanField(_("Es correcta"), null=True, blank=True)
    points_awarded = models.DecimalField(
        _("Puntos otorgados"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    feedback = models.TextField(_("Retroalimentación"), blank=True)
    answered_at = models.DateTimeField(_("Fecha de respuesta"), auto_now=True)

    class Meta:
        db_table = "attempt_answers"
        verbose_name = _("Respuesta de intento")
        verbose_name_plural = _("Respuestas de intento")
        unique_together = [["attempt", "question"]]

    def __str__(self):
        return f"{self.attempt} - {self.question}"
