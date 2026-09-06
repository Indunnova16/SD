"""
Tests for SD#54 -- auto-completar LessonProgress al aprobar una evaluacion,
y (reproceso 3ra ronda, 2026-07-13) boton "Continuar Curso" en la pantalla
de resultado.

Root cause bounce #1 (confirmed in F2_OUTPUT, decision Miguel 2026-07-09,
reverts the "click manual" scope decision from the previous close of #54):

apps/assessments/services.py never touched LessonProgress at all -- the 3
call-sites where AssessmentAttempt.passed is finalized (auto_grade_attempt,
grade_attempt, calculate_score) all ended in attempt.save() with zero
side-effect on the student's lesson progress. That meant a student who
passed a 'quiz' lesson's evaluation still had to find and click "Marcar
como completado" manually, and until that click, is_lesson_accessible()
(apps/courses/services.py) kept the next mandatory lesson locked -- exactly
the symptom reported by the client on 2026-07-07 ("apruebo y no se
desbloquea").

Fix bounce #1: AssessmentService._sync_lesson_progress_on_pass(attempt),
invoked at the end of the 3 call-sites, calls EnrollmentService.
update_progress with {"completed": True} once attempt.passed=True -- reusing
the existing progress-tracking service instead of duplicating logic.

Root cause bounce #3 (FIX_INCOMPLETO, F1/F2 2026-07-13): the 2026-07-10
close above was strictly backend -- it never touched
templates/assessments/attempt_result.html to expose a way to continue the
course from the "aprobado" result screen. The client reported this exact
gap again on 2026-07-13 (screenshot /assessments/result/66/, course/lesson
64/108): passing an evaluation still stranded the user with only "Volver a
la Evaluacion" / "Mis Intentos", no link forward. Fix: apps.assessments.
views.attempt_result now resolves next_lesson/next_lesson_accessible (via
the new shared EnrollmentService.get_next_lesson_context, extracted from
apps.courses.views.lesson_view's inline logic) and the template's rama
aprobado renders #continue-course-btn when the next lesson is accessible,
falling back to "Volver a la Leccion" otherwise -- symmetric to the
pre-existing rama reprobado pattern.

These tests invoke the service methods DIRECTLY (auto_grade_attempt /
grade_attempt / calculate_score), NOT AssessmentAttempt.objects.create with
passed=True already set -- the 7 pre-existing tests in
apps/courses/tests/test_issue_54.py do that and are intentionally left
unmodified (they exercise a different code path, apps.courses.views.
update_progress, unaffected by this fix). This file is exclusive to #54 and
must NOT be merged into the shared apps/assessments/tests/test_services.py
(same convention already applied to apps/courses/tests/test_issue_54.py and
apps/courses/tests/test_issue_59_a4.py in this same RUN -- SD has 3
issues in flight and each keeps its own test module).
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, Question
from apps.assessments.services import AssessmentService
from apps.courses.models import Course, Enrollment, Lesson, LessonProgress, Module
from apps.courses.services import EnrollmentService


class AutoCompleteLessonProgressOnPassTest(TestCase):
    """AssessmentService.auto_grade_attempt / grade_attempt / calculate_score
    auto-complete the assessment's own 'quiz' lesson once passed=True, and
    unlock the next mandatory lesson -- no manual click required (SD#54)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-i54svc@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900005410",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student-i54svc@test.com",
            password="testpass123",
            first_name="Student",
            last_name="User",
            document_number="900005411",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )

        self.course = Course.objects.create(
            code="ISSUE54-SVC-001",
            title="Curso Issue 54 Service",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.module = Module.objects.create(course=self.course, title="Modulo 1", order=1)
        self.quiz_lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion seguridad vial",
            lesson_type=Lesson.Type.QUIZ,
            order=1,
            is_mandatory=True,
        )
        # Next mandatory lesson: must stay locked until quiz_lesson completes.
        self.next_lesson = Lesson.objects.create(
            module=self.module,
            title="Firma de asistencia",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=2,
            is_mandatory=True,
        )
        self.assessment = Assessment.objects.create(
            title="Evaluacion seguridad vial",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            lesson=self.quiz_lesson,
            passing_score=Decimal("3.50"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)

    def _single_choice_question(self, order=1):
        q = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text=f"Q{order}",
            points=Decimal("10.00"),
            order=order,
        )
        a_ok = Answer.objects.create(question=q, text="Correcta", is_correct=True, order=1)
        Answer.objects.create(question=q, text="Incorrecta", is_correct=False, order=2)
        return q, a_ok

    def test_auto_grade_attempt_completes_lesson_and_unlocks_next(self):
        """Happy path via auto_grade_attempt: no POST to update_progress,
        no manual click -- passing the quiz alone completes the lesson AND
        unlocks the next mandatory lesson."""
        q, a_ok = self._single_choice_question()
        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])

        # Before grading: next lesson locked, quiz lesson not completed.
        accessible_before, blocking = EnrollmentService.is_lesson_accessible(
            self.enrollment, self.next_lesson
        )
        self.assertFalse(accessible_before)
        self.assertEqual(blocking, self.quiz_lesson)

        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertTrue(progress.is_completed)
        self.assertIsNotNone(progress.completed_at)

        accessible_after, _ = EnrollmentService.is_lesson_accessible(
            self.enrollment, self.next_lesson
        )
        self.assertTrue(accessible_after)

    def test_grade_attempt_completes_lesson(self):
        """Same auto-complete behavior via the manual grade_attempt path
        (used e.g. after grading essay/short_answer questions)."""
        q, a_ok = self._single_choice_question()
        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])

        AssessmentService.grade_attempt(attempt, grader=self.admin)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertTrue(progress.is_completed)

    def test_calculate_score_completes_lesson(self):
        """calculate_score (used to recalculate after a manual essay
        regrade) also triggers the auto-complete hook once passed flips
        to True."""
        essay = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.ESSAY,
            text="Explique el procedimiento",
            points=Decimal("10.00"),
            order=1,
        )
        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        ans = AssessmentService.submit_answer(attempt, essay, text_answer="mi respuesta")

        # Grade the essay with full points directly (bypassing
        # grade_essay_answer's own grade_attempt call) to exercise
        # calculate_score in isolation, same as an admin recalculation tool
        # would call it.
        ans.points_awarded = Decimal("10.00")
        ans.is_correct = True
        ans.save()

        AssessmentService.calculate_score(attempt)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertTrue(progress.is_completed)

    def test_failed_attempt_does_not_complete_lesson(self):
        """A failed attempt must NOT complete the lesson nor unlock the
        next mandatory lesson (guard: `if not attempt.passed: return`)."""
        q = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Q1",
            points=Decimal("10.00"),
            order=1,
        )
        Answer.objects.create(question=q, text="Correcta", is_correct=True, order=1)
        wrong = Answer.objects.create(question=q, text="Incorrecta", is_correct=False, order=2)

        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[wrong.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertFalse(attempt.passed)

        self.assertFalse(
            LessonProgress.objects.filter(
                enrollment=self.enrollment, lesson=self.quiz_lesson, is_completed=True
            ).exists()
        )
        accessible, _ = EnrollmentService.is_lesson_accessible(self.enrollment, self.next_lesson)
        self.assertFalse(accessible)

    def test_later_failed_attempt_does_not_revert_completion(self):
        """Once a lesson is completed via a passed attempt, a SUBSEQUENT
        failed attempt on the same assessment must NOT revert
        is_completed -- "passed at least once" stays completed, consistent
        with the rest of the codebase (max_attempts / attempt history)."""
        q, a_ok = self._single_choice_question()
        first_attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(first_attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(first_attempt)
        first_attempt.refresh_from_db()
        self.assertTrue(first_attempt.passed)

        second_attempt = AssessmentService.start_attempt(self.student, self.assessment)
        q2 = self.assessment.questions.get(pk=q.pk)
        wrong = q2.answers.get(is_correct=False)
        AssessmentService.submit_answer(second_attempt, q2, selected_answer_ids=[wrong.id])
        AssessmentService.auto_grade_attempt(second_attempt)
        second_attempt.refresh_from_db()
        self.assertFalse(second_attempt.passed)

        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertTrue(progress.is_completed)

    def test_assessment_without_lesson_link_is_unaffected(self):
        """Generic course assessments not tied to any 'quiz' lesson
        (assessment.lesson=None, the shape used across the pre-existing
        test_services.py suite) must keep grading without error and without
        creating any LessonProgress row."""
        generic_assessment = Assessment.objects.create(
            title="Evaluacion general sin leccion",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            lesson=None,
            passing_score=Decimal("3.50"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        q = Question.objects.create(
            assessment=generic_assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Q1",
            points=Decimal("10.00"),
            order=1,
        )
        a_ok = Answer.objects.create(question=q, text="Correcta", is_correct=True, order=1)

        attempt = AssessmentService.start_attempt(self.student, generic_assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()

        self.assertTrue(attempt.passed)
        self.assertFalse(LessonProgress.objects.filter(enrollment=self.enrollment).exists())

    def test_no_enrollment_does_not_raise(self):
        """A passed attempt from a user with no Enrollment in the course
        (e.g. an admin previewing the assessment) must not raise."""
        q, a_ok = self._single_choice_question()
        attempt = AssessmentService.start_attempt(self.admin, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])

        AssessmentService.auto_grade_attempt(attempt)  # must not raise
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertFalse(
            LessonProgress.objects.filter(
                lesson=self.quiz_lesson, enrollment__user=self.admin
            ).exists()
        )


class AttemptResultContinueButtonTest(TestCase):
    """attempt_result view + template, rama aprobado (SD#54, bounce #3 --
    reproceso FIX_INCOMPLETO). El cierre del 2026-07-10 solo arreglo el
    auto-completado backend; nunca toco el template para exponer un enlace
    de continuacion tras aprobar -- exactamente el hueco que el cliente
    reporto de nuevo el 2026-07-13 (screenshot /assessments/result/66/,
    curso/leccion 64/108, Intento 6, 5.0, Aprobado).

    `test_continue_button_present_and_points_to_next_lesson` es a la vez la
    reproduccion (habria fallado contra el HEAD previo a este fix -- el
    template no emitia ningun `#continue-course-btn`) y la validacion del
    fix, siguiendo la misma convencion que los tests de
    `AutoCompleteLessonProgressOnPassTest` arriba en este archivo."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-i54btn@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900005412",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student-i54btn@test.com",
            password="testpass123",
            first_name="Student",
            last_name="User",
            document_number="900005413",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )

        self.course = Course.objects.create(
            code="ISSUE54-BTN-001",
            title="Curso Issue 54 Boton Continuar",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.module = Module.objects.create(course=self.course, title="Modulo 1", order=1)
        self.quiz_lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion seguridad vial",
            lesson_type=Lesson.Type.QUIZ,
            order=1,
            is_mandatory=True,
        )
        self.next_lesson = Lesson.objects.create(
            module=self.module,
            title="Firma de asistencia",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=2,
            is_mandatory=True,
        )
        self.assessment = Assessment.objects.create(
            title="Evaluacion seguridad vial",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            lesson=self.quiz_lesson,
            passing_score=Decimal("4.00"),
            max_attempts=0,  # unlimited -- needed to replay several attempts below
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)
        self.client.force_login(self.student)

    def _question(self):
        q = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Q1",
            points=Decimal("10.00"),
            order=1,
        )
        a_ok = Answer.objects.create(question=q, text="Correcta", is_correct=True, order=1)
        a_bad = Answer.objects.create(question=q, text="Incorrecta", is_correct=False, order=2)
        return q, a_ok, a_bad

    def test_continue_button_present_and_points_to_next_lesson(self):
        """Dato-legacy-like: replay 5 failed attempts + 1 passed one to reach
        attempt_number=6 / score=5.00 -- mirroring the exact shape of the
        real client record (attempt id=66: attempt_number=6, score=5.00,
        passed=True) that F2 could not attach a local test to directly (it
        belongs to a live prod user, no BD write access from F3/F2 -- see
        F2_OUTPUT reproduccion.limitacion). Passing must render
        #continue-course-btn pointing at the next mandatory lesson, and
        must NOT regress the pre-existing 'Intento'/score display."""
        q, a_ok, a_bad = self._question()
        for _ in range(5):
            failed_attempt = AssessmentService.start_attempt(self.student, self.assessment)
            AssessmentService.submit_answer(failed_attempt, q, selected_answer_ids=[a_bad.id])
            AssessmentService.auto_grade_attempt(failed_attempt)

        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()

        self.assertEqual(attempt.attempt_number, 6)
        self.assertEqual(attempt.score, Decimal("5.00"))
        self.assertTrue(attempt.passed)

        response = self.client.get(reverse("assessments:result", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)

        # Sub-item 4 del plan_accion (reproceso): Intento/puntaje siguen
        # correctos post-cambio -- no regression on the pre-existing stats.
        self.assertContains(response, "5.0")
        self.assertContains(response, "Aprobado")

        # El fix en si: boton nuevo presente y apuntando a la leccion
        # siguiente (accesible porque el quiz se auto-completo al aprobar).
        self.assertContains(response, 'id="continue-course-btn"')
        expected_url = reverse("courses:lesson", args=[self.course.id, self.next_lesson.id])
        self.assertContains(response, f'href="{expected_url}"')

    def test_fallback_to_lesson_link_when_next_lesson_still_locked(self):
        """If some OTHER earlier mandatory lesson (unrelated to this quiz)
        is still incomplete, the immediate next lesson stays locked even
        though the quiz itself auto-completed on pass -- the template must
        fall back to 'Volver a la Leccion' instead of linking to a locked
        lesson (no #continue-course-btn)."""
        intro_lesson = Lesson.objects.create(
            module=self.module,
            title="Introduccion (bloqueante)",
            lesson_type=Lesson.Type.TEXT,
            order=0,
            is_mandatory=True,
        )
        q, a_ok, _ = self._question()
        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        # Sanity: intro_lesson (order 0) really is what blocks next_lesson.
        accessible, blocking = EnrollmentService.is_lesson_accessible(
            self.enrollment, self.next_lesson
        )
        self.assertFalse(accessible)
        self.assertEqual(blocking, intro_lesson)

        response = self.client.get(reverse("assessments:result", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="continue-course-btn"')

        fallback_url = reverse("courses:lesson", args=[self.course.id, self.quiz_lesson.id])
        self.assertContains(response, f'href="{fallback_url}"')
        self.assertContains(response, "Volver a la Lección")

    def test_no_continue_button_when_assessment_not_tied_to_lesson(self):
        """Generic course assessments (assessment.lesson=None) must keep
        rendering without error and without any continue/fallback link --
        no lesson to continue to or fall back on."""
        generic_assessment = Assessment.objects.create(
            title="Evaluacion general sin leccion",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            lesson=None,
            passing_score=Decimal("4.00"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        q = Question.objects.create(
            assessment=generic_assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Q1",
            points=Decimal("10.00"),
            order=1,
        )
        a_ok = Answer.objects.create(question=q, text="Correcta", is_correct=True, order=1)

        attempt = AssessmentService.start_attempt(self.student, generic_assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        response = self.client.get(reverse("assessments:result", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="continue-course-btn"')
        self.assertContains(response, "Volver a la Evaluación")

    def test_no_continue_button_and_no_500_without_enrollment(self):
        """A passed attempt viewed by a user with no Enrollment (e.g. an
        admin previewing the assessment) must render 200, with no
        continue/fallback lesson link, and must never raise -- mirrors the
        service-level `test_no_enrollment_does_not_raise` guard but at the
        view/template layer."""
        q, a_ok, _ = self._question()
        attempt = AssessmentService.start_attempt(self.admin, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("assessments:result", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="continue-course-btn"')

    def test_failed_attempt_result_is_unaffected(self):
        """Sanity/no-regression: the rama reprobado (untouched by this fix)
        keeps its own pre-existing 'Reintentar Evaluacion' + 'Volver a la
        Leccion' actions and never renders #continue-course-btn."""
        q, _, a_bad = self._question()
        attempt = AssessmentService.start_attempt(self.student, self.assessment)
        AssessmentService.submit_answer(attempt, q, selected_answer_ids=[a_bad.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertFalse(attempt.passed)

        response = self.client.get(reverse("assessments:result", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="continue-course-btn"')
        self.assertContains(response, "Reintentar Evaluación")
