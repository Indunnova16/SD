"""
Tests for SD#43 — 3 bugs in the certificados module reported by the client:

  B1: Certificate.verification_url used a hardcoded fallback domain
      ('https://lms.sd.com.co') AND the wrong path segment
      ('/certificates/verify/' instead of the real
      '/certifications/verify/<str:certificate_number>/' mounted in
      apps/certifications/urls.py + config/urls.py). SITE_URL is now
      defaulted in config/settings/cloudrun.py.

  B3: the post_save signal that auto-issues a certificate on Enrollment
      completion only checked whether ANY ISSUED certificate existed for
      (user, course), without comparing dates. After a course is reassigned
      (apps/accounts/views.py::reassign_enrollment) and completed again, the
      newer completion left the OLD certificate untouched instead of
      reissuing it (reproduced in prod with certificates.id=20,
      user_id=4/course_id=63: issued_at=2026-06-29 21:45:44 predates the
      recompletion's completed_at=2026-06-29 22:23:03 after a
      reset_reason='Reasignación por administrador' CompletionRecord).

B2 (Course.duration_hours) is covered separately in
apps/courses/tests/test_issue_43.py since it's a Course model concern.
"""

import re
from datetime import date, timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate, CertificateTemplate
from apps.certifications.services import CertificateService
from apps.courses.models import Course, Enrollment


def mock_generate_certificate_file(certificate):
    """Mock that skips PDF/QR generation and just marks the cert as issued.

    Mirrors apps/certifications/tests/test_signals.py's helper so signal
    tests don't depend on weasyprint/qrcode being importable in the test env.
    """
    certificate.status = Certificate.Status.ISSUED
    certificate.issued_at = timezone.now()
    certificate.verification_url = (
        f"https://example.com/certifications/verify/{certificate.certificate_number}/"
    )
    certificate.save()
    return certificate


class VerificationUrlPathTest(TestCase):
    """B1: verification_url must use '/certifications/verify/', not '/certificates/verify/'."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-issue43@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000101",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user-issue43@test.com",
            password="testpass123",
            first_name="Ana",
            last_name="Gomez",
            document_number="900000102",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.course = Course.objects.create(
            code="ISSUE43-001",
            title="Curso Issue 43",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )

    @patch.object(CertificateService, "_generate_pdf")
    @patch.object(CertificateService, "_generate_qr_code")
    def test_verification_url_uses_certifications_path(self, mock_qr, mock_pdf):
        """
        Regression test for the hardcoded '/certificates/verify/' segment.
        Real URLs are mounted at
        '/certifications/verify/<str:certificate_number>/'
        (apps/certifications/urls.py name='verify_number' + config/urls.py
        path("certifications/", include("apps.certifications.urls"))).
        Confirmed live in prod: curl .../certifications/verify/<num>/ -> 200
        vs .../certificates/verify/<num>/ -> 404.
        """
        certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-ISSUE43-00000001",
            status=Certificate.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=365),
        )

        CertificateService.generate_certificate_file(certificate)

        self.assertIn("/certifications/verify/", certificate.verification_url)
        self.assertNotIn("/certificates/verify/", certificate.verification_url)
        self.assertTrue(
            certificate.verification_url.endswith(
                f"/certifications/verify/{certificate.certificate_number}/"
            )
        )

    @override_settings(SITE_URL="https://sd-lms-rvfp6uj2va-uc.a.run.app")
    @patch.object(CertificateService, "_generate_pdf")
    @patch.object(CertificateService, "_generate_qr_code")
    def test_verification_url_honors_site_url_setting(self, mock_qr, mock_pdf):
        """When SITE_URL is configured, it's used verbatim as the domain."""
        certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-ISSUE43-00000002",
            status=Certificate.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=365),
        )

        CertificateService.generate_certificate_file(certificate)

        self.assertEqual(
            certificate.verification_url,
            "https://sd-lms-rvfp6uj2va-uc.a.run.app/certifications/verify/"
            f"{certificate.certificate_number}/",
        )

    def test_preview_template_sample_data_uses_certifications_path(self):
        """Cosmetic fix: the preview sample data must match the real path too.

        certificate_template.html renders {{ verification_url }} as plain
        text ("Verificar en {{ verification_url }}"), so the wrong hardcoded
        path in CertificateTemplateService.preview_template's default_data
        would leak into the rendered preview HTML.
        """
        from apps.certifications.services import CertificateTemplateService

        template = CertificateTemplate.objects.create(
            name="Preview Template Issue 43",
            signer_name="Director",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )
        # No template_file attached -> preview_template falls back to
        # rendering the default certificate_template.html with its own
        # sample_data (the one containing the hardcoded verification_url).
        html = CertificateTemplateService.preview_template(template)
        self.assertIn("/certifications/verify/", html)
        self.assertNotIn("/certificates/verify/", html)


@patch.object(
    CertificateService,
    "generate_certificate_file",
    side_effect=mock_generate_certificate_file,
)
class ReissueOnRecompletionSignalTest(TransactionTestCase):
    """
    B3: the signal must reissue (not silently skip) when an existing ISSUED
    certificate predates the enrollment's current completed_at (reassign +
    recomplete cycle). Uses TransactionTestCase so on_commit callbacks fire.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-issue43-signal@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000201",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user-issue43-signal@test.com",
            password="testpass123",
            first_name="Carlos",
            last_name="Ruiz",
            document_number="900000202",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.course = Course.objects.create(
            code="ISSUE43-SIG-001",
            title="Curso Issue 43 Signal",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        self.template = CertificateTemplate.objects.create(
            name="Default Template (issue 43)",
            signer_name="Director",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )

    def test_signal_reissues_stale_certificate_after_reassignment(self, mock_gen):
        """
        Reproduces the real prod case (certificates.id=20, user_id=4,
        course_id=63): a certificate ISSUED at T0 must be revoked and
        reissued when the enrollment completes again at T1 > T0 (e.g. after
        accounts.views.reassign_enrollment resets progress).
        """
        t0 = timezone.now() - timedelta(hours=1)
        t1 = timezone.now()

        # First completion at t0 -> signal issues certificate #1.
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
            completed_at=t0,
        )
        first_cert = Certificate.objects.get(user=self.user, course=self.course)
        self.assertEqual(first_cert.status, Certificate.Status.ISSUED)
        # The mocked generator stamps issued_at=now(); force it to t0 to
        # deterministically reproduce "cert issued before the 2nd completion".
        Certificate.objects.filter(pk=first_cert.pk).update(issued_at=t0)

        # Reassignment resets the enrollment (mirrors reassign_enrollment).
        enrollment.status = Enrollment.Status.ENROLLED
        enrollment.progress = 0
        enrollment.completed_at = None
        enrollment.save()

        # Still only the original certificate; no new one issued on reset.
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )

        # Recompletion at t1 (after the original cert's issued_at).
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.progress = 100
        enrollment.completed_at = t1
        enrollment.save()

        certs = Certificate.objects.filter(user=self.user, course=self.course).order_by(
            "created_at"
        )
        self.assertEqual(certs.count(), 2)

        first_cert.refresh_from_db()
        self.assertEqual(first_cert.status, Certificate.Status.REVOKED)

        new_cert = certs.exclude(pk=first_cert.pk).get()
        self.assertEqual(new_cert.status, Certificate.Status.ISSUED)
        self.assertEqual(
            new_cert.metadata.get("reissued_from"), first_cert.certificate_number
        )

    def test_signal_skips_when_existing_certificate_is_still_current(self, mock_gen):
        """
        Guard rail: if the enrollment's completed_at does NOT postdate the
        existing certificate's issued_at (e.g. simple re-save, no reassign
        cycle happened), the signal must NOT reissue.
        """
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )

        # Re-save without changing status/completed_at -> still 1 cert.
        enrollment.save()
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )
        cert = Certificate.objects.get(user=self.user, course=self.course)
        self.assertEqual(cert.status, Certificate.Status.ISSUED)

    def test_signal_does_not_reissue_when_completed_at_is_none(self, mock_gen):
        """Defensive: a COMPLETED enrollment with completed_at=None must not crash
        the date comparison and must not trigger a reissue."""
        # Pre-seed an ISSUED certificate directly (simulating legacy data).
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-PRESEED-ISSUE43-01",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=365),
        )

        # completed_at intentionally left None.
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
            completed_at=None,
        )

        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )


class ReassignEnrollmentViewReissueTest(TransactionTestCase):
    """
    Full-cycle integration test through the real
    accounts.views.reassign_enrollment view (the actual production entry
    point that resets an enrollment), followed by recompletion, verifying the
    stale certificate left over from the FIRST completion gets reissued.
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff-issue43-reassign@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="Staff",
            document_number="900000301",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user-issue43-reassign@test.com",
            password="testpass123",
            first_name="Laura",
            last_name="Diaz",
            document_number="900000302",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.course = Course.objects.create(
            code="ISSUE43-REASSIGN-001",
            title="Curso Issue 43 Reassign",
            created_by=self.staff,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        CertificateTemplate.objects.create(
            name="Default Template (reassign)",
            signer_name="Director",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )

    @patch.object(
        CertificateService,
        "generate_certificate_file",
        side_effect=mock_generate_certificate_file,
    )
    def test_reassign_then_recomplete_reissues_certificate(self, mock_gen):
        t0 = timezone.now() - timedelta(hours=2)

        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
            completed_at=t0,
        )
        first_cert = Certificate.objects.get(user=self.user, course=self.course)
        Certificate.objects.filter(pk=first_cert.pk).update(issued_at=t0)

        # Staff reassigns the course via the real view.
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse(
                "accounts:reassign_enrollment",
                args=[self.user.id, enrollment.id],
            )
        )
        self.assertEqual(resp.status_code, 302)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(enrollment.completed_at)

        # No new certificate yet — only the reset happened.
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )

        # User completes the course again, after the reassignment.
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.progress = 100
        enrollment.completed_at = timezone.now()
        enrollment.save()

        certs = Certificate.objects.filter(user=self.user, course=self.course)
        self.assertEqual(certs.count(), 2)
        first_cert.refresh_from_db()
        self.assertEqual(first_cert.status, Certificate.Status.REVOKED)
        self.assertTrue(
            certs.filter(status=Certificate.Status.ISSUED).exists(),
            "expected a fresh ISSUED certificate after recompletion post-reassignment",
        )


# Minimal valid PDF content, same pattern used by test_download.py, to give
# the older ("still visible/downloadable") certificate a real attached file —
# without it the pre-existing template gate
# (`certificate.certificate_file and certificate.status == 'issued'`) hides
# the download link regardless of status, which isn't the scenario SD#43
# describes (the OLD cert is a real, already-downloadable certificate).
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

# Matches the pending-notice <div ...> ONLY as an HTML tag attribute — not the
# always-present `[data-certificate-pending="true"]` CSS selector string
# embedded in the auto-refresh <script> (see extra_js block), which would
# otherwise produce a false positive on a plain substring check.
PENDING_MARKER_TAG_RE = re.compile(r'<div[^>]*\bdata-certificate-pending="true"[^>]*>')


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class MyCertificatesPendingIndicatorTest(TestCase):
    """
    UX mitigation (F2/F3, SD#43 reproceso round 2): F2 REFUTED F1's silent-
    rollback hypothesis with hard evidence (psql against prod, 48h Cloud Run
    logs, live HTTP download+pdftotext of 2 real certificates) — the
    generation pipeline works correctly end to end. The most plausible
    explanation for what the client saw is a ~3.5s timing window between
    Enrollment.completed_at and Certificate.status flipping to 'issued'
    (transaction.on_commit + weasyprint render), during which the NEW
    certificate exists with status=PENDING (no download button, template
    gates on status=='issued') while an OLDER certificate from a different
    course remains fully visible/downloadable on the same page with no
    indicator explaining the missing new one.

    These tests cover the UX mitigation only (explicit pending notice +
    bounded auto-refresh marker in my_certificates.html) — they do not (and
    cannot) reproduce the transitory timing window itself.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="user-issue43-pending@test.com",
            password="testpass123",
            first_name="Marta",
            last_name="Lopez",
            document_number="900000401",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.old_course = Course.objects.create(
            code="ISSUE43-PEND-OLD",
            title="Curso Viejo Issue 43",
            created_by=self.user,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        self.new_course = Course.objects.create(
            code="ISSUE43-PEND-NEW",
            title="Curso Nuevo Issue 43",
            created_by=self.user,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        # Older certificate, fully issued AND with a real file attached, so
        # it renders as downloadable — mirrors the real prod case (user_id=2
        # had an ISSUED+downloadable certificate for course 63 while course
        # 68's certificate was still generating).
        self.old_cert = Certificate.objects.create(
            user=self.user,
            course=self.old_course,
            certificate_number="SD-ISSUE43-PEND-OLD",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=20),
            expires_at=timezone.now() + timedelta(days=345),
        )
        self.old_cert.certificate_file.save(
            f"{self.old_cert.certificate_number}.pdf",
            ContentFile(MINIMAL_PDF),
            save=True,
        )

    def test_pending_certificate_shows_generation_notice_and_poll_marker(self):
        """
        While the new certificate is still PENDING, the card must show an
        explicit notice and the pending-marker tag must render, instead of
        silently omitting the download button with no explanation — and the
        older certificate's download link must remain untouched (still
        visible), matching the real scenario.
        """
        new_cert = Certificate.objects.create(
            user=self.user,
            course=self.new_course,
            certificate_number="SD-ISSUE43-PEND-NEW",
            status=Certificate.Status.PENDING,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("certifications:my_certificates"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Certificado en generación")
        self.assertRegex(content, PENDING_MARKER_TAG_RE)
        # Bounded auto-refresh marker present (script only acts when the
        # pending-marker tag it queries for actually exists in the DOM).
        self.assertContains(response, "sd43CertPollStart")
        # The older certificate keeps its download link...
        self.assertContains(
            response, reverse("certifications:download", args=[self.old_cert.id])
        )
        # ...but the new PENDING certificate must not offer one yet.
        self.assertNotContains(
            response, reverse("certifications:download", args=[new_cert.id])
        )

    def test_no_pending_certificates_omits_notice_and_marker_tag(self):
        """
        Baseline / regression guard: with no PENDING certificate (only the
        older ISSUED+downloadable one from setUp), neither the notice nor the
        pending-marker tag should render on any card — the auto-refresh
        script itself may still be present in the page (it self-gates via a
        DOM query and is a no-op with nothing to find), but it must find
        zero elements to act on.
        """
        self.client.force_login(self.user)
        response = self.client.get(reverse("certifications:my_certificates"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Certificado en generación")
        self.assertNotRegex(content, PENDING_MARKER_TAG_RE)
        # The older certificate's download link is present and untouched.
        self.assertContains(
            response, reverse("certifications:download", args=[self.old_cert.id])
        )
