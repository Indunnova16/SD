"""
Tests for integrations API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.integrations.models import (
    DataMapping,
    ExternalSystem,
    IntegrationLog,
    Webhook,
    WebhookDelivery,
)


class ExternalSystemAPITests(TestCase):
    """Tests for ExternalSystem API endpoints."""

    def setUp(self):
        ExternalSystem.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="systemadmin@example.com",
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
            email="systemuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.admin)

        self.system = ExternalSystem.objects.create(
            name="Sistema de RH",
            code="HR_SYSTEM",
            system_type=ExternalSystem.Type.HR,
            base_url="https://hr.example.com/api",
            auth_type="bearer",
            is_active=True,
        )

    def test_list_systems(self):
        """Test listing external systems."""
        url = reverse("integrations_api:system-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_system(self):
        """Test creating an external system."""
        url = reverse("integrations_api:system-list")
        data = {
            "name": "ERP Sistema",
            "code": "ERP_SYSTEM",
            "system_type": "erp",
            "base_url": "https://erp.example.com/api",
            "auth_type": "api_key",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ExternalSystem.objects.count(), 2)

    def test_non_staff_cannot_access(self):
        """Test that non-staff users cannot access systems."""
        self.client.force_authenticate(user=self.user)
        url = reverse("integrations_api:system-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_test_connection(self):
        """Test testing connection to external system."""
        url = reverse("integrations_api:system-test-connection", args=[self.system.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

    def test_toggle_active(self):
        """Test toggling system active status."""
        url = reverse("integrations_api:system-toggle-active", args=[self.system.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.system.refresh_from_db()
        self.assertFalse(self.system.is_active)


class IntegrationLogAPITests(TestCase):
    """Tests for IntegrationLog API endpoints."""

    def setUp(self):
        IntegrationLog.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="logadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="32345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

        self.system = ExternalSystem.objects.create(
            name="Sistema de Prueba",
            code="TEST_SYSTEM",
            system_type=ExternalSystem.Type.API,
        )

        self.log = IntegrationLog.objects.create(
            external_system=self.system,
            operation="sync_users",
            direction=IntegrationLog.Direction.INBOUND,
            status=IntegrationLog.Status.SUCCESS,
            records_processed=50,
            duration_ms=1500,
        )

    def test_list_logs(self):
        """Test listing integration logs."""
        url = reverse("integrations_api:log-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_get_stats(self):
        """Test getting integration statistics."""
        url = reverse("integrations_api:log-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total", response.data)
        self.assertIn("successful", response.data)


class DataMappingAPITests(TestCase):
    """Tests for DataMapping API endpoints."""

    def setUp(self):
        DataMapping.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="mappingadmin@example.com",
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

        self.system = ExternalSystem.objects.create(
            name="Sistema de Prueba",
            code="TEST_SYSTEM",
            system_type=ExternalSystem.Type.HR,
        )

        self.mapping = DataMapping.objects.create(
            external_system=self.system,
            entity_type="user",
            external_field="employee_id",
            internal_field="document_number",
            is_required=True,
            is_active=True,
        )

    def test_list_mappings(self):
        """Test listing data mappings."""
        url = reverse("integrations_api:mapping-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_mapping(self):
        """Test creating a data mapping."""
        url = reverse("integrations_api:mapping-list")
        data = {
            "external_system": self.system.id,
            "entity_type": "user",
            "external_field": "full_name",
            "internal_field": "first_name",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DataMapping.objects.count(), 2)

    def test_get_entity_types(self):
        """Test getting available entity types."""
        url = reverse("integrations_api:mapping-entity-types")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)


class WebhookAPITests(TestCase):
    """Tests for Webhook API endpoints."""

    def setUp(self):
        Webhook.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="webhookadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="52345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

        self.webhook = Webhook.objects.create(
            name="Webhook de Prueba",
            url="https://example.com/webhook",
            events=["user_created", "course_completed"],
            is_active=True,
            created_by=self.admin,
        )

    def test_list_webhooks(self):
        """Test listing webhooks."""
        url = reverse("integrations_api:webhook-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_webhook(self):
        """Test creating a webhook."""
        url = reverse("integrations_api:webhook-list")
        data = {
            "name": "Nuevo Webhook",
            "url": "https://example.com/new-webhook",
            "events": ["certificate_issued"],
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Webhook.objects.count(), 2)

    def test_test_webhook(self):
        """Test testing a webhook."""
        url = reverse("integrations_api:webhook-test", args=[self.webhook.id])
        data = {
            "event": "user_created",
            "payload": {"user_id": 1},
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

    def test_toggle_webhook_active(self):
        """Test toggling webhook active status."""
        url = reverse("integrations_api:webhook-toggle-active", args=[self.webhook.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.webhook.refresh_from_db()
        self.assertFalse(self.webhook.is_active)


class WebhookDeliveryAPITests(TestCase):
    """Tests for WebhookDelivery API endpoints."""

    def setUp(self):
        WebhookDelivery.objects.all().delete()

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="deliveryadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="62345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

        self.webhook = Webhook.objects.create(
            name="Webhook de Prueba",
            url="https://example.com/webhook",
            events=["user_created"],
            created_by=self.admin,
        )

        self.delivery = WebhookDelivery.objects.create(
            webhook=self.webhook,
            event="user_created",
            payload={"user_id": 1},
            status=WebhookDelivery.Status.FAILED,
            http_status=500,
            error_message="Internal Server Error",
        )

    def test_list_deliveries(self):
        """Test listing webhook deliveries."""
        url = reverse("integrations_api:delivery-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_retry_delivery(self):
        """Test retrying a failed delivery."""
        url = reverse("integrations_api:delivery-retry", args=[self.delivery.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.RETRYING)

    def test_get_pending_deliveries(self):
        """Test getting pending deliveries."""
        url = reverse("integrations_api:delivery-pending")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
