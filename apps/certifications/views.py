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

            # Check validity
            is_valid = certificate.status == Certificate.Status.ISSUED
            if certificate.expires_at and certificate.expires_at < timezone.now():
                is_valid = False
                verification_result = "expired"
            elif certificate.status == Certificate.Status.REVOKED:
                verification_result = "revoked"
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

    if not certificate.certificate_file:
        context = {"message": "El archivo del certificado no está disponible."}
        return render(request, "certifications/not_available.html", context)

    # Redirect to file URL (in production would serve directly)
    from django.http import HttpResponseRedirect

    return HttpResponseRedirect(certificate.certificate_file.url)
