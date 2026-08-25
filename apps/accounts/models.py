"""
User and authentication models for SD LMS.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager for email or document-based authentication."""

    def create_user(self, email=None, password=None, **extra_fields):
        """Create user with email (optional for operational staff)."""
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser debe tener is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser debe tener is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model for SD LMS.

    Uses email as the username field and includes additional fields
    for employee management in high-risk electrical work environments.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("Activo")
        INACTIVE = "inactive", _("Inactivo")

    class DocumentType(models.TextChoices):
        CC = "CC", _("Cédula de Ciudadanía")
        CE = "CE", _("Cédula de Extranjería")
        TI = "TI", _("Tarjeta de Identidad")
        PASSPORT = "PA", _("Pasaporte")

    class EmploymentType(models.TextChoices):
        DIRECT = "direct", _("Directo")
        CONTRACTOR = "contractor", _("Contratista")

    class Country(models.TextChoices):
        COLOMBIA = "CO", _("Colombia")
        PANAMA = "PA", _("Panamá")
        PERU = "PE", _("Perú")

    class JobProfile(models.TextChoices):
        # Personal operativo (usa cédula para login)
        LINIERO = "LINIERO", _("Liniero")
        TECNICO = "TECNICO", _("Técnico")
        OPERADOR = "OPERADOR", _("Operador")
        # Personal profesional (usa email para login)
        JEFE_CUADRILLA = "JEFE_CUADRILLA", _("Jefe de Cuadrilla")
        INGENIERO_RESIDENTE = "INGENIERO_RESIDENTE", _("Ingeniero Residente")
        COORDINADOR_HSEQ = "COORDINADOR_HSEQ", _("Coordinador HSEQ")
        # Coordinador con permisos de solo visualización (usa email para login)
        COORDINADOR_VISUALIZACION = "COORDINADOR_VIZ", _("Coordinador (Solo Visualización)")
        # Personal administrativo (usa email para login)
        ADMINISTRADOR = "ADMINISTRADOR", _("Administrador")

    class Rol(models.TextChoices):
        """Rol de acceso (RBAC) — issue #58.

        INDEPENDIENTE de `job_profile` (decisión de Miguel, HITL 2026-07-06):
        no se deriva en runtime, es un campo real persistido, editable por un
        Administrador aunque se sugiera un valor según `job_profile`. No
        confundir con `JobProfile` (arriba, TextChoices código muerto — ver
        migración 0012) ni con el modelo `Role`/`UserRole` de más abajo
        (sistema de permisos granulares sin uso real hoy). `rol` es la ÚNICA
        fuente de verdad para gating de UI/vistas (`apps/accounts/permissions.py`,
        sub-item A4 — NO leer `job_profile` ni `is_staff` en checks nuevos).
        """

        EJECUTOR = "EJECUTOR", _("Ejecutor")
        COORDINADOR = "COORDINADOR", _("Coordinador")
        ADMINISTRADOR = "ADMINISTRADOR", _("Administrador")
        TESORERIA = "TESORERIA", _("Tesorería")

    # Remove username field, use email or document for login
    username = None
    email = models.EmailField(
        _("Correo electrónico"),
        unique=True,
        null=True,
        blank=True,
        help_text=_("Requerido para personal profesional y administrativo"),
    )

    # Personal information
    document_type = models.CharField(
        _("Tipo de documento"),
        max_length=10,
        choices=DocumentType.choices,
        default=DocumentType.CC,
    )
    document_number = models.CharField(
        _("Número de documento"),
        max_length=20,
        unique=True,
    )
    phone = models.CharField(_("Teléfono"), max_length=20, blank=True)
    photo = models.ImageField(
        _("Foto"),
        upload_to="users/photos/",
        blank=True,
        null=True,
    )
    signature = models.ImageField(
        _("Firma"),
        upload_to="users/signatures/",
        blank=True,
        null=True,
    )

    # Employment information
    job_position = models.CharField(_("Cargo"), max_length=100)
    job_profile = models.ForeignKey(
        "courses.JobProfileType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("Perfil ocupacional"),
    )
    rol = models.CharField(
        _("Rol de acceso"),
        max_length=20,
        choices=Rol.choices,
        null=True,
        blank=True,
        help_text=_(
            "Rol de acceso (RBAC) para navegación y permisos. Independiente "
            "del perfil ocupacional: se sugiere un valor según `job_profile` "
            "al crear/editar el usuario, pero es editable por un "
            "Administrador. Nulo = pendiente de asignación explícita."
        ),
    )
    supervisor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipo",
        verbose_name=_("Supervisor"),
        help_text=_(
            "Coordinador o Administrador responsable de este usuario. Se usa "
            "para filtrar datos por equipo (Certificados, Gamificación) "
            "cuando el rol del supervisor es Coordinador."
        ),
    )
    employment_type = models.CharField(
        _("Tipo de vinculación"),
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.DIRECT,
    )
    hire_date = models.DateField(_("Fecha de ingreso"))
    country = models.CharField(
        _("País"),
        max_length=2,
        choices=Country.choices,
        default=Country.COLOMBIA,
        help_text=_("País donde trabaja el usuario"),
    )
    status = models.CharField(
        _("Estado"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )


    # Metadata
    created_at = models.DateTimeField(_("Fecha de creación"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Fecha de actualización"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "document_number"
    REQUIRED_FIELDS = ["first_name", "last_name", "job_position", "hire_date"]

    class Meta:
        db_table = "users"
        verbose_name = _("Usuario")
        verbose_name_plural = _("Usuarios")
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.document_number})"

    def save(self, *args, **kwargs):
        """Auto-assign is_staff=True for ADMINISTRADOR profile."""
        if self.job_profile and self.job_profile.code == "ADMINISTRADOR":
            self.is_staff = True
        # Normalize empty email to None to avoid unique constraint violations
        if not self.email:
            self.email = None
        super().save(*args, **kwargs)

    def clean(self):
        """Reject self-supervision (`supervisor == self`, issue #58 A1)."""
        super().clean()
        if self.pk is not None and self.supervisor_id == self.pk:
            raise ValidationError(
                {"supervisor": _("Un usuario no puede ser supervisor de sí mismo.")}
            )

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_operational(self):
        """Check if user is operational staff (uses document number for login)."""
        return self.job_profile and self.job_profile.code in [
            "LINIERO",
            "TECNICO",
            "OPERADOR",
        ]

    @property
    def is_professional(self):
        """Check if user is professional staff (requires email for login)."""
        return self.job_profile and self.job_profile.code in [
            "JEFE_CUADRILLA",
            "INGENIERO_RESIDENTE",
            "COORDINADOR_HSEQ",
            "COORDINADOR_VIZ",
        ]

    @property
    def is_viewer_only(self):
        """Check if user has view-only permissions (no editing capabilities)."""
        return self.job_profile and self.job_profile.code == "COORDINADOR_VIZ"

    @property
    def is_admin(self):
        """Check if user is system administrator (requires email for login)."""
        return self.job_profile and self.job_profile.code == "ADMINISTRADOR"

    @property
    def is_supervisor(self):
        """Check if user has supervisor role (can modify data)."""
        return self.job_profile and self.job_profile.code in [
            "JEFE_CUADRILLA",
            "INGENIERO_RESIDENTE",
            "COORDINADOR_HSEQ",
        ]

    @property
    def can_view_analytics(self):
        """Check if user can view analytics dashboard."""
        return self.is_supervisor or self.is_admin or self.is_viewer_only

    @property
    def can_edit_data(self):
        """Check if user can edit data (not view-only)."""
        return (self.is_supervisor or self.is_admin) and not self.is_viewer_only

    @property
    def requires_email(self):
        """Check if user requires email for authentication."""
        return self.is_professional or self.is_admin

    @property
    def can_access_field(self):
        """Check if user has completed required training for field work."""
        # This will be implemented with the certifications app
        return True


class Role(models.Model):
    """
    Custom roles for fine-grained permissions.
    """

    class RoleType(models.TextChoices):
        ADMIN = "admin", _("Administrador")
        SUPERVISOR = "supervisor", _("Supervisor")
        INSTRUCTOR = "instructor", _("Instructor")
        WORKER = "worker", _("Colaborador")
        AUDITOR = "auditor", _("Auditor ISA")

    name = models.CharField(_("Nombre"), max_length=50, unique=True)
    role_type = models.CharField(
        _("Tipo de rol"),
        max_length=20,
        choices=RoleType.choices,
        default=RoleType.WORKER,
    )
    description = models.TextField(_("Descripción"), blank=True)
    permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=_("Permisos"),
        blank=True,
    )
    users = models.ManyToManyField(
        User,
        through="UserRole",
        through_fields=("role", "user"),
        related_name="custom_roles",
        verbose_name=_("Usuarios"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"
        verbose_name = _("Rol")
        verbose_name_plural = _("Roles")
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserRole(models.Model):
    """
    Through model for User-Role relationship with additional metadata.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_users",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="roles_assigned",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "user_roles"
        verbose_name = _("Asignación de rol")
        verbose_name_plural = _("Asignaciones de roles")
        unique_together = ["user", "role"]

    def __str__(self):
        return f"{self.user} - {self.role}"


class Contract(models.Model):
    """
    Contracts with clients (e.g., ISA Intercolombia).
    """

    code = models.CharField(
        _("Código de contrato"),
        max_length=50,
        unique=True,
        help_text=_("Ej: ISA 4620004459"),
    )
    name = models.CharField(_("Nombre"), max_length=200)
    client = models.CharField(_("Cliente"), max_length=100)
    description = models.TextField(_("Descripción"), blank=True)
    start_date = models.DateField(_("Fecha de inicio"))
    end_date = models.DateField(_("Fecha de fin"), null=True, blank=True)
    is_active = models.BooleanField(_("Activo"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contracts"
        verbose_name = _("Contrato")
        verbose_name_plural = _("Contratos")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class UserContract(models.Model):
    """
    Assignment of users to contracts.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="users",
    )
    assigned_date = models.DateField(_("Fecha de asignación"))
    end_date = models.DateField(_("Fecha de fin"), null=True, blank=True)
    is_active = models.BooleanField(_("Activo"), default=True)
    notes = models.TextField(_("Notas"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_contracts"
        verbose_name = _("Asignación a contrato")
        verbose_name_plural = _("Asignaciones a contratos")
        unique_together = ["user", "contract"]

    def __str__(self):
        return f"{self.user} - {self.contract}"


class JobHistory(models.Model):
    """
    Historical record of job position changes for traceability.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="job_history",
        verbose_name=_("Usuario"),
    )
    previous_position = models.CharField(
        _("Cargo anterior"),
        max_length=100,
        blank=True,
    )
    new_position = models.CharField(
        _("Cargo nuevo"),
        max_length=100,
    )
    previous_profile = models.CharField(
        _("Perfil anterior"),
        max_length=50,
        blank=True,
    )
    new_profile = models.CharField(
        _("Perfil nuevo"),
        max_length=50,
    )
    previous_employment_type = models.CharField(
        _("Vinculación anterior"),
        max_length=20,
        blank=True,
    )
    new_employment_type = models.CharField(
        _("Vinculación nueva"),
        max_length=20,
    )
    change_date = models.DateField(_("Fecha de cambio"))
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="job_changes_made",
        verbose_name=_("Modificado por"),
    )
    reason = models.TextField(_("Motivo"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "job_history"
        verbose_name = _("Historial de cargo")
        verbose_name_plural = _("Historial de cargos")
        ordering = ["-change_date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-change_date"]),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.previous_position} → {self.new_position}"
