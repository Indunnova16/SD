"""
Forms for accounts app.
"""

import json

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.utils.translation import gettext_lazy as _

from apps.courses.models import JobProfileType

User = get_user_model()


class LoginForm(forms.Form):
    """Login form with document number/email and password."""

    username = forms.CharField(
        label=_("Cédula o correo electrónico"),
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Número de cédula o correo@ejemplo.com",
                "autocomplete": "username",
            }
        ),
        help_text=_(
            "Personal operativo: ingrese su número de cédula. Personal profesional/administrativo: ingrese su correo electrónico."
        ),
    )
    password = forms.CharField(
        label=_("Contraseña"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        label=_("Recordarme"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
    )


class ProfileForm(forms.ModelForm):
    """Form for editing user profile."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "photo"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "placeholder": "Nombre"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "placeholder": "Apellido"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "placeholder": "+57 300 123 4567"}
            ),
            "photo": forms.FileInput(attrs={"class": "file-input file-input-bordered w-full"}),
        }


class PasswordChangeForm(SetPasswordForm):
    """Form for changing password (requires old password)."""

    old_password = forms.CharField(
        label=_("Contraseña actual"),
        widget=forms.PasswordInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(user, *args, **kwargs)
        # Reorder fields
        self.fields = {
            "old_password": self.fields["old_password"],
            "new_password1": self.fields["new_password1"],
            "new_password2": self.fields["new_password2"],
        }
        # Update widget classes
        self.fields["new_password1"].widget.attrs.update(
            {"class": "input input-bordered w-full", "placeholder": "••••••••"}
        )
        self.fields["new_password2"].widget.attrs.update(
            {"class": "input input-bordered w-full", "placeholder": "••••••••"}
        )

    def clean_old_password(self):
        old_password = self.cleaned_data.get("old_password")
        if not self.user.check_password(old_password):
            raise forms.ValidationError(_("La contraseña actual es incorrecta."))
        return old_password

    def save(self, commit=True):
        self.user.set_password(self.cleaned_data["new_password1"])
        if commit:
            self.user.save()
        return self.user


class PasswordResetRequestForm(forms.Form):
    """Form for requesting password reset."""

    email = forms.EmailField(
        label=_("Correo electrónico"),
        widget=forms.EmailInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "correo@ejemplo.com",
                "autocomplete": "email",
            }
        ),
    )


class PasswordResetConfirmForm(SetPasswordForm):
    """Form for setting new password after reset."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].widget.attrs.update(
            {
                "class": "input input-bordered w-full",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        )
        self.fields["new_password2"].widget.attrs.update(
            {
                "class": "input input-bordered w-full",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        )


class BulkUploadForm(forms.Form):
    """Form for bulk user upload from Excel file."""

    file = forms.FileField(
        label=_("Archivo Excel"),
        widget=forms.FileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": ".xlsx,.xls",
            }
        ),
        help_text=_("Suba un archivo Excel (.xlsx) con las columnas requeridas."),
    )

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            if not file.name.endswith((".xlsx", ".xls")):
                raise forms.ValidationError(_("Solo se permiten archivos Excel (.xlsx, .xls)."))
            if file.size > 5 * 1024 * 1024:  # 5MB limit
                raise forms.ValidationError(_("El archivo no puede superar los 5MB."))
        return file


class RolSupervisorMixin:
    """Comportamiento compartido de `rol`/`supervisor` entre
    `UserCreateForm` y `UserEditForm` (issue #58, sub-item A2).

    - `rol`: se sugiere automáticamente según `job_profile` (mismo mapeo
      que la migración de datos `0016_backfill_user_rol.py`, sub-item A1),
      pero SIEMPRE queda editable — el Administrador puede cambiarlo antes
      de guardar. Si el `job_profile` elegido no tiene una sugerencia
      confiable (`COORDINADOR_VIZ`, `CAPATAZ`, `"TODOS LOS CARGOS"`,
      `CONTRATISTA`, `CONDUCTOR`, sin perfil, o cualquier código futuro
      desconocido) y `rol` llega vacío al servidor, se exige elección
      explícita (`ValidationError` solo en el campo `rol`, no bloquea el
      resto del form). Si sí hay sugerencia confiable y el cliente no
      envió `rol` (ej. JS deshabilitado, o un POST directo sin ese campo),
      se aplica la sugerencia como respaldo server-side — evita romper
      integraciones/tests que no conocían este campo antes de A2.

    NOTA: este mapeo NO reutiliza el de `0016_backfill_user_rol.py`
    (importar un módulo de migración numerado desde código de aplicación
    es frágil — se rompe si el historial de migraciones se squashea). Es
    una copia intencional documentada; ambos deben mantenerse en sync si
    Miguel ajusta el mapeo (mismo caveat que deja PLAN.md para `CAPATAZ`).
    A diferencia del backfill (que defaultea lo no-mapeado a EJECUTOR para
    NO dejar usuarios existentes en NULL), acá lo no-mapeado NO tiene
    sugerencia — es un flujo hacia adelante (alta/edición), no hay razón
    para adivinar: se le pide al Administrador que elija.
    """

    ROL_SUGERIDO_POR_JOB_PROFILE_CODE = {
        "LINIERO": User.Rol.EJECUTOR,
        "TECNICO": User.Rol.EJECUTOR,
        "OPERADOR": User.Rol.EJECUTOR,
        "JEFE_CUADRILLA": User.Rol.COORDINADOR,
        "INGENIERO_RESIDENTE": User.Rol.COORDINADOR,
        "COORDINADOR_HSEQ": User.Rol.COORDINADOR,
        "ADMINISTRADOR": User.Rol.ADMINISTRADOR,
    }

    @classmethod
    def suggest_rol_for_job_profile(cls, job_profile):
        """Rol sugerido (str) para un `JobProfileType`, o `None` si el
        código no tiene un mapeo automático confiable — en ese caso el
        selector `rol` debe quedar vacío y forzar elección explícita."""
        if job_profile is None:
            return None
        return cls.ROL_SUGERIDO_POR_JOB_PROFILE_CODE.get(job_profile.code)

    def _setup_rol_supervisor_fields(self):
        """Configura queryset/empty_label de `supervisor`. Llamar al final
        de `__init__`, después de `super().__init__()`."""
        if "supervisor" not in self.fields:
            return
        supervisor_field = self.fields["supervisor"]
        supervisor_field.queryset = User.objects.filter(
            rol__in=[User.Rol.COORDINADOR, User.Rol.ADMINISTRADOR]
        ).order_by("last_name", "first_name")
        supervisor_field.required = False
        supervisor_field.empty_label = "— Sin supervisor asignado —"

    @property
    def rol_suggestions_json(self):
        """JSON `{"<job_profile_id>": "<rol_sugerido>"|null, ...}` que el
        template usa para prellenar `rol` vía JS cuando cambia
        `job_profile`, sin bloquear la edición manual posterior."""
        job_profile_field = self.fields.get("job_profile")
        queryset = (
            job_profile_field.queryset
            if job_profile_field is not None
            else JobProfileType.objects.filter(is_active=True)
        )
        mapping = {str(jp.pk): self.suggest_rol_for_job_profile(jp) for jp in queryset}
        return json.dumps(mapping)

    def _clean_rol_requiere_eleccion_explicita(self, cleaned_data):
        """Ver docstring de la clase. Muta y retorna `cleaned_data`."""
        job_profile = cleaned_data.get("job_profile")
        rol = cleaned_data.get("rol")
        if rol:
            return cleaned_data

        suggestion = self.suggest_rol_for_job_profile(job_profile)
        if suggestion:
            cleaned_data["rol"] = suggestion
        else:
            self.add_error(
                "rol",
                _(
                    "Debe seleccionar un rol de acceso: el perfil ocupacional "
                    "elegido no sugiere uno automáticamente."
                ),
            )
        return cleaned_data

    def _clean_supervisor_no_puede_ser_uno_mismo(self, cleaned_data):
        """Propaga con un mensaje claro (no 500) la regla de A1
        (`User.clean()`: `supervisor != self`) apenas el form la detecta,
        sin esperar a la validación del modelo en `_post_clean()`."""
        supervisor = cleaned_data.get("supervisor")
        if (
            supervisor is not None
            and self.instance.pk is not None
            and supervisor.pk == self.instance.pk
        ):
            self.add_error(
                "supervisor", _("Un usuario no puede ser supervisor de sí mismo.")
            )
        return cleaned_data


class UserCreateForm(RolSupervisorMixin, forms.ModelForm):
    """Form for creating new users (admin only). Password auto-generated."""

    # Override hire_date to force ISO format on render AND parse.
    # HTML5 <input type="date"> only accepts/emits YYYY-MM-DD in its `value`
    # attribute. The default DateInput widget renders the initial value using
    # the first DATE_INPUT_FORMATS of the active locale (es-co → "%d/%m/%Y"),
    # which the browser silently rejects → datepicker shows empty → POST sends
    # blank → ValidationError → user perceives "no persiste". See SD#41.
    hire_date = forms.DateField(
        label=_("Fecha de ingreso"),
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "input input-bordered w-full", "type": "date"},
        ),
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "document_type",
            "document_number",
            "phone",
            "job_position",
            "job_profile",
            "rol",
            "supervisor",
            "employment_type",
            "hire_date",
            "status",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "input input-bordered w-full"}),
            "first_name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "last_name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "document_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "document_number": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "phone": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "job_position": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "job_profile": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "rol": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "supervisor": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "employment_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            # hire_date widget controlled by class-level field override above
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_rol_supervisor_fields()

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("Ya existe un usuario con este correo electrónico."))
        return email

    def clean_document_number(self):
        document_number = self.cleaned_data.get("document_number")
        if User.objects.filter(document_number=document_number).exists():
            raise forms.ValidationError(_("Ya existe un usuario con este número de documento."))
        return document_number

    def clean(self):
        cleaned_data = super().clean()
        job_profile = cleaned_data.get("job_profile")
        email = cleaned_data.get("email")

        # Solo administradores requieren email obligatoriamente
        if job_profile and job_profile.code == "ADMINISTRADOR" and not email:
            self.add_error("email", _("El correo electrónico es requerido para administradores."))

        cleaned_data = self._clean_rol_requiere_eleccion_explicita(cleaned_data)
        cleaned_data = self._clean_supervisor_no_puede_ser_uno_mismo(cleaned_data)

        return cleaned_data

    def save(self, commit=True):
        from .services import PasswordService

        user = super().save(commit=False)
        password = PasswordService.generate_password(user.document_number, user.first_name)
        user.set_password(password)
        # Atributo transiente (NO campo de modelo, no persiste en BD): expone
        # la contraseña generada para que la vista la muestre al admin en el
        # momento de la creación — sin esto, la única forma de conocerla era
        # `admin_reset_password` (issue #58, reproceso: avelasquez@indunnova.com
        # no pudo loguearse porque nadie vio nunca su password inicial).
        user.generated_password = password
        if commit:
            user.save()
        return user


class UserEditForm(RolSupervisorMixin, forms.ModelForm):
    """Form for editing existing users (admin only)."""

    # Override hire_date to force ISO format on render AND parse.
    # See UserCreateForm for the full rationale; this is the form where the
    # bug actually manifested: editing an existing user with a populated
    # hire_date rendered "15/01/2024" in the value attribute, which HTML5
    # <input type="date"> rejects, so the field appeared empty and any
    # subsequent save failed validation. See SD#41.
    hire_date = forms.DateField(
        label=_("Fecha de ingreso"),
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "input input-bordered w-full", "type": "date"},
        ),
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "document_type",
            "document_number",
            "phone",
            "job_position",
            "job_profile",
            "rol",
            "supervisor",
            "employment_type",
            "hire_date",
            "status",
            "is_active",
            "is_staff",
            "signature",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "input input-bordered w-full"}),
            "first_name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "last_name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "document_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "document_number": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "phone": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "job_position": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "job_profile": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "rol": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "supervisor": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "employment_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            # hire_date widget controlled by class-level field override above
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
            "signature": forms.FileInput(
                attrs={
                    "class": "file-input file-input-bordered w-full",
                    "accept": "image/*",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make document_number validation skip current instance
        # Email is optional for operational staff
        self.fields["email"].required = False
        self.fields["document_number"].required = True
        self._setup_rol_supervisor_fields()

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Ya existe un usuario con este correo electrónico."))
        return email

    def clean_document_number(self):
        document_number = self.cleaned_data.get("document_number")
        if (
            User.objects.filter(document_number=document_number)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(_("Ya existe un usuario con este número de documento."))
        return document_number

    def clean(self):
        cleaned_data = super().clean()
        job_profile = cleaned_data.get("job_profile")
        email = cleaned_data.get("email")

        # Solo administradores requieren email obligatoriamente
        if job_profile and job_profile.code == "ADMINISTRADOR" and not email:
            self.add_error("email", _("El correo electrónico es requerido para administradores."))

        cleaned_data = self._clean_rol_requiere_eleccion_explicita(cleaned_data)
        cleaned_data = self._clean_supervisor_no_puede_ser_uno_mismo(cleaned_data)

        return cleaned_data
