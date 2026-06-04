"""
Forms for courses app.
"""

from decimal import Decimal

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.assessments.models import Assessment

from .models import AttendanceSignature, Category, Course, JobProfileType, Lesson, Module


def get_profile_choices():
    """Get profile choices from the database."""
    return list(
        JobProfileType.objects.filter(is_active=True)
        .order_by("order", "name")
        .values_list("code", "name")
    )


class CategoryForm(forms.ModelForm):
    """Form for creating and editing categories."""

    subcategories_text = forms.CharField(
        label=_("Subcategorias"),
        widget=forms.Textarea(
            attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": 4,
                "placeholder": "Ingrese una subcategoria por linea, ej:\nSeguridad Electrica\nTrabajo en Alturas\nPrimeros Auxilios",
            }
        ),
        required=False,
        help_text=_(
            "Ingrese una subcategoria por linea. Las existentes se conservan, las nuevas se crean automaticamente."
        ),
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Pre-populate subcategories field with existing children
            children = self.instance.children.order_by("order", "name")
            if children.exists():
                self.initial["subcategories_text"] = "\n".join(child.name for child in children)

    def clean_name(self):
        name = self.cleaned_data.get("name")
        # Check for duplicate name at root level
        qs = Category.objects.filter(name=name, parent__isnull=True)
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
            self._save_subcategories(instance)
        return instance

    def _save_subcategories(self, instance):
        """Create/update subcategories from the text field."""
        text = self.cleaned_data.get("subcategories_text", "")
        new_names = [line.strip() for line in text.splitlines() if line.strip()]

        existing_children = {child.name: child for child in instance.children.all()}

        # Remove children that are no longer in the list
        for name, child in existing_children.items():
            if name not in new_names:
                # Only unlink (set parent=None), don't delete if it has courses
                if child.courses.exists():
                    child.parent = None
                    child.save(update_fields=["parent"])
                else:
                    child.delete()

        # Create or keep subcategories
        for order, name in enumerate(new_names):
            if name in existing_children:
                # Update order if needed
                child = existing_children[name]
                if child.order != order:
                    child.order = order
                    child.save(update_fields=["order"])
            else:
                # Create new subcategory
                base_slug = slugify(name)
                slug = base_slug
                counter = 1
                while Category.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                Category.objects.create(
                    name=name,
                    slug=slug,
                    parent=instance,
                    order=order,
                    is_active=True,
                    color=instance.color,
                )


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
            "validity_months": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Sin categoria"
        self.fields["target_profiles"].choices = get_profile_choices()

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
            "validity_months": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Sin categoria"
        self.fields["target_profiles"].choices = get_profile_choices()
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
        lesson_type = cleaned_data.get("lesson_type")
        scheduled_date = cleaned_data.get("scheduled_date")
        if lesson_type == Lesson.Type.ATTENDANCE and not scheduled_date:
            self.add_error(
                "scheduled_date",
                _("La fecha y hora agendada es obligatoria para lecciones de Asistencia."),
            )
        return cleaned_data


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
            ("quiz", _("Quiz")),
            ("exam", _("Examen")),
            ("practice", _("Practica")),
        ],
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    passing_score = forms.DecimalField(
        label=_("Puntaje minimo (%)"),
        initial=Decimal("80.00"),
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        max_digits=5,
        decimal_places=2,
        localize=False,  # es-CO: evitar coma decimal que vacia el input number
        widget=forms.NumberInput(
            attrs={
                "class": "input input-bordered w-full",
                "min": "0",
                "max": "100",
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
        initial=3,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input input-bordered w-full", "min": "0"}),
        help_text=_("0 = intentos ilimitados"),
    )


class AssessmentEditForm(forms.ModelForm):
    """Form for editing all properties of an existing Assessment from the course builder."""

    # Override the auto-generated field to disable es-CO localization
    # (Decimal con coma "80,00" vacia el <input type=number> en el navegador).
    passing_score = forms.DecimalField(
        label=_("Puntaje minimo (%)"),
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        max_digits=5,
        decimal_places=2,
        localize=False,
        widget=forms.NumberInput(
            attrs={
                "class": "input input-bordered input-sm w-full",
                "min": "0",
                "max": "100",
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
        if value is None or value < 0 or value > 100:
            raise forms.ValidationError(_("Debe estar entre 0 y 100."))
        return value

    def clean_time_limit(self):
        value = self.cleaned_data.get("time_limit")
        if value is not None and value < 0:
            raise forms.ValidationError(_("No puede ser negativo."))
        return value


class AttendanceSignatureForm(forms.ModelForm):
    """Form for capturing attendance signatures."""

    class Meta:
        model = AttendanceSignature
        fields = ["signature_image"]
        widgets = {
            "signature_image": forms.HiddenInput(),
        }
