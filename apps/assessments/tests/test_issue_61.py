"""
Tests for SD#61 -- reenvio (doble-clic / timer + click manual coincidente /
boton Atras + reenvio) del formulario de evaluacion sobre un attempt YA
enviado devolvia HTTP 404 crudo en vez de redirigir al resultado.

Root cause (confirmed in F2_OUTPUT): apps/assessments/views.py:submit_attempt
usaba get_object_or_404(AssessmentAttempt, pk=attempt_id, user=request.user,
status=AssessmentAttempt.Status.IN_PROGRESS). El primer POST exitoso cambia
el status del attempt (a SUBMITTED y luego, si es auto-calificable, a
GRADED via AssessmentService.auto_grade_attempt). Un 2do POST al MISMO
attempt_id ya no matchea el filtro status=IN_PROGRESS del queryset, y
Django lanza un Http404 generico -- a diferencia de take_assessment (views.py
:166-176) y attempt_result (views.py:370-380), que obtienen el attempt SIN
ese filtro y branchean explicitamente por status.

Fix: submit_attempt ahora sigue el mismo patron -- obtiene el attempt sin
filtrar por status y, si ya no esta IN_PROGRESS, redirige de inmediato a
assessments:result ANTES de tocar request.POST / guardar respuestas /
cambiar status / recalificar. Esto hace el endpoint idempotente: un reenvio
no re-procesa ni re-califica, solo redirige al resultado ya calculado.

Este archivo es exclusivo de #61 (SD tiene multiples issues en vuelo en
este RUN -- convencion ya aplicada a test_issue_54.py / test_issue_57.py /
test_issue_58_a6.py en este mismo paquete) y no debe mergearse a
test_services.py ni a ningun otro modulo de tests compartido.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, AssessmentAttempt, AttemptAnswer, Question
from apps.assessments.services import AssessmentService
from apps.courses.models import Course


class SubmitAttemptIdempotencyTest(TestCase):
    """POST repetido a assessments:submit sobre el mismo attempt_id, ya no
    IN_PROGRESS tras el primer envio exitoso, debe redirigir a
    assessments:result (302) -- nunca un Http404 crudo -- y no debe
    re-procesar respuestas ni re-calificar el intento (SD#61)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-i61@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900006101",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student-i61@test.com",
            password="testpass123",
            first_name="Student",
            last_name="User",
            document_number="900006102",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )
        self.course = Course.objects.create(
            code="ISSUE61-001",
            title="Curso Issue 61",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.assessment = Assessment.objects.create(
            title="Evaluacion Issue 61",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=Decimal("3.50"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        self.question = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Pregunta unica",
            points=Decimal("10.00"),
            order=1,
        )
        self.a_ok = Answer.objects.create(
            question=self.question, text="Correcta", is_correct=True, order=1
        )
        self.a_bad = Answer.objects.create(
            question=self.question, text="Incorrecta", is_correct=False, order=2
        )

        self.client.force_login(self.student)
        self.attempt = AssessmentService.start_attempt(self.student, self.assessment)
        self.submit_url = reverse("assessments:submit", args=[self.attempt.id])
        self.result_url = reverse("assessments:result", args=[self.attempt.id])

    def _submit(self):
        return self.client.post(
            self.submit_url,
            {f"question_{self.question.id}": [str(self.a_ok.id)], "time_spent": "30"},
        )

    def test_first_submit_grades_and_redirects_to_result(self):
        """Control -- comportamiento correcto del primer envio (no toca lo
        que ya funcionaba)."""
        response = self._submit()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.result_url)

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AssessmentAttempt.Status.GRADED)
        self.assertTrue(self.attempt.passed)
        self.assertEqual(self.attempt.score, Decimal("5.00"))

    def test_second_submit_on_same_attempt_redirects_not_404(self):
        """Reproduccion + validacion del fix: antes de este cambio, este
        2do POST devolvia HTTP 404 crudo (get_object_or_404 filtraba
        status=IN_PROGRESS y el attempt, ya GRADED, no matcheaba)."""
        self._submit()

        response = self._submit()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.result_url)

    def test_second_submit_does_not_regrade_or_change_score(self):
        """El reenvio no debe re-calificar: score, points_earned y
        submitted_at deben quedar exactamente como los dejo el 1er envio."""
        self._submit()
        self.attempt.refresh_from_db()
        first_score = self.attempt.score
        first_points_earned = self.attempt.points_earned
        first_submitted_at = self.attempt.submitted_at
        first_status = self.attempt.status

        self._submit()
        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.score, first_score)
        self.assertEqual(self.attempt.points_earned, first_points_earned)
        self.assertEqual(self.attempt.submitted_at, first_submitted_at)
        self.assertEqual(self.attempt.status, first_status)

    def test_second_submit_does_not_duplicate_attempt_answers(self):
        """El reenvio no debe crear ni duplicar AttemptAnswer -- el branch
        de idempotencia corta ANTES de procesar request.POST."""
        self._submit()
        count_after_first = AttemptAnswer.objects.filter(attempt=self.attempt).count()
        selected_after_first = list(
            AttemptAnswer.objects.get(
                attempt=self.attempt, question=self.question
            ).selected_answers.values_list("id", flat=True)
        )

        self._submit()

        count_after_second = AttemptAnswer.objects.filter(attempt=self.attempt).count()
        selected_after_second = list(
            AttemptAnswer.objects.get(
                attempt=self.attempt, question=self.question
            ).selected_answers.values_list("id", flat=True)
        )

        self.assertEqual(count_after_first, count_after_second)
        self.assertEqual(selected_after_first, selected_after_second)

    def test_submit_on_directly_created_submitted_attempt_redirects(self):
        """Caso C de F2 (attempt creado/dejado con status=SUBMITTED sin
        pasar por el 1er submit real de este test -- simula volver atras
        y reenviar) tambien debe redirigir, no dar 404."""
        other_attempt = AssessmentAttempt.objects.create(
            user=self.student,
            assessment=self.assessment,
            attempt_number=2,
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        url = reverse("assessments:submit", args=[other_attempt.id])

        response = self.client.post(url, {"time_spent": "0"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("assessments:result", args=[other_attempt.id]))

    def test_submit_other_users_attempt_still_404s(self):
        """No-regression de seguridad: se relajo SOLO el filtro de status,
        no el de user -- un attempt de OTRO usuario sigue dando 404."""
        other_student = User.objects.create_user(
            email="other-i61@test.com",
            password="testpass123",
            first_name="Other",
            last_name="Student",
            document_number="900006103",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )
        other_attempt = AssessmentService.start_attempt(other_student, self.assessment)
        url = reverse("assessments:submit", args=[other_attempt.id])

        response = self.client.post(url, {"time_spent": "0"})

        self.assertEqual(response.status_code, 404)
