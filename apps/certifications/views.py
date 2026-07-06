"""
Web views for certifications app.
"""

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.permissions import Rol, user_has_rol

from .models import Certificate, CertificateVerification


# ---------------------------------------------------------------------------
# A7 (issue #58) — filtrado por rol: propio (Ejecutor) / equipo vía
# `supervisor` FK (Coordinador) / todos (Administrador).
# ---------------------------------------------------------------------------

#: Valores válidos del query param ``scope`` en `my_certificates`.
SCOPE_MIO = "mio"
SCOPE_EQUIPO = "equipo"
SCOPE_TODOS = "todos"


def _certificates_queryset_for_scope(user, scope):
    """
    Devuelve el queryset de `Certificate` correspondiente a `scope`,
    ya resuelto y autorizado para `user` (ver `_resolve_scope`).

    - ``mio``: certificados propios (todos los roles).
    - ``equipo``: certificados de usuarios con `supervisor=user` (Coordinador
      o Administrador — un Administrador que además supervisa gente ve su
      propio equipo con este scope, distinto de `todos`).
    - ``todos``: TODOS los certificados del sistema (solo Administrador).
    """
    if scope == SCOPE_TODOS:
        return Certificate.objects.select_related("course", "template", "user")
    if scope == SCOPE_EQUIPO:
        return Certificate.objects.filter(user__supervisor=user).select_related(
            "course", "template", "user"
        )
    return Certificate.objects.filter(user=user).select_related("course", "template")


def _resolve_scope(user, requested_scope):
    """
    Valida `requested_scope` contra el `rol` de `user` y degrada a `mio`
    (el más restrictivo) si el usuario no está autorizado — nunca se filtra
    "hacia arriba" un scope no permitido (evita fuga de datos por
    manipulación del query param, ej. un Ejecutor pidiendo `?scope=todos`).
    """
    can_view_equipo = user_has_rol(user, Rol.COORDINADOR, Rol.ADMINISTRADOR)
    can_view_todos = user_has_rol(user, Rol.ADMINISTRADOR)

    if requested_scope == SCOPE_TODOS and can_view_todos:
        scope = SCOPE_TODOS
    elif requested_scope == SCOPE_EQUIPO and can_view_equipo:
        scope = SCOPE_EQUIPO
    else:
        scope = SCOPE_MIO

    return scope, can_view_equipo, can_view_todos


def _user_can_view_certificate(user, certificate):
    """
    True si `user` puede ver/descargar `certificate`: dueño, Administrador
    (ve todo), o Coordinador que supervisa al dueño del certificado (equipo,
    vía `User.supervisor` — FK de A1, `related_name='equipo'`).
    """
    if certificate.user_id == user.id:
        return True
    if user_has_rol(user, Rol.ADMINISTRADOR):
        return True
    if user_has_rol(user, Rol.COORDINADOR):
        return certificate.user.supervisor_id == user.id
    return False


@login_required
def my_certificates(request):
    """
    Ver certificados: propios por defecto; `?scope=equipo` (Coordinador ve
    su equipo vía `supervisor` FK; Administrador ve a quien supervisa
    directamente) o `?scope=todos` (Administrador, todos los certificados
    del sistema) — issue #58 sub-item A7.
    """
    requested_scope = request.GET.get("scope", SCOPE_MIO)
    scope, can_view_equipo, can_view_todos = _resolve_scope(request.user, requested_scope)

    certificates = _certificates_queryset_for_scope(request.user, scope).order_by(
        "-issued_at"
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        certificates = certificates.filter(status=status_filter)

    context = {
        "certificates": certificates,
        "current_status": status_filter,
        "statuses": Certificate.Status.choices,
        "current_scope": scope,
        "can_view_equipo": can_view_equipo,
        "can_view_todos": can_view_todos,
    }
    return render(request, "certifications/my_certificates.html", context)


@login_required
def certificate_detail(request, certificate_id):
    """View certificate details."""
    certificate = get_object_or_404(
        Certificate.objects.select_related("course", "template", "user"),
        pk=certificate_id,
    )

    # Owner, Administrador, o Coordinador del equipo del dueño (A7).
    if not _user_can_view_certificate(request.user, certificate):
        return render(request, "certifications/not_authorized.html", status=403)

    context = {
        "certificate": certificate,
    }
    return render(request, "certifications/certificate_detail.html", context)


def verify_certificate(request, certificate_number=None):
    """Public certificate verification page."""
    certificate = None
    verification_result = None

    if request.method == "POST" or certificate_number:
        cert_num = certificate_number or request.POST.get("certificate_number", "")

        try:
            certificate = Certificate.objects.select_related("user", "course").get(
                certificate_number=cert_num
            )

            # Check validity (check REVOKED first, then expiration)
            is_valid = certificate.status == Certificate.Status.ISSUED
            if certificate.status == Certificate.Status.REVOKED:
                is_valid = False
                verification_result = "revoked"
            elif certificate.expires_at and certificate.expires_at < timezone.now():
                is_valid = False
                verification_result = "expired"
            elif is_valid:
                verification_result = "valid"

            # Log verification
            CertificateVerification.objects.create(
                certificate=certificate,
                ip_address=request.META.get("REMOTE_ADDR", ""),
                user_agent=request.headers.get("user-agent", ""),
                is_valid=is_valid,
            )

        except Certificate.DoesNotExist:
            verification_result = "not_found"

    context = {
        "certificate": certificate,
        "verification_result": verification_result,
        "certificate_number": certificate_number,
    }
    return render(request, "certifications/verify.html", context)


@login_required
def certificate_download(request, certificate_id):
    """Download certificate file."""
    certificate = get_object_or_404(
        Certificate.objects.select_related("user"),
        pk=certificate_id,
    )

    # Owner, Administrador, o Coordinador del equipo del dueño (A7) — mismo
    # criterio que certificate_detail, para no dejar un botón "Descargar"
    # visible en el detalle que luego 403-ee acá.
    if not _user_can_view_certificate(request.user, certificate):
        return render(request, "certifications/not_authorized.html", status=403)

    # Validate certificate status
    if certificate.status != Certificate.Status.ISSUED:
        context = {
            "message": f"Este certificado no está disponible para descargar (Estado: {certificate.get_status_display()})."
        }
        return render(request, "certifications/not_available.html", context, status=403)

    # Check expiration
    if certificate.expires_at and certificate.expires_at < timezone.now():
        context = {"message": "Este certificado ha expirado y no puede ser descargado."}
        return render(request, "certifications/not_available.html", context, status=403)

    if not certificate.certificate_file:
        context = {"message": "El archivo del certificado no está disponible."}
        return render(request, "certifications/not_available.html", context, status=404)

    # Serve PDF directly via FileResponse (streams + correct content-type + as_attachment)
    # This avoids relying on a public GCS bucket URL or signed-URL expiration.
    try:
        # certificate_file is a FieldFile; .open("rb") returns a file handle that
        # FileResponse will iterate over and close after streaming.
        file_handle = certificate.certificate_file.open("rb")
    except FileNotFoundError:
        context = {
            "message": "El archivo del certificado no está disponible (FileNotFound)."
        }
        return render(request, "certifications/not_available.html", context, status=404)

    response = FileResponse(
        file_handle,
        as_attachment=True,
        filename=f"Certificado_{certificate.certificate_number}.pdf",
        content_type="application/pdf",
    )
    return response


# ---------------------------------------------------------------------------
# B2 — Staff admin panel for CertificateTemplate
# ---------------------------------------------------------------------------

from django.contrib import messages  # noqa: E402
from django.contrib.auth.decorators import user_passes_test  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.shortcuts import redirect  # noqa: E402
from django.views.decorators.http import require_http_methods  # noqa: E402

from .forms import CertificateTemplateForm  # noqa: E402
from .models import CertificateTemplate  # noqa: E402
from .services import CertificateTemplateService  # noqa: E402


def _staff_required(view):
    """Decorator: only users with rol=ADMINISTRADOR can access."""
    return user_passes_test(lambda u: user_has_rol(u, Rol.ADMINISTRADOR))(view)


@_staff_required
def template_list(request):
    """List all certificate templates for staff to manage."""
    templates = CertificateTemplate.objects.all().order_by("-is_active", "name")
    return render(
        request,
        "certifications/admin/template_list.html",
        {"templates": templates},
    )


@_staff_required
@require_http_methods(["GET", "POST"])
def template_create(request):
    """Create a new certificate template."""
    if request.method == "POST":
        form = CertificateTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            template = form.save()
            messages.success(request, f"Plantilla '{template.name}' creada.")
            return redirect("certifications:template_edit", template_id=template.pk)
    else:
        form = CertificateTemplateForm()
    return render(
        request,
        "certifications/admin/template_form.html",
        {"form": form, "template": None, "action": "create"},
    )


@_staff_required
@require_http_methods(["GET", "POST"])
def template_edit(request, template_id):
    """Edit an existing certificate template."""
    template = get_object_or_404(CertificateTemplate, pk=template_id)
    if request.method == "POST":
        form = CertificateTemplateForm(request.POST, request.FILES, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Plantilla actualizada.")
            return redirect("certifications:template_edit", template_id=template.pk)
    else:
        form = CertificateTemplateForm(instance=template)
    return render(
        request,
        "certifications/admin/template_form.html",
        {"form": form, "template": template, "action": "edit"},
    )


@_staff_required
def template_preview(request, template_id):
    """Render a HTML preview of the template with sample data."""
    template = get_object_or_404(CertificateTemplate, pk=template_id)
    html = CertificateTemplateService.preview_template(template)
    return HttpResponse(html)


@_staff_required
@require_http_methods(["POST"])
def template_toggle_active(request, template_id):
    """Activate/deactivate a template (HTMX target)."""
    template = get_object_or_404(CertificateTemplate, pk=template_id)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    return render(
        request,
        "certifications/admin/_template_row.html",
        {"t": template},
    )
