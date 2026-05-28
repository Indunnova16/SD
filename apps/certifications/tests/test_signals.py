"""
Tests for certifications signals.

Covers the post_save Enrollment -> auto-issue Certificate signal
(`issue_certificate_on_enrollment_completed`).

Uses TransactionTestCase so that `transaction.on_commit` callbacks fire
during the test (TestCase wraps each test in a never-committed transaction,
which would swallow the callback).
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate, CertificateTemplate
from apps.certifications.services import CertificateService
from apps.courses.models import Course, Enrollment


def mock_generate_certificate_file(certificate):
    """Mock that skips PDF/QR generation and just marks the cert as issued."""
    certificate.status = Certificate.Status.ISSUED
    certificate.issued_at = timezone.now()
    certificate.verification_url = (
        f"https://example.com/verify/{certificate.certificate_number}/"
    )
    certificate.save()
    return certificate


@patch.object(
    CertificateService,
    "generate_certificate_file",
    side_effect=mock_generate_certificate_file,
)
class EnrollmentCompletionSignalTest(TransactionTestCase):
    """Tests for issue_certificate_on_enrollment_completed signal."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-signals@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000001",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user-signals@test.com",
            password="testpass123",
            first_name="Juan",
            last_name="Perez",
            document_number="900000002",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.course = Course.objects.create(
            code="SIG-001",
            title="Signal Test Course",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        self.template = CertificateTemplate.objects.create(
            name="Default Template (signals)",
            signer_name="Director",
            signer_title="S.D. S.A.S.",
            is_active=True,
        )

    def test_signal_issues_certificate_on_completed(self, mock_gen):
        """When enrollment goes IN_PROGRESS -> COMPLETED, a cert is issued."""
        enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            progress=50,
        )

        # No cert yet (status != COMPLETED)
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            0,
        )

        # Transition to COMPLETED -> signal should fire on commit
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.progress = 100
        enrollment.save()

        certs = Certificate.objects.filter(user=self.user, course=self.course)
        self.assertEqual(certs.count(), 1)
        self.assertEqual(certs.first().status, Certificate.Status.ISSUED)

    def test_signal_idempotent(self, mock_gen):
        """Re-saving a COMPLETED enrollment does not duplicate the certificate."""
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

        # Re-save without changing status -> still 1 cert
        enrollment.save()
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )

    def test_signal_skips_when_not_completed(self, mock_gen):
        """No cert is issued when enrollment is created in IN_PROGRESS."""
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            progress=50,
        )

        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            0,
        )

    def test_signal_skips_when_existing_issued_cert(self, mock_gen):
        """If a valid ISSUED cert already exists, signal does not create another."""
        # Pre-create an ISSUED certificate manually
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-PRESEED-00000001",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=365),
        )
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )

        # Now flip the enrollment to COMPLETED
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )

        # Still exactly 1 cert (the pre-seeded one); signal short-circuited.
        self.assertEqual(
            Certificate.objects.filter(user=self.user, course=self.course).count(),
            1,
        )
