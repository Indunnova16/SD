"""
Tests for reports API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.reports.models import Dashboard, GeneratedReport, ReportTemplate


class ReportTemplateAPITests(TestCase):
    """Tests for ReportTemplate API endpoints."""

    def setUp(self):
        ReportTemplate.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="reportuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.admin = User.objects.create_user(
            email="reportadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="22345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.template = ReportTemplate.objects.create(
            name="Reporte de Capacitación",
            description="Reporte de progreso de capacitación",
            report_type=ReportTemplate.Type.TRAINING,
            default_format=ReportTemplate.Format.PDF,
            columns=[{"name": "usuario", "type": "string"}],
            filters=[{"name": "fecha", "type": "date"}],
            is_active=True,
            created_by=self.admin,
        )

    def test_list_templates(self):
        """Test listing report templates."""
        url = reverse("reports_api:template-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_template_as_admin(self):
        """Test creating a template as admin."""
        self.client.force_authenticate(user=self.admin)
        url = reverse("reports_api:template-list")
        data = {
            "name": "Nuevo Reporte",
            "description": "Descripción",
            "report_type": "compliance",
            "default_format": "excel",
            "columns": [],
            "filters": [],
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ReportTemplate.objects.count(), 2)

    def test_create_template_as_user_forbidden(self):
        """Test that regular users cannot create templates."""
        url = reverse("reports_api:template-list")
        data = {
            "name": "Nuevo Reporte",
            "report_type": "training",
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GeneratedReportAPITests(TestCase):
    """Tests for GeneratedReport API endpoints."""

    def setUp(self):
        GeneratedReport.objects.all().delete()
        ReportTemplate.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="genreportuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="32345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.template = ReportTemplate.objects.create(
            name="Reporte de Prueba",
            report_type=ReportTemplate.Type.TRAINING,
            is_active=True,
            created_by=self.user,
        )

        self.report = GeneratedReport.objects.create(
            template=self.template,
            name="Reporte Generado",
            format=ReportTemplate.Format.PDF,
            status=GeneratedReport.Status.COMPLETED,
            generated_by=self.user,
        )

    def test_list_reports(self):
        """Test listing generated reports."""
        url = reverse("reports_api:generated-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_generate_report(self):
        """Test generating a report."""
        url = reverse("reports_api:generated-generate")
        data = {
            "template_id": self.template.id,
            "name": "Mi Reporte",
            "format": "excel",
            "filters": {"fecha": "2024-01-01"},
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(GeneratedReport.objects.count(), 2)

    def test_my_reports(self):
        """Test getting user's reports."""
        url = reverse("reports_api:generated-my-reports")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class DashboardAPITests(TestCase):
    """Tests for Dashboard API endpoints."""

    def setUp(self):
        Dashboard.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="dashboardadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="42345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

        self.dashboard = Dashboard.objects.create(
            name="Dashboard Principal",
            description="Dashboard de métricas principales",
            is_default=True,
            is_active=True,
            is_public=True,
            layout={"type": "grid"},
            widgets=[{"type": "chart", "title": "Gráfico 1"}],
            created_by=self.admin,
        )

    def test_list_dashboards(self):
        """Test listing dashboards."""
        url = reverse("reports_api:dashboard-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_dashboard(self):
        """Test creating a dashboard."""
        url = reverse("reports_api:dashboard-list")
        data = {
            "name": "Nuevo Dashboard",
            "description": "Descripción",
            "layout": {},
            "widgets": [],
            "is_public": False,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dashboard.objects.count(), 2)

    def test_get_default_dashboard(self):
        """Test getting default dashboard."""
        url = reverse("reports_api:dashboard-default")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Dashboard Principal")

    def test_duplicate_dashboard(self):
        """Test duplicating a dashboard."""
        url = reverse("reports_api:dashboard-duplicate", args=[self.dashboard.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dashboard.objects.count(), 2)
        self.assertIn("(copia)", response.data["name"])
