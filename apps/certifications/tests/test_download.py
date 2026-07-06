"""
Tests for the certificate_download view (FileResponse-based PDF download).

Covers:
- Login required
- Owner can download
- Staff can download any certificate
- Other users get 403
- Revoked certificates are blocked
- Expired certificates are blocked
- Missing file returns 404
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate, CertificateTemplate
from apps.courses.models import Course


# Minimal valid PDF (header + EOF) — large enough to be a real-ish file.
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<<>>endobj\n"
    b"trailer<<>>\n"
    b"%%EOF\n"
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CertificateDownloadTests(TestCase):
    """Test certificate_download view enforces auth, ownership and status."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="100000001",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        cls.owner = User.objects.create_user(
            email="owner@test.com",
            password="testpass123",
            first_name="Juan",
            last_name="Pérez",
            document_number="100000002",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )
        cls.other = User.objects.create_user(
            email="other@test.com",
            password="testpass123",
            first_name="Pedro",
            last_name="Gómez",
            document_number="100000003",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )

        cls.course = Course.objects.create(
            code="DL-001",
            title="Curso de prueba descarga",
            created_by=cls.admin,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        cls.template = CertificateTemplate.objects.create(
            name="Plantilla descarga",
            signer_name="Directora HSEQ",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )

    def _make_certificate(
        self,
        *,
        user=None,
        status=Certificate.Status.ISSUED,
        with_file=True,
        expires_at=None,
        number_suffix="A",
    ):
        """Create a certificate (optionally with attached PDF content)."""
        user = user or self.owner
        cert = Certificate.objects.create(
            user=user,
            course=self.course,
            template=self.template,
            certificate_number=f"CERT-2026-{number_suffix}",
            status=status,
            issued_at=timezone.now() if status == Certificate.Status.ISSUED else None,
            expires_at=expires_at,
        )
        if with_file:
            cert.certificate_file.save(
                f"{cert.certificate_number}.pdf",
                ContentFile(MINIMAL_PDF),
                save=True,
            )
        return cert

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def test_download_requires_login(self):
        """Anonymous user must be redirected to login."""
        cert = self._make_certificate(number_suffix="ANON")
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    # ------------------------------------------------------------------
    # Happy path: owner
    # ------------------------------------------------------------------
    def test_download_owner_ok(self):
        """Owner can download — response is PDF, attachment, with bytes."""
        cert = self._make_certificate(number_suffix="OWN")
        self.client.force_login(self.owner)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        disposition = response.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn(f"Certificado_{cert.certificate_number}.pdf", disposition)
        # Drain streaming content and check it starts with PDF magic.
        body = b"".join(response.streaming_content)
        self.assertTrue(body.startswith(b"%PDF"))

    # ------------------------------------------------------------------
    # AuthZ
    # ------------------------------------------------------------------
    def test_download_other_user_forbidden(self):
        """Another (non-owner, non-staff) user gets 403."""
        cert = self._make_certificate(number_suffix="OTH")
        self.client.force_login(self.other)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    def test_download_staff_ok(self):
        """Staff can download any certificate."""
        cert = self._make_certificate(number_suffix="STF")
        self.client.force_login(self.admin)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------
    def test_download_revoked_blocked(self):
        """Revoked certs cannot be downloaded (403)."""
        cert = self._make_certificate(
            status=Certificate.Status.REVOKED,
            number_suffix="REV",
        )
        self.client.force_login(self.owner)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    def test_download_expired_blocked(self):
        """Certificates with expires_at in the past cannot be downloaded (403)."""
        past = timezone.now() - timedelta(days=1)
        cert = self._make_certificate(
            status=Certificate.Status.ISSUED,
            expires_at=past,
            number_suffix="EXP",
        )
        self.client.force_login(self.owner)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # File missing
    # ------------------------------------------------------------------
    def test_download_no_file_404(self):
        """Issued cert without a file returns 404 from not_available template."""
        cert = self._make_certificate(with_file=False, number_suffix="NOF")
        self.client.force_login(self.owner)
        url = reverse("certifications:download", args=[cert.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_download_file_not_found_on_storage_returns_404(self):
        """If the FieldFile points to a missing blob, view returns 404."""
        cert = self._make_certificate(number_suffix="FNF")
        self.client.force_login(self.owner)
        url = reverse("certifications:download", args=[cert.id])

        # Simulate the underlying storage not having the file anymore.
        with patch.object(
            cert.certificate_file.storage,
            "open",
            side_effect=FileNotFoundError(),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
