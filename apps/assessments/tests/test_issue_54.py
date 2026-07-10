"""
Tests for SD#54 -- auto-completar LessonProgress al aprobar una evaluacion.

Root cause (confirmed in F2_OUTPUT, decision Miguel 2026-07-09, reverts the
"click manual" scope decision from the previous close of #54):

apps/assessments/services.py never touched LessonProgress at all -- the 3
call-sites where AssessmentAttempt.passed is finalized (auto_grade_attempt,
grade_attempt, calculate_score) all ended in attempt.save() with zero
side-effect on the student's lesson progress. That meant a student who
passed a 'quiz' lesson's evaluation still had to find and click "Marcar
como completado" manually, and until that click, is_lesson_accessible()
(apps/courses/services.py) kept the next mandatory lesson locked -- exactly
the symptom reported by the client on 2026-07-07 ("apruebo y no se
desbloquea").

Fix: AssessmentService._sync_lesson_progress_on_pass(attempt), invoked at
the end of the 3 call-sites, calls EnrollmentService.update_progress with
{"completed": True} once attempt.passed=True -- reusing the existing
progress-tracking service instead of duplicating logic.

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
            passing_score=Decimal("80.00"),
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
            passing_score=Decimal("80.00"),
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
        self.assertFalse(
            LessonProgress.objects.filter(enrollment=self.enrollment).exists()
        )

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
            LessonProgress.objects.filter(lesson=self.quiz_lesson, enrollment__user=self.admin).exists()
        )
