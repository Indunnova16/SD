"""
Web views for certifications app.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Certificate, CertificateVerification


@login_required
def my_certificates(request):
    """View user's certificates."""
    certificates = (
        Certificate.objects.filter(
            user=request.user,
        )
        .select_related("course", "template")
        .order_by("-issued_at")
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        certificates = certificates.filter(status=status_filter)

    context = {
        "certificates": certificates,
        "current_status": status_filter,
        "statuses": Certificate.Status.choices,
    }
    return render(request, "certifications/my_certificates.html", context)


@login_required
def certificate_detail(request, certificate_id):
    """View certificate details."""
    certificate = get_object_or_404(
        Certificate.objects.select_related("course", "template", "user"),
        pk=certificate_id,
    )

    # Only allow owner or staff to view
    if certificate.user != request.user and not request.user.is_staff:
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
        Certificate,
        pk=certificate_id,
    )

    # Only allow owner or staff
    if certificate.user != request.user and not request.user.is_staff:
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
        return render(request, "certifications/not_available.html", context)

    # Redirect to file URL (in production would serve directly)
    from django.http import HttpResponseRedirect

    return HttpResponseRedirect(certificate.certificate_file.url)


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
    """Decorator: only staff users can access."""
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view)


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
