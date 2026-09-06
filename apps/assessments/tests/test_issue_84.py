"""
Regression tests for issue SD#84 — evaluación publicada con 0 preguntas
permite iniciar un intento y termina en un resultado 0/0.

Client report: al iniciar "Evaluacion seguridad vial" (una evaluación real
de producción), el sistema crea el intento igual y lo entrega calificado
0/0 en vez de bloquear con un mensaje claro.

Root cause (confirmado por F2 1:1 contra BD prod sd_lms — SELECT puros,
ver SPRINTS/RUN_2026-07-30_1129/agents/SD_84_f2.json):
  - `apps.assessments.views.start_attempt` reimplementaba sus propios
    checks (max_attempts, intento en progreso) SIN llamar nunca a
    `AssessmentService.can_start_attempt()`/`start_attempt()`
    (apps/assessments/services.py), que YA validaba
    `assessment.questions.count() == 0` -> "La evaluación no tiene
    preguntas". Ese guard quedaba muerto en producción.
  - Aguas arriba, `apps.courses.views.builder_add_lesson` y
    `builder_edit_lesson` creaban el Assessment con status="published" de
    forma incondicional, sin verificar que el parseo de quiz_questions
    hubiera producido >=1 Question real (ver
    apps/courses/tests/test_views.py::BuilderEditAssessmentPublishGuardIssue84Tests
    para el guard de creación/publicación).

Fix: `start_attempt` ahora delega en `AssessmentService.start_attempt()`
(que internamente llama a `can_start_attempt()`), envuelto en
try/except ValueError -> messages.error + redirect a assessments:detail.

Este archivo cubre el guard EN EL VIEW (happy path + edge cases), que es
justo lo que NO estaba probado antes de este fix (el service ya tenía su
propio test en test_services.py::test_cannot_start_with_no_questions,
pero nadie lo llamaba desde el view).
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, AssessmentAttempt, Question
from apps.courses.models import Category, Course, Lesson, Module


class StartAttemptGuardIssue84Tests(TestCase):
    """Guard runtime real: start_attempt debe bloquear evaluaciones sin
    preguntas delegando en AssessmentService, en vez de reimplementar sus
    propios checks incompletos."""

    def setUp(self):
        self.client = Client()

        self.student = User.objects.create_user(
            email="student_sd84@test.com",
            password="testpass123",
            first_name="Estudiante",
            last_name="SD84",
            document_number="84100001",
            job_position="Tecnico",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.staff = User.objects.create_user(
            email="staff_sd84_start@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD84",
            document_number="84100002",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD84 start",
            slug="cat-sd84-start",
            description="cat",
            color="#334455",
        )
        self.course = Course.objects.create(
            code="COURSE-SD84-START",
            title="Curso SD84",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=self.category,
            created_by=self.staff,
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_start_attempt_with_questions_creates_attempt_normally(self):
        """HAPPY PATH: evaluación publicada CON preguntas arranca normal —
        el fix no debe romper el flujo que ya funcionaba."""
        assessment = Assessment.objects.create(
            title="Quiz con preguntas SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        question = Question.objects.create(
            assessment=assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta real",
            points=10,
            order=0,
        )
        Answer.objects.create(question=question, text="A", is_correct=True, order=0)
        Answer.objects.create(question=question, text="B", is_correct=False, order=1)

        self.client.force_login(self.student)
        url = reverse("assessments:start", kwargs={"assessment_id": assessment.id})
        resp = self.client.post(url)

        attempt = AssessmentAttempt.objects.get(user=self.student, assessment=assessment)
        self.assertRedirects(resp, reverse("assessments:take", kwargs={"attempt_id": attempt.id}))
        self.assertEqual(attempt.status, AssessmentAttempt.Status.IN_PROGRESS)

    # ------------------------------------------------------------------
    # Edge case: 0 preguntas — el bug real de SD#84
    # ------------------------------------------------------------------

    def test_start_attempt_blocked_when_zero_questions(self):
        """EDGE CASE (el bug reportado): evaluación PUBLICADA con 0
        preguntas debe bloquearse con mensaje claro, redirigir al detalle,
        y NO crear ningún AssessmentAttempt (antes: se creaba y terminaba
        en resultado 0/0)."""
        assessment = Assessment.objects.create(
            title="Quiz sin preguntas SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        self.assertEqual(assessment.questions.count(), 0)

        self.client.force_login(self.student)
        url = reverse("assessments:start", kwargs={"assessment_id": assessment.id})
        resp = self.client.post(url, follow=True)

        self.assertRedirects(
            resp, reverse("assessments:detail", kwargs={"assessment_id": assessment.id})
        )
        messages = [str(m) for m in resp.context["messages"]]
        self.assertIn("La evaluación no tiene preguntas", messages)

        # El corazón del bug: NO debe existir ningún AssessmentAttempt.
        self.assertFalse(
            AssessmentAttempt.objects.filter(user=self.student, assessment=assessment).exists(),
            "start_attempt NO debe crear un AssessmentAttempt cuando la "
            "evaluación no tiene preguntas (esto es lo que producía el "
            "resultado 0/0 reportado por el cliente).",
        )

    def test_start_attempt_preserves_max_attempts_behavior(self):
        """Regresión: el caso 'máximo de intentos alcanzado' (que SÍ
        funcionaba antes) debe seguir funcionando igual tras delegar en
        AssessmentService."""
        assessment = Assessment.objects.create(
            title="Quiz con limite SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=1,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        question = Question.objects.create(
            assessment=assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta real",
            points=10,
            order=0,
        )
        Answer.objects.create(question=question, text="A", is_correct=True, order=0)

        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=assessment,
            attempt_number=1,
            status=AssessmentAttempt.Status.GRADED,
        )

        self.client.force_login(self.student)
        url = reverse("assessments:start", kwargs={"assessment_id": assessment.id})
        resp = self.client.post(url, follow=True)

        self.assertRedirects(
            resp, reverse("assessments:detail", kwargs={"assessment_id": assessment.id})
        )
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("máximo" in m for m in messages))
        self.assertEqual(
            AssessmentAttempt.objects.filter(user=self.student, assessment=assessment).count(),
            1,
        )

    def test_start_attempt_preserves_in_progress_redirect_behavior(self):
        """Regresión: si ya hay un intento en progreso, sigue
        redirigiendo directo a continuarlo (sin mensaje de error), igual
        que antes del fix."""
        assessment = Assessment.objects.create(
            title="Quiz en progreso SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        question = Question.objects.create(
            assessment=assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta real",
            points=10,
            order=0,
        )
        Answer.objects.create(question=question, text="A", is_correct=True, order=0)

        existing = AssessmentAttempt.objects.create(
            user=self.student,
            assessment=assessment,
            attempt_number=1,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        )

        self.client.force_login(self.student)
        url = reverse("assessments:start", kwargs={"assessment_id": assessment.id})
        resp = self.client.post(url)

        self.assertRedirects(resp, reverse("assessments:take", kwargs={"attempt_id": existing.id}))
        self.assertEqual(
            AssessmentAttempt.objects.filter(user=self.student, assessment=assessment).count(),
            1,
        )

    # ------------------------------------------------------------------
    # Dato legado real — assessment_id=28 "Evaluacion seguridad vial"
    # ------------------------------------------------------------------

    def test_start_attempt_blocked_against_real_legacy_row_shape(self):
        """Test contra el dato legado REAL (issue SD#84, protocolo de 7
        pasos paso 3 — obligatorio contra >=1 registro legacy real, no solo
        fixtures propias).

        Replica EXACTAMENTE la forma de la fila real de producción
        confirmada por F2 vía SELECT contra sd_lms (127.0.0.1:5434):
        assessment_id=28, title='Evaluacion seguridad vial', lesson_id=98,
        course_id=63 ('INDUCCIÓN PODA Y TALA'), status='published',
        max_attempts=0, question_count=0. Es la misma fila que el
        attempt_id=123 (reportado por el cliente con resultado 0/0)
        referencia 1:1 (ver evidencia_bd en SD_84_f2.json). No se usa el
        registro real de BD prod desde un test unitario (no hay conexión a
        prod en este entorno de tests) — se replica su forma exacta como
        fixture, igual que el patrón ya usado por
        apps/courses/tests/test_issue_38.py (legacy_lesson/legacy_assessment)."""
        course_63_like = Course.objects.create(
            code="COURSE-SD84-INDUCCION-PODA-TALA",
            title="INDUCCIÓN PODA Y TALA",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=self.category,
            created_by=self.staff,
        )
        module = Module.objects.create(
            course=course_63_like, title="Modulo seguridad vial", description="m", order=1
        )
        lesson_98_like = Lesson.objects.create(
            module=module,
            title="Evaluacion seguridad vial",
            description="leccion legacy",
            lesson_type=Lesson.Type.QUIZ,
            order=0,
        )
        assessment_28_like = Assessment.objects.create(
            title="Evaluacion seguridad vial",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=course_63_like,
            lesson=lesson_98_like,
            created_by=self.staff,
            status="published",
        )
        self.assertEqual(assessment_28_like.questions.count(), 0)

        self.client.force_login(self.student)
        url = reverse("assessments:start", kwargs={"assessment_id": assessment_28_like.id})
        resp = self.client.post(url, follow=True)

        self.assertRedirects(
            resp,
            reverse("assessments:detail", kwargs={"assessment_id": assessment_28_like.id}),
        )
        messages = [str(m) for m in resp.context["messages"]]
        self.assertIn("La evaluación no tiene preguntas", messages)
        self.assertFalse(
            AssessmentAttempt.objects.filter(
                user=self.student, assessment=assessment_28_like
            ).exists(),
            "Contra la fila legacy real (assessment_id=28) tampoco debe "
            "crearse un AssessmentAttempt -- este es exactamente el "
            "escenario reportado por el cliente (attempt_id=123, "
            "resultado 0/0).",
        )


class AssessmentDetailNoQuestionsIssue84Tests(TestCase):
    """Hallazgo adicional F2 (no bloqueante para cerrar SD#84, pero
    incluido por ser trivial): el detalle de una evaluación sin preguntas
    NO debe ofrecer el botón 'Iniciar Evaluación' como si estuviera
    disponible."""

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            email="student_sd84_detail@test.com",
            password="testpass123",
            first_name="Estudiante",
            last_name="SD84Detail",
            document_number="84200001",
            job_position="Tecnico",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.staff = User.objects.create_user(
            email="staff_sd84_detail@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD84Detail",
            document_number="84200002",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD84 detail",
            slug="cat-sd84-detail",
            description="cat",
            color="#556677",
        )
        self.course = Course.objects.create(
            code="COURSE-SD84-DETAIL",
            title="Curso SD84 detail",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=self.category,
            created_by=self.staff,
        )

    def test_detail_does_not_offer_start_button_without_questions(self):
        assessment = Assessment.objects.create(
            title="Evaluacion sin preguntas detalle SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        self.client.force_login(self.student)
        url = reverse("assessments:detail", kwargs={"assessment_id": assessment.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_start"])
        self.assertFalse(resp.context["has_questions"])
        self.assertContains(resp, "Sin Preguntas Disponibles")
        self.assertNotContains(resp, "Iniciar Evaluación")

    def test_detail_offers_start_button_with_questions(self):
        """HAPPY PATH: con >=1 pregunta real, el botón sigue disponible
        (el hallazgo adicional no debe romper el caso correcto)."""
        assessment = Assessment.objects.create(
            title="Evaluacion con preguntas detalle SD84",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            max_attempts=0,
            course=self.course,
            created_by=self.staff,
            status=Assessment.Status.PUBLISHED,
        )
        Question.objects.create(
            assessment=assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta real",
            points=10,
            order=0,
        )
        self.client.force_login(self.student)
        url = reverse("assessments:detail", kwargs={"assessment_id": assessment.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_start"])
        self.assertTrue(resp.context["has_questions"])
        self.assertContains(resp, "Iniciar Evaluación")
