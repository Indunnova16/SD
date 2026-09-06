"""
Forms for courses app.
"""

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.assessments.models import Assessment

from .models import (
    AttendanceSignature,
    Category,
    Course,
    CourseSchedule,
    JobProfileType,
    Lesson,
    Module,
)

User = get_user_model()


def get_profile_choices():
    """Get profile choices from the database."""
    return list(
        JobProfileType.objects.filter(is_active=True)
        .order_by("order", "name")
        .values_list("code", "name")
    )


class CategoryForm(forms.ModelForm):
    """Form for creating and editing categories."""

    class Meta:
        model = Category
        fields = ["name", "description", "icon", "color", "order", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
            "icon": forms.HiddenInput(attrs={"id": "id_icon"}),
            "color": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "type": "color"}
            ),
            "order": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name")
        # Check for duplicate name
        qs = Category.objects.filter(name=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Ya existe una categoria con este nombre."))
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Auto-generate slug from name if not set
        if not instance.slug:
            base_slug = slugify(instance.name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            instance.slug = slug
        if commit:
            instance.save()
        return instance


class CourseCreateForm(forms.ModelForm):
    """Form for creating courses (staff only)."""

    target_profiles = forms.MultipleChoiceField(
        label=_("Perfiles objetivo"),
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    class Meta:
        model = Course
        fields = [
            "code",
            "title",
            "description",
            "objectives",
            "course_type",
            "category",
            "project_name",
            "activity_type",
            "instructor",
            "target_profiles",
            "validity_months",
            "status",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "title": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 4}
            ),
            "objectives": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
            "course_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "category": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "project_name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Proyecto/obra (formato FT-HSEQ-60)",
                }
            ),
            "activity_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "instructor": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "validity_months": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Sin categoria"
        self.fields["target_profiles"].choices = get_profile_choices()
        # SD#63 A2: instructor solo entre usuarios activos -- un usuario
        # desactivado no deberia poder quedar seleccionado como instructor de
        # un curso nuevo (los ya asignados antes de desactivarse se
        # preservan via SET_NULL/edicion, no se fuerza aqui).
        self.fields["instructor"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        )
        self.fields["instructor"].empty_label = "Sin asignar"
        self.fields["instructor"].required = False

    def clean_code(self):
        code = self.cleaned_data.get("code")
        if Course.objects.filter(code=code).exists():
            raise forms.ValidationError(_("Ya existe un curso con este codigo."))
        return code

    def clean_target_profiles(self):
        profiles = self.cleaned_data.get("target_profiles")
        return list(profiles) if profiles else []


class CourseEditParamsForm(forms.ModelForm):
    """Form for editing course parameters from Parametrizacion (staff only)."""

    target_profiles = forms.MultipleChoiceField(
        label=_("Perfiles objetivo"),
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    class Meta:
        model = Course
        fields = [
            "title",
            "description",
            "course_type",
            "category",
            "project_name",
            "activity_type",
            "instructor",
            "target_profiles",
            "validity_months",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 4}
            ),
            "course_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "category": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "project_name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Proyecto/obra (formato FT-HSEQ-60)",
                }
            ),
            "activity_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "instructor": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "validity_months": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Sin categoria"
        self.fields["target_profiles"].choices = get_profile_choices()
        self.fields["instructor"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        )
        self.fields["instructor"].empty_label = "Sin asignar"
        self.fields["instructor"].required = False
        if self.instance and self.instance.pk:
            self.initial["target_profiles"] = self.instance.target_profiles or []

    def clean_target_profiles(self):
        profiles = self.cleaned_data.get("target_profiles")
        return list(profiles) if profiles else []


class CourseFullEditForm(forms.ModelForm):
    """Full course edit form for Parametrizacion."""

    target_profiles = forms.MultipleChoiceField(
        label=_("Perfiles objetivo"),
        choices=[],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    class Meta:
        model = Course
        fields = [
            "code",
            "title",
            "description",
            "objectives",
            "course_type",
            "thumbnail",
            "banner_image",
            "theme_color",
            "category",
            "project_name",
            "activity_type",
            "instructor",
            "target_profiles",
            "validity_months",
            "status",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "title": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 4}
            ),
            "objectives": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
            "course_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "category": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "project_name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Proyecto/obra (formato FT-HSEQ-60)",
                }
            ),
            "activity_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "instructor": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "validity_months": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "thumbnail": forms.ClearableFileInput(
                attrs={"class": "file-input file-input-bordered w-full"}
            ),
            "banner_image": forms.ClearableFileInput(
                attrs={"class": "file-input file-input-bordered w-full"}
            ),
            "theme_color": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "type": "color"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Sin categoria"
        self.fields["target_profiles"].choices = get_profile_choices()
        self.fields["instructor"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        )
        self.fields["instructor"].empty_label = "Sin asignar"
        self.fields["instructor"].required = False
        if self.instance and self.instance.pk:
            self.initial["target_profiles"] = self.instance.target_profiles or []

    def clean_code(self):
        code = self.cleaned_data.get("code")
        qs = Course.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Ya existe un curso con este codigo."))
        return code

    def clean_target_profiles(self):
        profiles = self.cleaned_data.get("target_profiles")
        return list(profiles) if profiles else []


class JobProfileTypeForm(forms.ModelForm):
    """Form for creating/editing job profile types."""

    class Meta:
        model = JobProfileType
        fields = ["code", "name", "description", "is_active", "order"]
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "placeholder": "ej: SUPERVISOR"}
            ),
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 2}
            ),
            "order": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
        }

    def clean_code(self):
        code = self.cleaned_data.get("code", "").upper()
        qs = JobProfileType.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Ya existe un perfil con este codigo."))
        return code


# =============================================================================
# Course Builder Forms
# =============================================================================


class ModuleBuilderForm(forms.ModelForm):
    """Form for creating/editing modules in the course builder."""

    class Meta:
        model = Module
        fields = ["title", "description", "cover_image"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Nombre del modulo",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "rows": 2,
                    "placeholder": "Descripcion del modulo (opcional)",
                }
            ),
            "cover_image": forms.ClearableFileInput(
                attrs={"class": "file-input file-input-bordered file-input-sm w-full"}
            ),
        }


class LessonBuilderForm(forms.ModelForm):
    """Form for creating/editing lessons in the course builder."""

    class Meta:
        model = Lesson
        fields = [
            "title",
            "lesson_type",
            "description",
            "content",
            "content_file",
            "video_url",
            "duration",
            "is_mandatory",
            "scheduled_date",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Nombre de la leccion",
                }
            ),
            "lesson_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "description": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "rows": 2,
                    "placeholder": "Descripcion (opcional)",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "rows": 4,
                    "placeholder": "Contenido de texto o HTML",
                }
            ),
            "content_file": forms.ClearableFileInput(
                attrs={"class": "file-input file-input-bordered w-full"}
            ),
            "video_url": forms.URLInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "https://...",
                }
            ),
            "duration": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "min": "0",
                    "placeholder": "Minutos",
                }
            ),
            "is_mandatory": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
            # datetime-local sends "YYYY-MM-DDTHH:MM"; format keeps the value
            # populated when editing an existing lesson.
            "scheduled_date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "input input-bordered input-sm w-full",
                },
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The browser datetime-local widget submits "YYYY-MM-DDTHH:MM"; the
        # default DateTimeField input_formats do NOT include the "T" separator,
        # so without this the field silently invalidates in production
        # (gotcha analogous to <input type="month">).
        self.fields["scheduled_date"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        # scheduled_date is only meaningful for attendance lessons; it is not
        # required at the DB level (legacy lessons have none).
        self.fields["scheduled_date"].required = False

    def clean(self):
        cleaned_data = super().clean()
        # scheduled_date es opcional incluso para lecciones de Asistencia
        # (decision de Miguel, SD#57.1): antes se exigia aqui, pero el campo
        # ya es null=True/blank=True a nivel de modelo y el cliente pidio
        # poder guardar una leccion de Asistencia sin fecha agendada.
        return cleaned_data

    def clean_duration(self):
        """SD#62 A2: duration es obligatorio (>0 minutos) para todo
        lesson_type EXCEPTO 'attendance' (que usa scheduled_date, SD#57.1).

        RIESGO documentado en el PLAN: 21/25 lecciones en prod (84%) tienen
        duration=0 hoy -- cualquier edicion futura de esas lecciones legacy
        queda bloqueada hasta completar duration (comportamiento esperado,
        no un bug: el cliente pidio que duration sea obligatorio).
        """
        duration = self.cleaned_data.get("duration")
        # lesson_type se limpia antes que duration (orden de Meta.fields),
        # pero self.data es el fallback si por algun motivo no llego a
        # cleaned_data (p.ej. el propio lesson_type fallo su validacion).
        lesson_type = self.cleaned_data.get("lesson_type") or self.data.get("lesson_type")
        if lesson_type and lesson_type != Lesson.Type.ATTENDANCE and not duration:
            raise forms.ValidationError(
                _("La duración es obligatoria (mayor a 0 minutos) para este tipo de lección.")
            )
        return duration


class QuickAssessmentForm(forms.Form):
    """Form for quickly creating an assessment from the course builder."""

    title = forms.CharField(
        label=_("Titulo"),
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Titulo de la evaluacion",
            }
        ),
    )
    assessment_type = forms.ChoiceField(
        label=_("Tipo"),
        choices=[
            ("quiz", _("Evaluación")),
            ("exam", _("Examen")),
            ("practice", _("Practica")),
        ],
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    passing_score = forms.DecimalField(
        label=_("Puntaje minimo (0-5)"),
        initial=Decimal("3.50"),
        min_value=Decimal("0"),
        max_value=Decimal("5"),
        max_digits=5,
        decimal_places=2,
        localize=False,  # es-CO: evitar coma decimal que vacia el input number
        widget=forms.NumberInput(
            attrs={
                "class": "input input-bordered w-full",
                "min": "0",
                "max": "5",
                "step": "0.01",
            }
        ),
    )
    time_limit = forms.IntegerField(
        label=_("Tiempo limite (minutos)"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "input input-bordered w-full", "min": "1", "placeholder": "Sin limite"}
        ),
    )
    max_attempts = forms.IntegerField(
        label=_("Intentos maximos"),
        initial=0,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input input-bordered w-full", "min": "0"}),
        help_text=_("0 = intentos ilimitados"),
    )


class AssessmentEditForm(forms.ModelForm):
    """Form for editing all properties of an existing Assessment from the course builder."""

    # Override the auto-generated field to disable es-CO localization
    # (Decimal con coma "80,00" vacia el <input type=number> en el navegador).
    passing_score = forms.DecimalField(
        label=_("Puntaje minimo (0-5)"),
        initial=Decimal("3.50"),
        min_value=Decimal("0"),
        max_value=Decimal("5"),
        max_digits=5,
        decimal_places=2,
        localize=False,
        widget=forms.NumberInput(
            attrs={
                "class": "input input-bordered input-sm w-full",
                "min": "0",
                "max": "5",
                "step": "0.01",
            }
        ),
    )

    class Meta:
        model = Assessment
        fields = [
            "title",
            "description",
            "assessment_type",
            "passing_score",
            "time_limit",
            "max_attempts",
            "shuffle_questions",
            "shuffle_answers",
            "show_correct_answers",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "input input-bordered input-sm w-full", "required": True}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered textarea-sm w-full",
                    "rows": 2,
                }
            ),
            "assessment_type": forms.Select(
                attrs={"class": "select select-bordered select-sm w-full"}
            ),
            "time_limit": forms.NumberInput(
                attrs={
                    "class": "input input-bordered input-sm w-full",
                    "min": "1",
                    "placeholder": "Sin limite",
                }
            ),
            "max_attempts": forms.NumberInput(
                attrs={"class": "input input-bordered input-sm w-full", "min": "0"}
            ),
            "shuffle_questions": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary checkbox-sm"}
            ),
            "shuffle_answers": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary checkbox-sm"}
            ),
            "show_correct_answers": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary checkbox-sm"}
            ),
            "status": forms.Select(attrs={"class": "select select-bordered select-sm w-full"}),
        }

    def clean_passing_score(self):
        value = self.cleaned_data.get("passing_score")
        if value is None or value < 0 or value > 5:
            raise forms.ValidationError(_("Debe estar entre 0 y 5."))
        return value

    def clean_time_limit(self):
        value = self.cleaned_data.get("time_limit")
        if value is not None and value < 0:
            raise forms.ValidationError(_("No puede ser negativo."))
        return value

    def clean_status(self):
        """Issue SD#84: no permitir publicar una evaluación sin preguntas.

        Este es el punto de guardado explícito "Publicar quiz" del builder
        (builder_edit_assessment). Sin este guard, un assessment con 0
        preguntas quedaba published (ver assessment_id=28 "Evaluacion
        seguridad vial") y permitía intentos con resultado 0/0.
        """
        value = self.cleaned_data.get("status")
        if value == Assessment.Status.PUBLISHED and self.instance.pk:
            if self.instance.questions.count() == 0:
                raise forms.ValidationError(
                    _(
                        "No se puede publicar: esta evaluación no tiene preguntas "
                        "todavía. Agrega al menos una pregunta antes de publicarla."
                    )
                )
        return value


class AttendanceSignatureForm(forms.ModelForm):
    """Form for capturing attendance signatures."""

    class Meta:
        model = AttendanceSignature
        fields = ["signature_image"]
        widgets = {
            "signature_image": forms.HiddenInput(),
        }


def get_job_position_choices():
    """Cargos (`User.job_position`) realmente existentes en la BD — SD#73.

    `job_position` es texto libre (no un catálogo), así que las opciones se
    derivan de los usuarios ACTIVOS. Mismo espíritu que `get_profile_choices`:
    la lista se lee de la BD, no se hardcodea.
    """
    values = (
        User.objects.filter(is_active=True)
        .exclude(job_position="")
        .values_list("job_position", flat=True)
        .distinct()
        .order_by("job_position")
    )
    return [(v, v) for v in values]


class CourseScheduleForm(forms.ModelForm):
    """Form de la "Programación" (convocatoria) — SD#73.

    Combina los datos de la programación con la audiencia (requisito 2 del
    issue): personas específicas + perfiles ocupacionales + cargos. Los tres
    campos de audiencia NO son del modelo `CourseSchedule` (la audiencia se
    materializa como `ScheduleAssignment` vía `CourseScheduleService`), por eso
    van declarados aparte.

    `users` usa `SelectMultiple` alimentado por el buscador HTMX
    (`schedule_search_people`) en vez de renderizar la lista completa de
    usuarios: el cliente pidió explícitamente "buscador, no una lista larga sin
    filtro". La validación contra el queryset de usuarios activos sigue del lado
    del servidor — el buscador es UI, no el control.
    """

    users = forms.ModelMultipleChoiceField(
        label=_("Personas específicas"),
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "hidden", "id": "id_users"}),
        help_text=_("Búsquelas por nombre o cédula."),
    )
    job_profiles = forms.ModelMultipleChoiceField(
        label=_("Perfiles ocupacionales"),
        queryset=JobProfileType.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text=_("Convoca a TODAS las personas activas con ese perfil."),
    )
    job_positions = forms.MultipleChoiceField(
        label=_("Cargos"),
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text=_("Convoca a TODAS las personas activas con ese cargo."),
    )

    class Meta:
        model = CourseSchedule
        fields = [
            "course",
            "name",
            "suggested_end_date",
            "responsable",
            "activity_type",
            "notes",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ej: Turno X",
                }
            ),
            "suggested_end_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"},
                format="%Y-%m-%d",
            ),
            "responsable": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "activity_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "notes": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_users = User.objects.filter(is_active=True).order_by("first_name", "last_name")

        self.fields["users"].queryset = active_users
        self.fields["job_profiles"].queryset = JobProfileType.objects.filter(
            is_active=True
        ).order_by("order", "name")
        self.fields["job_positions"].choices = get_job_position_choices()

        # Solo cursos publicados: una convocatoria es sobre un curso YA
        # existente y utilizable; convocar a un borrador dejaría al convocado
        # sin poder entrar. Los ya programados sobre otro estado se preservan.
        course_qs = Course.objects.filter(status=Course.Status.PUBLISHED).order_by("title")
        if self.instance and self.instance.pk and self.instance.course_id:
            course_qs = Course.objects.filter(
                models.Q(status=Course.Status.PUBLISHED) | models.Q(pk=self.instance.course_id)
            ).order_by("title")
        self.fields["course"].queryset = course_qs
        self.fields["course"].empty_label = None

        self.fields["responsable"].queryset = active_users
        self.fields["responsable"].empty_label = "Sin asignar"
        self.fields["responsable"].required = False

        if self.instance and self.instance.pk and self.instance.suggested_end_date:
            self.initial["suggested_end_date"] = self.instance.suggested_end_date.isoformat()

    def clean(self):
        cleaned = super().clean()
        # En creación hay que convocar a alguien; en edición se permite guardar
        # sin audiencia nueva (típicamente se está reasignando el responsable,
        # requisito 4 del issue, sin volver a tocar el grupo).
        if not self.instance.pk:
            if not any(
                (
                    cleaned.get("users"),
                    cleaned.get("job_profiles"),
                    cleaned.get("job_positions"),
                )
            ):
                raise forms.ValidationError(
                    _(
                        "Seleccione al menos una persona, un perfil ocupacional o un "
                        "cargo para convocar."
                    )
                )
        return cleaned
