"""
Forms for accounts app.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.utils.translation import gettext_lazy as _

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


class UserCreateForm(forms.ModelForm):
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
            "employment_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            # hire_date widget controlled by class-level field override above
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

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

        return cleaned_data

    def save(self, commit=True):
        from .services import PasswordService

        user = super().save(commit=False)
        password = PasswordService.generate_password(user.document_number, user.first_name)
        user.set_password(password)
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
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

        return cleaned_data
