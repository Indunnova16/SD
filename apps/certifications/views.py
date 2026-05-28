"""
Web views for certifications app.
"""

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
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
