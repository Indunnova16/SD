"""
Tests for assessments API endpoints.
"""

from datetime import date
from decimal import Decimal

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


class DecimalFormsAndBuilderTests(TestCase):
    """Forms + builder-view tests for decimal points support (issue #39)."""

    def setUp(self):
        from django.test import Client

        self.staff = User.objects.create_user(
            email="staff39@example.com",
            password="testpass123",
            first_name="Staff",
            last_name="User",
            document_number="3911111",
            job_position="Admin",
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.web = Client()
        self.web.force_login(self.staff)
        self.course = Course.objects.create(
            code="DECFORM-1",
            title="Curso Decimal",
            created_by=self.staff,
        )
        self.assessment = Assessment.objects.create(
            title="Eval Decimal",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=Decimal("80.00"),
            status=Assessment.Status.DRAFT,
            created_by=self.staff,
        )

    def test_quick_assessment_form_accepts_decimal_passing_score(self):
        from apps.courses.forms import QuickAssessmentForm

        form = QuickAssessmentForm(
            data={
                "title": "X",
                "assessment_type": "quiz",
                "passing_score": "75.5",
                "max_attempts": "3",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["passing_score"], Decimal("75.5"))

    def test_quick_assessment_form_rejects_over_100(self):
        from apps.courses.forms import QuickAssessmentForm

        form = QuickAssessmentForm(
            data={
                "title": "X",
                "assessment_type": "quiz",
                "passing_score": "100.5",
                "max_attempts": "3",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("passing_score", form.errors)

    def test_edit_form_accepts_decimal_and_not_localized(self):
        from apps.courses.forms import AssessmentEditForm

        form = AssessmentEditForm(instance=self.assessment)
        # Rendered widget value must use a dot (es-CO would otherwise emit "80,00")
        rendered = str(form["passing_score"])
        self.assertIn('value="80.00"', rendered)
        self.assertIn('step="0.01"', rendered)

        bound = AssessmentEditForm(
            data={
                "title": "Eval Decimal",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": "62.75",
                "max_attempts": "3",
                "status": "draft",
            },
            instance=self.assessment,
        )
        self.assertTrue(bound.is_valid(), bound.errors)
        obj = bound.save()
        obj.refresh_from_db()
        self.assertEqual(obj.passing_score, Decimal("62.75"))

    def test_edit_form_rejects_passing_score_over_100(self):
        from apps.courses.forms import AssessmentEditForm

        bound = AssessmentEditForm(
            data={
                "title": "Eval Decimal",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": "120.00",
                "max_attempts": "3",
                "status": "draft",
            },
            instance=self.assessment,
        )
        self.assertFalse(bound.is_valid())
        self.assertIn("passing_score", bound.errors)

    def test_builder_add_question_persists_decimal_points(self):
        url = reverse(
            "courses:builder_add_question",
            args=[self.course.id, self.assessment.id],
        )
        resp = self.web.post(
            url,
            data={
                "question_type": "single_choice",
                "text": "Pregunta 2.5 pts",
                "points": "2.5",
                "answer_text": ["A", "B"],
                "correct_answer": "0",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        q = Question.objects.filter(assessment=self.assessment, text="Pregunta 2.5 pts").first()
        self.assertIsNotNone(q)
        self.assertEqual(q.points, Decimal("2.50"))

    def test_builder_add_question_rejects_invalid_points(self):
        url = reverse(
            "courses:builder_add_question",
            args=[self.course.id, self.assessment.id],
        )
        resp = self.web.post(
            url,
            data={
                "question_type": "single_choice",
                "text": "Bad points",
                "points": "abc",
                "answer_text": ["A", "B"],
                "correct_answer": "0",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            Question.objects.filter(assessment=self.assessment, text="Bad points").exists()
        )

    def test_builder_edit_question_updates_decimal_points(self):
        q = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Editame",
            points=Decimal("1.00"),
            order=1,
        )
        Answer.objects.create(question=q, text="A", is_correct=True, order=1)
        Answer.objects.create(question=q, text="B", is_correct=False, order=2)
        url = reverse(
            "courses:builder_edit_question",
            args=[self.course.id, self.assessment.id, q.id],
        )
        resp = self.web.post(
            url,
            data={
                "question_type": "single_choice",
                "text": "Editame",
                "points": "3.75",
                "answer_text": ["A", "B"],
                "correct_answer": "0",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        q.refresh_from_db()
        self.assertEqual(q.points, Decimal("3.75"))

    def test_validate_percentage_accepts_decimal(self):
        from django.core.exceptions import ValidationError

        from apps.core.validators import validate_percentage

        # 75.5 is valid
        validate_percentage(Decimal("75.5"))
        # 100.01 raises
        with self.assertRaises(ValidationError):
            validate_percentage(Decimal("100.01"))
