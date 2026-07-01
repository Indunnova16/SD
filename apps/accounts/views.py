"""
Web views for accounts app (HTMX-powered).
"""

import base64
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    BulkUploadForm,
    LoginForm,
    PasswordChangeForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    ProfileForm,
    UserCreateForm,
    UserEditForm,
)
from .models import JobHistory
from .services import BulkUploadService, ExportService, PasswordService

logger = logging.getLogger(__name__)
User = get_user_model()


def login_view(request):
    """Login page with HTMX support."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = LoginForm(request.POST or None)
    error = None

    if request.method == "POST":
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            remember_me = form.cleaned_data.get("remember_me", False)

            # El backend soporta autenticación por email o número de documento
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                if not remember_me:
                    request.session.set_expiry(0)

                next_url = request.GET.get("next", "accounts:dashboard")

                if request.htmx:
                    response = HttpResponse()
                    response["HX-Redirect"] = reverse(next_url) if ":" in next_url else next_url
                    return response

                return redirect(next_url)
            else:
                error = "Credenciales inválidas. Por favor, intente de nuevo."
                logger.warning(f"Failed login attempt for: {username}")

    context = {
        "form": form,
        "error": error,
    }

    if request.htmx:
        return render(request, "accounts/partials/login_form.html", context)

    return render(request, "accounts/login.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Logout user with confirmation."""
    if request.method == "POST":
        logout(request)
        messages.success(request, "Has cerrado sesión exitosamente.")
        return redirect("accounts:login")

    return render(request, "accounts/logout_confirm.html")


@login_required
def dashboard(request):
    """Main dashboard."""
    from apps.courses.models import Category

    categories = Category.objects.filter(is_active=True).order_by(
        "order", "name"
    )
    from apps.courses.models import JobProfileType

    context = {
        "user": request.user,
        "categories": categories,
        "job_profiles": JobProfileType.objects.filter(is_active=True).values_list("code", "name"),
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile(request):
    """User profile page."""
    context = {
        "user": request.user,
    }
    return render(request, "accounts/profile.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def profile_edit(request):
    """Edit user profile."""
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil actualizado correctamente.")

        if request.htmx:
            return render(request, "accounts/partials/profile_success.html")

        return redirect("accounts:profile")

    context = {"form": form}

    if request.htmx:
        return render(request, "accounts/partials/profile_form.html", context)

    return render(request, "accounts/profile_edit.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    """Change user password."""
    form = PasswordChangeForm(user=request.user, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Contraseña actualizada correctamente. Por favor, inicie sesión nuevamente."
        )
        logout(request)
        return redirect("accounts:login")

    context = {"form": form}
    return render(request, "accounts/change_password.html", context)


def password_reset_request(request):
    """Request password reset email."""
    form = PasswordResetRequestForm(request.POST or None)
    email_sent = False

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        try:
            user = User.objects.get(email=email)
            # Generate token and send email
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            reset_url = request.build_absolute_uri(
                reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
            )

            context = {
                "user": user,
                "reset_url": reset_url,
            }

            subject = "Recuperar contraseña - SD LMS"
            message = render_to_string("accounts/emails/password_reset.txt", context)
            html_message = render_to_string("accounts/emails/password_reset.html", context)

            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                html_message=html_message,
                fail_silently=False,
            )

            logger.info(f"Password reset email sent to {email}")
        except User.DoesNotExist:
            # Don't reveal if email exists
            logger.info(f"Password reset requested for non-existent email: {email}")

        email_sent = True

    context = {
        "form": form,
        "email_sent": email_sent,
    }

    if request.htmx and email_sent:
        return render(request, "accounts/partials/password_reset_sent.html")

    return render(request, "accounts/password_reset.html", context)


def password_reset_confirm(request, uidb64, token):
    """Confirm password reset with new password."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "accounts/password_reset_invalid.html")

    form = PasswordResetConfirmForm(user=user, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Contraseña restablecida correctamente. Ahora puede iniciar sesión."
        )
        return redirect("accounts:login")

    context = {"form": form}
    return render(request, "accounts/password_reset_confirm.html", context)


# ==================== Lockout View ====================


def lockout_view(request):
    """View shown when user is locked out due to too many failed attempts."""
    return render(request, "accounts/lockout.html")


# ==================== User Management Views (Admin Only) ====================


@login_required
@require_http_methods(["GET"])
def user_list(request):
    """List all users (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("accounts:dashboard")

    # Get search and filter parameters
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    job_profile_filter = request.GET.get("job_profile", "")

    # Active/inactive tab filter (default: active users)
    active_filter = request.GET.get("active", "true")
    is_active = active_filter != "false"

    users = User.objects.all().order_by("-created_at")

    # Counts for tab badges (before other filters)
    active_count = User.objects.filter(is_active=True).count()
    inactive_count = User.objects.filter(is_active=False).count()

    # Filter by active status
    users = users.filter(is_active=is_active)

    if search:
        users = users.filter(
            models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
            | models.Q(email__icontains=search)
            | models.Q(document_number__icontains=search)
        )

    if status_filter:
        users = users.filter(status=status_filter)

    if job_profile_filter:
        users = users.filter(job_profile__code=job_profile_filter)

    # Get unique job profiles for filter dropdown
    job_profiles = (
        User.objects.values_list("job_profile__code", flat=True)
        .distinct()
        .order_by("job_profile__code")
    )

    context = {
        "users": users,
        "search": search,
        "status_filter": status_filter,
        "job_profile_filter": job_profile_filter,
        "job_profiles": job_profiles,
        "status_choices": User.Status.choices,
        "active_filter": active_filter,
        "active_count": active_count,
        "inactive_count": inactive_count,
    }

    if request.htmx:
        return render(request, "accounts/partials/user_list_table.html", context)

    return render(request, "accounts/user_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    """Create a new user (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("accounts:dashboard")

    form = UserCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Usuario {user.get_full_name()} creado exitosamente.")
        logger.info(f"User {user.document_number} created by {request.user.document_number}")

        if request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("accounts:user_list")
            return response

        return redirect("accounts:user_list")

    context = {"form": form}

    if request.htmx:
        return render(request, "accounts/partials/user_form.html", context)

    return render(request, "accounts/user_create.html", context)


@login_required
@require_http_methods(["GET"])
def user_detail(request, user_id):
    """View user details (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("accounts:dashboard")

    user = get_object_or_404(User, pk=user_id)

    context = {
        "user_obj": user,
    }

    if request.htmx:
        return render(request, "accounts/partials/user_detail.html", context)

    return render(request, "accounts/user_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def user_edit(request, user_id):
    """Edit user details (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("accounts:dashboard")

    user = get_object_or_404(User, pk=user_id)

    # Store old values before update for job history tracking
    old_position = user.job_position
    old_profile = user.job_profile
    old_employment_type = user.employment_type

    # Bug preexistente (SD#51): request.FILES no se pasaba al form, por lo que
    # ninguna subida de archivo (foto, y ahora firma) llegaba a validarse ni a
    # guardarse — se corrige de paso al agregar el campo `signature`.
    form = UserEditForm(request.POST or None, request.FILES or None, instance=user)

    if request.method == "POST" and form.is_valid():
        updated_user = form.save(commit=False)

        # Firma dibujada a mano en el canvas (base64), alternativa a subir un
        # archivo — mismo patrón que save_attendance_signature
        # (apps/courses/views.py). Si no viene ni archivo ni canvas data, el
        # campo `signature` queda intacto (no se pisa una firma existente).
        signature_canvas_data = request.POST.get("signature_canvas_data")
        if signature_canvas_data:
            try:
                _header, image_data = signature_canvas_data.split(",", 1)
                image_bytes = base64.b64decode(image_data)
                filename = f"signature_{updated_user.pk}_{timezone.now().timestamp()}.png"
                updated_user.signature.save(filename, ContentFile(image_bytes), save=False)
            except Exception:
                logger.warning(
                    f"signature_canvas_data inválido para usuario {updated_user.pk}, se ignora"
                )

        updated_user.save()
        form.save_m2m()

        # Check if job-related fields changed and create history record
        position_changed = old_position != updated_user.job_position
        profile_changed = old_profile != updated_user.job_profile
        employment_changed = old_employment_type != updated_user.employment_type

        if position_changed or profile_changed or employment_changed:
            JobHistory.objects.create(
                user=updated_user,
                previous_position=old_position,
                new_position=updated_user.job_position,
                previous_profile=old_profile,
                new_profile=updated_user.job_profile,
                previous_employment_type=old_employment_type,
                new_employment_type=updated_user.employment_type,
                change_date=timezone.now().date(),
                changed_by=request.user,
                reason="Modificado desde el sistema web",
            )

        messages.success(request, f"Usuario {user.get_full_name()} actualizado exitosamente.")
        logger.info(f"User {user.document_number} updated by {request.user.document_number}")

        if request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("accounts:user_detail", kwargs={"user_id": user.pk})
            return response

        return redirect("accounts:user_detail", user_id=user.pk)

    context = {
        "form": form,
        "user_obj": user,
    }

    if request.htmx:
        return render(request, "accounts/partials/user_form.html", context)

    return render(request, "accounts/user_edit.html", context)


@login_required
@require_POST
def user_toggle_status(request, user_id):
    """Toggle user active status (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    user = get_object_or_404(User, pk=user_id)

    # Prevent self-deactivation
    if user.pk == request.user.pk:
        messages.error(request, "No puede desactivar su propia cuenta.")
        if request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("accounts:user_list")
            return response
        return redirect("accounts:user_list")

    user.is_active = not user.is_active
    user.save()

    action = "activado" if user.is_active else "desactivado"
    messages.success(request, f"Usuario {user.get_full_name()} {action} exitosamente.")
    logger.info(f"User {user.document_number} {action} by {request.user.document_number}")

    # Reset and re-assign all profile courses when reactivated
    if user.is_active and user.job_profile:
        from .signals import _reset_and_reenroll_by_profile

        _reset_and_reenroll_by_profile(user)
        messages.info(
            request,
            f"Cursos reiniciados y reasignados según perfil: {user.job_profile.name if user.job_profile else 'N/A'}",
        )

    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = reverse("accounts:user_list")
        return response

    return redirect("accounts:user_list")


@login_required
def user_learning_history(request, user_id):
    """View a user's learning history (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    from apps.courses.models import CompletionRecord, Enrollment

    user = get_object_or_404(User, pk=user_id)
    enrollments = (
        Enrollment.objects.filter(user=user)
        .select_related("course", "course__category")
        .order_by("-updated_at")
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        enrollments = enrollments.filter(status=status_filter)

    # Past completion records (permanent history)
    completion_records = (
        CompletionRecord.objects.filter(user=user)
        .select_related("course", "course__category")
        .order_by("-completed_at")
    )

    # Stats counts (unfiltered)
    all_enrollments = Enrollment.objects.filter(user=user)
    context = {
        "user_obj": user,
        "enrollments": enrollments,
        "completion_records": completion_records,
        "current_status": status_filter,
        "status_choices": Enrollment.Status.choices,
        "completed_count": all_enrollments.filter(status="completed").count(),
        "in_progress_count": all_enrollments.filter(status="in_progress").count(),
        "pending_count": all_enrollments.filter(status="enrolled").count(),
        "past_completions_count": completion_records.count(),
    }

    if request.htmx:
        return render(request, "accounts/partials/learning_history_table.html", context)

    return render(request, "accounts/user_learning_history.html", context)


@login_required
@require_POST
def reassign_enrollment(request, user_id, enrollment_id):
    """Reassign a course from a user's learning history (admin/staff only).

    Resets the enrollment back to ENROLLED (progress 0, dates cleared) so the
    user can take the course again, regardless of its current status. A
    permanent CompletionRecord is kept for audit when there was prior progress.
    Mirrors the reset logic of courses.reenable_course but is staff-driven and
    applies to any status (not only EXPIRED).
    """
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    from apps.courses.models import CompletionRecord, Enrollment, LessonProgress

    enrollment = get_object_or_404(
        Enrollment.objects.select_related("course"),
        pk=enrollment_id,
        user_id=user_id,
    )
    course = enrollment.course

    # Preserve a permanent audit record before resetting.
    if enrollment.progress > 0:
        CompletionRecord.objects.create(
            user=enrollment.user,
            course=course,
            completed_at=enrollment.completed_at or enrollment.updated_at,
            progress=enrollment.progress,
            reset_reason="Reasignación por administrador",
        )

    # Reset the enrollment so the course is available again.
    enrollment.status = Enrollment.Status.ENROLLED
    enrollment.progress = 0
    enrollment.started_at = None
    enrollment.completed_at = None
    enrollment.assigned_by = request.user
    enrollment.save()

    # Reset per-lesson progress.
    LessonProgress.objects.filter(enrollment=enrollment).update(
        is_completed=False,
        progress_percent=0,
        time_spent=0,
        completed_at=None,
    )

    messages.success(
        request,
        f"Curso '{course.title}' reasignado correctamente.",
    )
    return redirect("accounts:user_learning_history", user_id=user_id)


@login_required
@require_GET
def user_export_pdf(request, user_id):
    """Export user profile and learning history as PDF (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    from io import BytesIO

    from xhtml2pdf import pisa

    from apps.courses.models import CompletionRecord, Enrollment

    user = get_object_or_404(User, pk=user_id)

    enrollments = (
        Enrollment.objects.filter(user=user)
        .select_related("course", "course__category")
        .order_by("-updated_at")
    )
    completion_records = (
        CompletionRecord.objects.filter(user=user)
        .select_related("course", "course__category")
        .order_by("-completed_at")
    )
    all_enrollments = Enrollment.objects.filter(user=user)

    context = {
        "user_obj": user,
        "enrollments": enrollments,
        "completion_records": completion_records,
        "total_enrollments": all_enrollments.count(),
        "completed_count": all_enrollments.filter(status="completed").count(),
        "in_progress_count": all_enrollments.filter(status="in_progress").count(),
        "pending_count": all_enrollments.filter(status="enrolled").count(),
        "generated_at": timezone.now(),
        "request_user": request.user,
    }

    html_string = render_to_string("accounts/user_profile_pdf.html", context)

    result = BytesIO()
    pdf = pisa.CreatePDF(html_string, dest=result, encoding="utf-8")

    if pdf.err:
        messages.error(request, "Error al generar el PDF.")
        return redirect("accounts:user_detail", user_id=user_id)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    filename = f"ficha_{user.document_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def user_delete(request, user_id):
    """Delete a user permanently (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    user = get_object_or_404(User, pk=user_id)

    # Prevent self-deletion
    if user.pk == request.user.pk:
        messages.error(request, "No puede eliminar su propia cuenta.")
        if request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = reverse("accounts:user_list")
            return response
        return redirect("accounts:user_list")

    full_name = user.get_full_name()
    document = user.document_number

    try:
        user.delete()
    except models.ProtectedError:
        messages.error(
            request,
            f"No se puede eliminar a {full_name} porque tiene registros asociados "
            "(cursos, charlas, evaluaciones, etc.). Desactívelo en su lugar.",
        )
        redirect_url = reverse("accounts:user_detail", args=[user_id])
        if request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)

    messages.success(request, f"Usuario {full_name} eliminado permanentemente.")
    logger.info(f"User {document} deleted by {request.user.document_number}")

    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = reverse("accounts:user_list")
        return response

    return redirect("accounts:user_list")


@login_required
@require_POST
def admin_reset_password(request, user_id):
    """Reset user password to parameterized default (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    user = get_object_or_404(User, pk=user_id)
    new_password = PasswordService.reset_password(user)

    messages.success(
        request,
        f"Contraseña de {user.get_full_name()} restablecida. Nueva contraseña: {new_password}",
    )
    logger.info(f"Password reset for {user.document_number} by {request.user.document_number}")

    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = reverse("accounts:user_detail", kwargs={"user_id": user.pk})
        return response

    return redirect("accounts:user_detail", user_id=user.pk)


# ==================== Bulk Upload Views ====================


@login_required
@require_http_methods(["GET", "POST"])
def bulk_upload(request):
    """Bulk upload users from Excel file (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("accounts:dashboard")

    form = BulkUploadForm(request.POST or None, request.FILES or None)
    results = None

    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        rows, parse_errors = BulkUploadService.parse_excel(file)

        if parse_errors:
            results = {"created": [], "errors": parse_errors}
        else:
            created, create_errors = BulkUploadService.create_users_from_rows(rows)
            results = {"created": created, "errors": create_errors}

            if created:
                messages.success(request, f"Se crearon {len(created)} usuarios exitosamente.")

    context = {
        "form": form,
        "results": results,
    }
    return render(request, "accounts/bulk_upload.html", context)


@login_required
def download_template(request):
    """Download Excel template for bulk upload."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    content = BulkUploadService.generate_template()
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="plantilla_usuarios.xlsx"'
    return response


# ==================== Export Views ====================


@login_required
def export_pending_users(request):
    """Export users with pending courses to Excel (admin/staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect("accounts:dashboard")

    category_id = request.GET.get("category")
    profile = request.GET.get("job_profile")

    content = ExportService.export_pending_users(category_id=category_id, profile=profile)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="usuarios_pendientes.xlsx"'
    return response


# =============================================================================
# Help / User Manual
# =============================================================================


@login_required
@require_GET
def help_admin(request):
    """Admin user manual page."""
    return render(request, "help/admin_manual.html")


@login_required
@require_GET
def help_worker(request):
    """Worker user manual page."""
    return render(request, "help/worker_manual.html")
