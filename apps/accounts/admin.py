"""
Admin configuration for accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Contract, JobHistory, Role, User, UserContract, UserRole


class JobHistoryInline(admin.TabularInline):
    """Inline for JobHistory in User admin."""

    model = JobHistory
    fk_name = "user"
    extra = 0
    readonly_fields = (
        "previous_position",
        "new_position",
        "previous_profile",
        "new_profile",
        "previous_employment_type",
        "new_employment_type",
        "change_date",
        "changed_by",
        "reason",
        "created_at",
    )
    can_delete = False
    verbose_name = _("Cambio de cargo")
    verbose_name_plural = _("Historial de cambios de cargo")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = (
        "email",
        "first_name",
        "last_name",
        "document_number",
        "job_position",
        "employment_type",
        "status",
        "is_active",
    )
    list_filter = ("status", "is_active", "is_staff", "job_profile", "employment_type", "hire_date")
    search_fields = ("email", "first_name", "last_name", "document_number")
    ordering = ("last_name", "first_name")
    inlines = [JobHistoryInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Información Personal"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "document_type",
                    "document_number",
                    "phone",
                    "photo",
                )
            },
        ),
        (
            _("Información Laboral"),
            {
                "fields": (
                    "job_position",
                    "job_profile",
                    "employment_type",
                    "hire_date",
                    "status",
                )
            },
        ),
        (
            _("Permisos"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Fechas Importantes"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "document_type",
                    "document_number",
                    "job_position",
                    "job_profile",
                    "employment_type",
                    "hire_date",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Save user and create job history if position/profile/employment_type changed."""
        if change:  # Only for existing users
            try:
                old_user = User.objects.get(pk=obj.pk)
                # Check if job-related fields changed
                position_changed = old_user.job_position != obj.job_position
                profile_changed = old_user.job_profile != obj.job_profile
                employment_changed = old_user.employment_type != obj.employment_type

                if position_changed or profile_changed or employment_changed:
                    # Create job history record
                    JobHistory.objects.create(
                        user=obj,
                        previous_position=old_user.job_position,
                        new_position=obj.job_position,
                        previous_profile=old_user.job_profile,
                        new_profile=obj.job_profile,
                        previous_employment_type=old_user.employment_type,
                        new_employment_type=obj.employment_type,
                        change_date=timezone.now().date(),
                        changed_by=request.user,
                        reason="Modificado desde el panel de administración",
                    )
            except User.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin configuration for Role model."""

    list_display = ("name", "role_type", "user_count", "created_at")
    list_filter = ("role_type",)
    search_fields = ("name", "description")
    filter_horizontal = ("permissions",)

    @admin.display(description=_("Usuarios"))
    def user_count(self, obj):
        return obj.users.count()


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    """Admin configuration for Contract model."""

    list_display = ("code", "name", "client", "start_date", "end_date", "is_active")
    list_filter = ("is_active", "client", "start_date")
    search_fields = ("code", "name", "client")
    date_hierarchy = "start_date"


class UserContractInline(admin.TabularInline):
    """Inline for UserContract in User admin."""

    model = UserContract
    extra = 0
    autocomplete_fields = ["contract"]


class UserRoleInline(admin.TabularInline):
    """Inline for UserRole in User admin."""

    model = UserRole
    extra = 0
    autocomplete_fields = ["role"]


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    """Admin configuration for JobHistory model."""

    list_display = (
        "user",
        "previous_position",
        "new_position",
        "previous_employment_type",
        "new_employment_type",
        "change_date",
        "changed_by",
    )
    list_filter = ("change_date", "new_profile", "new_employment_type")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__document_number",
        "new_position",
        "reason",
    )
    date_hierarchy = "change_date"
    readonly_fields = ("created_at",)
    autocomplete_fields = ["user", "changed_by"]
