"""
Tests for certifications API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.certifications.models import Certificate, CertificateTemplate
from apps.courses.models import Course


class CertificateTemplateAPITests(TestCase):
    """Tests for CertificateTemplate API endpoints."""

    def setUp(self):
        # Clear existing data
        CertificateTemplate.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="templatetest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.template = CertificateTemplate.objects.create(
            name="Plantilla Estándar",
            description="Plantilla de certificado estándar",
            signer_name="Director de Capacitación",
            signer_title="Director",
            is_active=True,
        )

    def test_list_templates(self):
        """Test listing certificate templates."""
        url = reverse("certifications_api:template-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_filter_active_templates(self):
        """Test filtering active templates."""
        CertificateTemplate.objects.create(
            name="Plantilla Inactiva",
            description="No activa",
            is_active=False,
        )

        url = reverse("certifications_api:template-list")
        response = self.client.get(url, {"active": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_get_template_detail(self):
        """Test getting template detail."""
        url = reverse("certifications_api:template-detail", args=[self.template.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Plantilla Estándar")


class CertificateAPITests(TestCase):
    """Tests for Certificate API endpoints."""

    def setUp(self):
        # Clear existing data
        Certificate.objects.all().delete()
        Course.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="certadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="12345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="certuser@example.com",
            password="testpass123",
            first_name="Regular",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.admin)

        self.course = Course.objects.create(
            code="CERT-C1",
            title="Curso con Certificado",
            description="Descripción del curso",
            created_by=self.admin,
        )

        self.template = CertificateTemplate.objects.create(
            name="Plantilla Test",
            description="Para tests",
            is_active=True,
        )

    def test_issue_certificate(self):
        """Test issuing a certificate."""
        url = reverse("certifications_api:certificate-issue")
        data = {
            "user_id": self.user.id,
            "course_id": self.course.id,
            "template_id": self.template.id,
            "score": 95.5,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Certificate.objects.count(), 1)
        certificate = Certificate.objects.first()
        self.assertEqual(certificate.status, Certificate.Status.ISSUED)
        self.assertIsNotNone(certificate.certificate_number)

    def test_issue_duplicate_certificate_fails(self):
        """Test that issuing duplicate certificate fails."""
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-TEST0001",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )

        url = reverse("certifications_api:certificate-issue")
        data = {
            "user_id": self.user.id,
            "course_id": self.course.id,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revoke_certificate(self):
        """Test revoking a certificate."""
        certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-TEST0002",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )

        url = reverse("certifications_api:certificate-revoke", args=[certificate.id])
        data = {"reason": "Fraude detectado"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        certificate.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.REVOKED)
        self.assertEqual(certificate.revoked_reason, "Fraude detectado")

    def test_verify_certificate(self):
        """Test verifying a certificate."""
        certificate = Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-VERIFY01",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )

        url = reverse("certifications_api:certificate-verify")
        data = {"certificate_number": "SD-2024-VERIFY01"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["certificate_number"], "SD-2024-VERIFY01")

    def test_verify_nonexistent_certificate(self):
        """Test verifying a nonexistent certificate."""
        url = reverse("certifications_api:certificate-verify")
        data = {"certificate_number": "INVALID-NUMBER"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["valid"])

    def test_my_certificates(self):
        """Test getting user's certificates."""
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-MYCERT01",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("certifications_api:certificate-my-certificates")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_certificates_as_staff(self):
        """Test that staff can list all certificates."""
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-LIST01",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )

        url = reverse("certifications_api:certificate-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_filter_certificates_by_status(self):
        """Test filtering certificates by status."""
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-FILTER01",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )
        Certificate.objects.create(
            user=self.user,
            course=self.course,
            certificate_number="SD-2024-FILTER02",
            status=Certificate.Status.REVOKED,
        )

        url = reverse("certifications_api:certificate-list")
        response = self.client.get(url, {"status": "issued"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_non_staff_issue_fails(self):
        """Test that non-staff cannot issue certificates."""
        self.client.force_authenticate(user=self.user)

        url = reverse("certifications_api:certificate-issue")
        data = {
            "user_id": self.user.id,
            "course_id": self.course.id,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
