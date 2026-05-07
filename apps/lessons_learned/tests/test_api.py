"""
Tests for lessons learned API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.lessons_learned.models import Category, LessonLearned


class CategoryAPITests(TestCase):
    """Tests for Category API endpoints."""

    def setUp(self):
        Category.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="cattest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(
            name="Seguridad",
            description="Lecciones de seguridad",
        )

    def test_list_categories(self):
        """Test listing categories."""
        url = reverse("lessons_learned_api:category-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_category(self):
        """Test creating a category."""
        url = reverse("lessons_learned_api:category-list")
        data = {
            "name": "Mantenimiento",
            "description": "Lecciones de mantenimiento",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Category.objects.count(), 2)


class LessonLearnedAPITests(TestCase):
    """Tests for LessonLearned API endpoints."""

    def setUp(self):
        LessonLearned.objects.all().delete()
        Category.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="lessontest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.admin = User.objects.create_user(
            email="lessonadmin@example.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="32345678",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(
            name="Seguridad",
            description="Lecciones de seguridad",
        )

        self.lesson = LessonLearned.objects.create(
            title="Lección de Prueba",
            description="Descripción",
            category=self.category,
            lesson_type=LessonLearned.Type.OBSERVATION,
            severity=LessonLearned.Severity.MEDIUM,
            status=LessonLearned.Status.APPROVED,
            situation="Situación de prueba",
            lesson="Lección aprendida",
            recommendations="Recomendaciones",
            created_by=self.user,
        )

    def test_list_lessons(self):
        """Test listing lessons."""
        url = reverse("lessons_learned_api:lesson-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_lesson(self):
        """Test creating a lesson."""
        url = reverse("lessons_learned_api:lesson-list")
        data = {
            "title": "Nueva Lección",
            "description": "Nueva descripción",
            "category": self.category.id,
            "lesson_type": "incident",
            "severity": "high",
            "situation": "Situación",
            "lesson": "Lección",
            "recommendations": "Recomendaciones",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(LessonLearned.objects.count(), 2)

    def test_submit_for_review(self):
        """Test submitting lesson for review."""
        # Create a draft lesson
        draft = LessonLearned.objects.create(
            title="Borrador",
            description="Descripción",
            category=self.category,
            lesson_type=LessonLearned.Type.OBSERVATION,
            severity=LessonLearned.Severity.LOW,
            status=LessonLearned.Status.DRAFT,
            situation="Situación",
            lesson="Lección",
            recommendations="Recomendaciones",
            created_by=self.user,
        )

        url = reverse(
            "lessons_learned_api:lesson-submit-for-review",
            args=[draft.id],
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertEqual(draft.status, LessonLearned.Status.PENDING_REVIEW)

    def test_review_lesson_as_staff(self):
        """Test reviewing lesson as staff."""
        # Create pending lesson
        pending = LessonLearned.objects.create(
            title="Pendiente",
            description="Descripción",
            category=self.category,
            lesson_type=LessonLearned.Type.OBSERVATION,
            severity=LessonLearned.Severity.LOW,
            status=LessonLearned.Status.PENDING_REVIEW,
            situation="Situación",
            lesson="Lección",
            recommendations="Recomendaciones",
            created_by=self.user,
        )

        self.client.force_authenticate(user=self.admin)

        url = reverse("lessons_learned_api:lesson-review", args=[pending.id])
        data = {"action": "approve", "review_notes": "Aprobado"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pending.refresh_from_db()
        self.assertEqual(pending.status, LessonLearned.Status.APPROVED)

    def test_my_lessons(self):
        """Test getting user's lessons."""
        url = reverse("lessons_learned_api:lesson-my-lessons")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_severity(self):
        """Test filtering lessons by severity."""
        url = reverse("lessons_learned_api:lesson-list")
        response = self.client.get(url, {"severity": "medium"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
