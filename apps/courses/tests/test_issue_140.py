"""Regression coverage for assessment modality in SD#140."""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.courses.forms import QuickAssessmentForm
from apps.courses.models import Category, Course


class AssessmentModalityIssue140Tests(TestCase):
    """Modalidad is separate from assessment_type and editable by coordinators."""

    def setUp(self):
        self.client = Client()
        self.admin = self._user("admin140@test.com", User.Rol.ADMINISTRADOR)
        self.coordinator = self._user("coordinator140@test.com", User.Rol.COORDINADOR)
        self.executor = self._user("executor140@test.com", User.Rol.EJECUTOR)
        category = Category.objects.create(
            name="Categoría SD140", slug="categoria-sd140", description="", color="#123456"
        )
        self.course = Course.objects.create(
            code="SD140-COURSE",
            title="Curso SD140",
            description="",
            objectives="",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=category,
            created_by=self.admin,
        )
        self.create_url = reverse("courses:builder_create_quiz", args=[self.course.id])

    @staticmethod
    def _user(email, rol):
        return User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="SD",
            last_name="140",
            document_number=email.split("@")[0].replace("140", "")[-8:] or "14000000",
            job_position="QA",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            rol=rol,
        )

    @staticmethod
    def _payload(modality="oral"):
        return {
            "title": "Evaluación práctica",
            "assessment_type": Assessment.Type.EXAM,
            "modality": modality,
            "passing_score": "3.50",
            "time_limit": "30",
            "max_attempts": "2",
        }

    def test_coordinator_creates_oral_assessment_independent_of_type(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(self.create_url, self._payload("oral"))

        self.assertEqual(response.status_code, 302)
        assessment = Assessment.objects.get(course=self.course)
        self.assertEqual(assessment.assessment_type, Assessment.Type.EXAM)
        self.assertEqual(assessment.modality, Assessment.Modality.ORAL)

    def test_coordinator_updates_modality_and_editor_shows_all_choices(self):
        assessment = Assessment.objects.create(
            title="Registro legacy",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            created_by=self.admin,
        )
        edit_url = reverse("courses:builder_edit_assessment", args=[self.course.id, assessment.id])
        self.client.force_login(self.coordinator)

        get_response = self.client.get(edit_url)
        self.assertContains(get_response, "Modalidad")
        for label in ("Oral", "Escrita", "Otra"):
            self.assertContains(get_response, label)

        response = self.client.post(
            edit_url,
            {
                "title": assessment.title,
                "description": "",
                "assessment_type": Assessment.Type.QUIZ,
                "modality": Assessment.Modality.WRITTEN,
                "passing_score": "3.50",
                "time_limit": "",
                "max_attempts": "0",
                "status": Assessment.Status.DRAFT,
            },
        )
        self.assertEqual(response.status_code, 200)
        assessment.refresh_from_db()
        self.assertEqual(assessment.modality, Assessment.Modality.WRITTEN)

    def test_invalid_modality_is_rejected_and_executor_cannot_create(self):
        self.assertFalse(QuickAssessmentForm(data=self._payload("virtual")).is_valid())

        self.client.force_login(self.executor)
        response = self.client.post(self.create_url, self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Assessment.objects.filter(course=self.course).exists())

    def test_legacy_create_without_modality_defaults_to_other(self):
        assessment = Assessment.objects.create(
            title="Evaluación anterior",
            assessment_type=Assessment.Type.PRACTICE,
            course=self.course,
            created_by=self.admin,
            passing_score=Decimal("3.50"),
        )
        self.assertEqual(assessment.modality, Assessment.Modality.OTHER)
