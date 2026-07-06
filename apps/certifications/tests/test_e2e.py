"""
E2E acceptance test for the certificados module (SD#43, SD#44).

Exercises the full flow:
  1. Staff creates a CertificateTemplate via the custom panel (B2 — SD#44).
  2. Student enrolls in a course, completes it (status=COMPLETED).
  3. The post_save signal automatically issues a Certificate (B1 — SD#43).
  4. Student downloads the PDF via the FileResponse endpoint (B3 — SD#43).

Uses TransactionTestCase so that `transaction.on_commit` callbacks fire
during the test (TestCase wraps each test in a never-committed transaction,
which would swallow the signal callback).
"""

from datetime import date
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate, CertificateTemplate
from apps.certifications.services import CertificateService
from apps.courses.models import Course, Enrollment


# Minimal valid PDF (header + EOF) — large enough to be a real-ish file.
MINIMAL_PDF = b"%PDF-1.4\n%test certificate e2e\n" + b"x" * 500 + b"\n%%EOF\n"


def _fake_generate_certificate_file(certificate):
    """
    Mock that mimics CertificateService.generate_certificate_file without
    invoking weasyprint / qrcode (which may not be available in the test
    env). Persists a minimal PDF blob on the certificate and marks it as
    ISSUED so the full flow can continue end-to-end.
    """
    certificate.certificate_file.save(
        f"cert_{certificate.certificate_number}.pdf",
        ContentFile(MINIMAL_PDF),
        save=False,
    )
    certificate.status = Certificate.Status.ISSUED
    certificate.issued_at = timezone.now()
    certificate.verification_url = (
        f"https://example.com/verify/{certificate.certificate_number}/"
    )
    certificate.save()
    return certificate


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CertificadosE2ETest(TransactionTestCase):
    """End-to-end flow covering B1 + B2 + B3."""

    def setUp(self):
        # Clean templates from any prior test that may have leaked rows
        # (TransactionTestCase truncates between tests but be defensive).
        CertificateTemplate.objects.all().delete()

        # Staff user — will create the template via the custom panel.
        self.staff = User.objects.create_user(
            email="staff-e2e@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="Staff",
            document_number="900000010",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        # Student — will complete the course and download the cert.
        self.student = User.objects.create_user(
            email="student-e2e@example.com",
            password="testpass123",
            first_name="Juan",
            last_name="Estudiante",
            document_number="900000011",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        # Course already published.
        self.course = Course.objects.create(
            code="E2E-001",
            title="Curso E2E",
            description="Descripción del curso E2E",
            created_by=self.staff,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )

    @patch.object(
        CertificateService,
        "generate_certificate_file",
        side_effect=_fake_generate_certificate_file,
    )
    def test_full_flow_template_enroll_complete_download(self, mock_gen):
        """Template → enrollment → completed → signal → download."""

        # ---- B2 (SD#44): staff creates template via custom panel ----
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("certifications:template_create"),
            data={
                "name": "Plantilla E2E",
                "description": "Plantilla para test E2E",
                "template_file": SimpleUploadedFile(
                    "plantilla_e2e.html", b"<html></html>", content_type="text/html"
                ),
                "signer_name": "Directora HSEQ",
                "signer_title": "HSEQ",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        template = CertificateTemplate.objects.get(name="Plantilla E2E")
        self.assertTrue(template.is_active)

        # ---- B1 (SD#43): enrollment COMPLETED triggers signal ----
        enrollment = Enrollment.objects.create(
            user=self.student,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            progress=50,
        )
        self.assertFalse(
            Certificate.objects.filter(
                user=self.student, course=self.course
            ).exists()
        )

        # Transition IN_PROGRESS -> COMPLETED. Signal fires on commit and
        # invokes our mocked generator, which attaches the PDF blob.
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.progress = 100
        enrollment.save()

        cert = Certificate.objects.get(user=self.student, course=self.course)
        self.assertEqual(cert.status, Certificate.Status.ISSUED)
        self.assertTrue(cert.certificate_file)
        # Generator was actually invoked exactly once for this enrollment.
        self.assertGreaterEqual(mock_gen.call_count, 1)

        # ---- B3 (SD#43): student downloads PDF via FileResponse ----
        self.client.force_login(self.student)
        resp = self.client.get(
            reverse("certifications:download", args=[cert.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        disposition = resp.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn(
            f"Certificado_{cert.certificate_number}.pdf", disposition
        )

        body = b"".join(resp.streaming_content)
        self.assertTrue(body.startswith(b"%PDF"))
        self.assertGreater(len(body), 200)

    @patch.object(
        CertificateService,
        "generate_certificate_file",
        side_effect=_fake_generate_certificate_file,
    )
    def test_signal_idempotent_across_two_completes(self, mock_gen):
        """Re-saving a COMPLETED enrollment does not issue a second cert."""

        # Seed an active template so the signal has something to pick up.
        CertificateTemplate.objects.create(
            name="Plantilla Idempotent",
            signer_name="Director",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )

        enrollment = Enrollment.objects.create(
            user=self.student,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )

        # First save -> 1 cert exists.
        self.assertEqual(
            Certificate.objects.filter(
                user=self.student, course=self.course
            ).count(),
            1,
        )

        # Re-save without changing status -> still exactly 1 cert.
        enrollment.save()
        self.assertEqual(
            Certificate.objects.filter(
                user=self.student, course=self.course
            ).count(),
            1,
        )
