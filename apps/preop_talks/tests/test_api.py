"""
Tests for pre-operational talks API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.preop_talks.models import PreopTalk, TalkAttendee, TalkTemplate


class TalkTemplateAPITests(TestCase):
    """Tests for TalkTemplate API endpoints."""

    def setUp(self):
        TalkTemplate.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="talktemplate@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.template = TalkTemplate.objects.create(
            title="Charla de Seguridad",
            description="Charla diaria de seguridad",
            talk_type=TalkTemplate.Type.DAILY,
            content="Contenido de la charla",
            key_points=["Punto 1", "Punto 2"],
            safety_topics=["EPP", "Trabajo en alturas"],
            estimated_duration=15,
            created_by=self.user,
        )

    def test_list_templates(self):
        """Test listing templates."""
        url = reverse("preop_talks_api:template-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_template(self):
        """Test creating a template."""
        url = reverse("preop_talks_api:template-list")
        data = {
            "title": "Nueva Plantilla",
            "description": "Descripción",
            "talk_type": "weekly",
            "content": "Contenido",
            "key_points": ["Punto 1"],
            "safety_topics": ["Tema 1"],
            "estimated_duration": 20,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TalkTemplate.objects.count(), 2)

    def test_filter_by_type(self):
        """Test filtering templates by type."""
        url = reverse("preop_talks_api:template-list")
        response = self.client.get(url, {"type": "daily"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)


class PreopTalkAPITests(TestCase):
    """Tests for PreopTalk API endpoints."""

    def setUp(self):
        PreopTalk.objects.all().delete()
        TalkTemplate.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="talkuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.supervisor = User.objects.create_user(
            email="talksupervisor@example.com",
            password="testpass123",
            first_name="Super",
            last_name="Visor",
            document_number="32345678",
            job_position="Supervisor",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.template = TalkTemplate.objects.create(
            title="Charla de Seguridad",
            description="Charla diaria",
            talk_type=TalkTemplate.Type.DAILY,
            content="Contenido",
            key_points=["Punto 1"],
            created_by=self.user,
        )

        self.talk = PreopTalk.objects.create(
            template=self.template,
            title="Charla del día",
            content="Contenido de la charla",
            key_points=["Punto 1"],
            status=PreopTalk.Status.SCHEDULED,
            project_name="Proyecto X",
            location="Ubicación Y",
            work_activity="Mantenimiento",
            scheduled_at=timezone.now(),
            conducted_by=self.user,
            supervisor=self.supervisor,
        )

    def test_list_talks(self):
        """Test listing talks."""
        url = reverse("preop_talks_api:talk-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_talk(self):
        """Test creating a talk."""
        url = reverse("preop_talks_api:talk-list")
        data = {
            "template": self.template.id,
            "title": "Nueva Charla",
            "content": "Contenido",
            "key_points": ["Punto 1"],
            "project_name": "Proyecto Z",
            "location": "Ubicación Z",
            "work_activity": "Instalación",
            "scheduled_at": timezone.now().isoformat(),
            "supervisor": self.supervisor.id,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PreopTalk.objects.count(), 2)

    def test_start_talk(self):
        """Test starting a talk."""
        url = reverse("preop_talks_api:talk-start", args=[self.talk.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.talk.refresh_from_db()
        self.assertEqual(self.talk.status, PreopTalk.Status.IN_PROGRESS)
        self.assertIsNotNone(self.talk.started_at)

    def test_complete_talk(self):
        """Test completing a talk."""
        # First start the talk
        self.talk.status = PreopTalk.Status.IN_PROGRESS
        self.talk.started_at = timezone.now()
        self.talk.save()

        url = reverse("preop_talks_api:talk-complete", args=[self.talk.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.talk.refresh_from_db()
        self.assertEqual(self.talk.status, PreopTalk.Status.COMPLETED)
        self.assertIsNotNone(self.talk.completed_at)

    def test_add_attendees(self):
        """Test adding attendees to a talk."""
        url = reverse("preop_talks_api:talk-add-attendees", args=[self.talk.id])
        data = {"user_ids": [self.supervisor.id]}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["added"], 1)
        self.assertEqual(self.talk.attendees.count(), 1)

    def test_sign_attendance(self):
        """Test signing attendance."""
        # Add user as attendee
        TalkAttendee.objects.create(talk=self.talk, user=self.user)

        url = reverse("preop_talks_api:talk-sign", args=[self.talk.id])
        data = {"understood_content": True, "comments": "Entendido"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attendee = TalkAttendee.objects.get(talk=self.talk, user=self.user)
        self.assertIsNotNone(attendee.signed_at)

    def test_my_talks(self):
        """Test getting user's conducted talks."""
        url = reverse("preop_talks_api:talk-my-talks")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_today_talks(self):
        """Test getting today's talks."""
        url = reverse("preop_talks_api:talk-today")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_talk_report(self):
        """Test getting talk report."""
        # Add attendee
        TalkAttendee.objects.create(talk=self.talk, user=self.supervisor)

        url = reverse("preop_talks_api:talk-report", args=[self.talk.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("statistics", response.data)
        self.assertEqual(response.data["statistics"]["total_attendees"], 1)
