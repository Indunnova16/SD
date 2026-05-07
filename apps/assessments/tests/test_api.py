"""
Tests for assessments API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.assessments.models import (
    Answer,
    Assessment,
    AssessmentAttempt,
    Question,
)
from apps.courses.models import Course


class AssessmentAPITests(TestCase):
    """Tests for Assessment API endpoints."""

    def setUp(self):
        # Clear existing data
        Assessment.objects.all().delete()
        Course.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="assesstest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.course = Course.objects.create(
            code="ASSESS-C1",
            title="Curso de Prueba",
            description="Descripción del curso",
            created_by=self.user,
        )

        self.assessment = Assessment.objects.create(
            title="Evaluación de Prueba",
            description="Descripción de la evaluación",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=70,
            time_limit=30,
            max_attempts=3,
            status=Assessment.Status.PUBLISHED,
            created_by=self.user,
        )

        self.question = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="¿Cuál es la respuesta correcta?",
            points=10,
            order=1,
        )

        self.correct_answer = Answer.objects.create(
            question=self.question,
            text="Respuesta correcta",
            is_correct=True,
            order=1,
        )

        self.wrong_answer = Answer.objects.create(
            question=self.question,
            text="Respuesta incorrecta",
            is_correct=False,
            order=2,
        )

    def test_list_assessments(self):
        """Test listing assessments."""
        url = reverse("assessments_api:assessment-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_filter_assessments_by_type(self):
        """Test filtering assessments by type."""
        url = reverse("assessments_api:assessment-list")
        response = self.client.get(url, {"type": "quiz"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_get_assessment_detail(self):
        """Test getting assessment detail."""
        url = reverse("assessments_api:assessment-detail", args=[self.assessment.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Evaluación de Prueba")

    def test_create_assessment(self):
        """Test creating an assessment."""
        url = reverse("assessments_api:assessment-list")
        data = {
            "title": "Nueva Evaluación",
            "description": "Descripción nueva",
            "assessment_type": "exam",
            "course": self.course.id,
            "passing_score": 80,
            "time_limit": 60,
            "max_attempts": 2,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Assessment.objects.count(), 2)

    def test_publish_assessment(self):
        """Test publishing an assessment."""
        draft = Assessment.objects.create(
            title="Borrador",
            description="Descripción",
            assessment_type=Assessment.Type.QUIZ,
            status=Assessment.Status.DRAFT,
            created_by=self.user,
        )

        # Add a question (required for publishing)
        Question.objects.create(
            assessment=draft,
            question_type=Question.Type.TRUE_FALSE,
            text="¿Es verdad?",
            points=5,
        )

        url = reverse("assessments_api:assessment-publish", args=[draft.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Assessment.Status.PUBLISHED)

    def test_publish_empty_assessment_fails(self):
        """Test that publishing an empty assessment fails."""
        draft = Assessment.objects.create(
            title="Borrador vacío",
            description="Sin preguntas",
            assessment_type=Assessment.Type.QUIZ,
            status=Assessment.Status.DRAFT,
            created_by=self.user,
        )

        url = reverse("assessments_api:assessment-publish", args=[draft.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_assessment_questions(self):
        """Test getting assessment questions."""
        url = reverse("assessments_api:assessment-questions", args=[self.assessment.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class AssessmentAttemptAPITests(TestCase):
    """Tests for AssessmentAttempt API endpoints."""

    def setUp(self):
        # Clear existing data
        AssessmentAttempt.objects.all().delete()
        Assessment.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="attempttest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.course = Course.objects.create(
            code="ATTEMPT-C1",
            title="Curso de Intento",
            description="Descripción",
            created_by=self.user,
        )

        self.assessment = Assessment.objects.create(
            title="Evaluación para Intentos",
            description="Descripción",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=70,
            time_limit=30,
            max_attempts=2,
            status=Assessment.Status.PUBLISHED,
            created_by=self.user,
        )

        self.question = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta de prueba",
            points=10,
            order=1,
        )

        self.correct_answer = Answer.objects.create(
            question=self.question,
            text="Correcta",
            is_correct=True,
            order=1,
        )

        self.wrong_answer = Answer.objects.create(
            question=self.question,
            text="Incorrecta",
            is_correct=False,
            order=2,
        )

    def test_start_attempt(self):
        """Test starting an assessment attempt."""
        url = reverse("assessments_api:attempt-start")
        data = {"assessment_id": self.assessment.id}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AssessmentAttempt.objects.count(), 1)
        self.assertEqual(response.data["attempt_number"], 1)

    def test_start_attempt_returns_existing_in_progress(self):
        """Test that starting returns existing in-progress attempt."""
        # Create in-progress attempt
        attempt = AssessmentAttempt.objects.create(
            user=self.user,
            assessment=self.assessment,
            attempt_number=1,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        )

        url = reverse("assessments_api:attempt-start")
        data = {"assessment_id": self.assessment.id}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], attempt.id)

    def test_max_attempts_exceeded(self):
        """Test that max attempts is enforced."""
        # Create max attempts
        for i in range(2):
            AssessmentAttempt.objects.create(
                user=self.user,
                assessment=self.assessment,
                attempt_number=i + 1,
                status=AssessmentAttempt.Status.GRADED,
            )

        url = reverse("assessments_api:attempt-start")
        data = {"assessment_id": self.assessment.id}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_attempt(self):
        """Test submitting an attempt."""
        attempt = AssessmentAttempt.objects.create(
            user=self.user,
            assessment=self.assessment,
            attempt_number=1,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        )

        url = reverse("assessments_api:attempt-submit", args=[attempt.id])
        data = {
            "answers": [
                {
                    "question_id": self.question.id,
                    "selected_answer_ids": [self.correct_answer.id],
                }
            ],
            "time_spent": 120,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check response data for grading
        self.assertEqual(response.data["status"], "graded")
        self.assertIsNotNone(response.data["score"])

    def test_my_attempts(self):
        """Test getting user's attempts."""
        AssessmentAttempt.objects.create(
            user=self.user,
            assessment=self.assessment,
            attempt_number=1,
            status=AssessmentAttempt.Status.GRADED,
        )

        url = reverse("assessments_api:attempt-my-attempts")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class QuestionAPITests(TestCase):
    """Tests for Question API endpoints."""

    def setUp(self):
        # Clear existing data
        Assessment.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="questiontest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="32345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.assessment = Assessment.objects.create(
            title="Evaluación para Preguntas",
            description="Descripción",
            assessment_type=Assessment.Type.QUIZ,
            status=Assessment.Status.DRAFT,
            created_by=self.user,
        )

    def test_create_question_with_answers(self):
        """Test creating a question with answers directly."""
        # Create question and answers directly
        from apps.assessments.api.serializers import QuestionCreateSerializer

        data = {
            "question_type": "single_choice",
            "text": "Nueva pregunta",
            "points": 5,
            "answers": [
                {"text": "Respuesta 1", "order": 1},
                {"text": "Respuesta 2", "order": 2},
            ],
        }

        serializer = QuestionCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        # Manually create with assessment
        question = serializer.save(assessment=self.assessment)

        self.assertEqual(self.assessment.questions.count(), 1)
        self.assertEqual(question.answers.count(), 2)

    def test_list_questions(self):
        """Test listing questions for an assessment."""
        Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.TRUE_FALSE,
            text="Pregunta 1",
            points=5,
            order=1,
        )

        # Use direct URL path for nested router
        url = f"/api/v1/assessments/assessments/{self.assessment.id}/questions/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
