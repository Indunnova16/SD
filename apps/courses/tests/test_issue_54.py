"""
Tests for SD#54 -- a 'quiz' (Evaluación) lesson could be marked completed
without ever having passed its assessment.

Root cause (2 layers, confirmed in F2_OUTPUT):

1. Backend: apps/courses/views.py::update_progress marked
   LessonProgress.is_completed=True for ANY lesson_type once progress_percent
   reached 100, with no check against AssessmentAttempt.passed. A direct POST
   to the endpoint (or the generic "mark as complete" button) could bypass
   the evaluation entirely.
2. Frontend: templates/courses/lesson_view.html rendered the generic
   "Marcar como completado" form for any lesson_type not explicitly handled
   (video/attendance/presential), which included 'quiz'.

Reproduced in prod BD (sd_lms): lesson_progress.id=50 had is_completed=true
even though the user's only graded AssessmentAttempt (id=19) had score=0.00
and passed=false -- an explicit REPROBADO case incorrectly marked complete.
That exact shape (a graded, failed attempt) is reproduced here as the
"legacy data" regression test.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Assessment, AssessmentAttempt
from apps.courses.models import Course, Enrollment, Lesson, LessonProgress, Module


class UpdateProgressQuizGateTest(TestCase):
    """Server-side gate in apps.courses.views.update_progress (SD#54)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-issue54@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000541",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student-issue54@test.com",
            password="testpass123",
            first_name="Student",
            last_name="User",
            document_number="900000542",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )

        self.course = Course.objects.create(
            code="ISSUE54-001",
            title="Curso Issue 54",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.module = Module.objects.create(course=self.course, title="Modulo 1", order=1)
        self.quiz_lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion seguridad vial",
            lesson_type=Lesson.Type.QUIZ,
            order=1,
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

        self.client.force_login(self.student)
        self.url = reverse(
            "courses:update_progress",
            args=[self.course.id, self.quiz_lesson.id],
        )

    def _post_complete(self):
        return self.client.post(self.url, {"progress": "100"})

    def test_quiz_without_any_attempt_cannot_be_completed(self):
        """The bug's primary scenario: no AssessmentAttempt at all (never
        even started), yet a direct POST tried to mark it done -- matches
        lesson_progress_id=88 in prod (attempt in_progress, never submitted)."""
        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=self.assessment,
            status=AssessmentAttempt.Status.IN_PROGRESS,
            attempt_number=1,
        )

        response = self._post_complete()

        self.assertEqual(response.status_code, 400)
        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertFalse(progress.is_completed)
        self.assertIsNone(progress.completed_at)

    def test_quiz_with_failed_graded_attempt_cannot_be_completed(self):
        """Legacy-data regression: reproduces prod lesson_progress_id=50 --
        a graded attempt that explicitly FAILED (score=0.00, passed=False)
        must NOT be allowed to complete the lesson."""
        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=self.assessment,
            status=AssessmentAttempt.Status.GRADED,
            attempt_number=1,
            score=Decimal("0.00"),
            points_earned=Decimal("0.00"),
            passed=False,
        )

        response = self._post_complete()

        self.assertEqual(response.status_code, 400)
        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertFalse(progress.is_completed)

    def test_quiz_with_passed_attempt_can_be_completed(self):
        """Happy path: once the user has a PASSED attempt for the lesson's
        assessment, marking the lesson complete must succeed."""
        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=self.assessment,
            status=AssessmentAttempt.Status.GRADED,
            attempt_number=1,
            score=Decimal("100.00"),
            points_earned=Decimal("10.00"),
            passed=True,
        )

        response = self._post_complete()

        self.assertEqual(response.status_code, 200)
        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertTrue(progress.is_completed)
        self.assertIsNotNone(progress.completed_at)

    def test_non_quiz_lesson_completion_unaffected(self):
        """Regression: the gate is scoped to lesson_type='quiz' only -- a
        plain text/interactive lesson must keep completing exactly as
        before, with no AssessmentAttempt involved at all."""
        text_lesson = Lesson.objects.create(
            module=self.module,
            title="Leccion de texto",
            lesson_type=Lesson.Type.TEXT,
            order=2,
        )
        url = reverse("courses:update_progress", args=[self.course.id, text_lesson.id])

        response = self.client.post(url, {"progress": "100"})

        self.assertEqual(response.status_code, 200)
        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=text_lesson)
        self.assertTrue(progress.is_completed)

    def test_quiz_passed_attempt_for_a_different_assessment_does_not_count(self):
        """A passed attempt on an unrelated assessment must not leak into
        this lesson's gate (assessment__lesson=lesson scoping)."""
        other_lesson = Lesson.objects.create(
            module=self.module,
            title="Otra evaluacion",
            lesson_type=Lesson.Type.QUIZ,
            order=3,
        )
        other_assessment = Assessment.objects.create(
            title="Otra evaluacion",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            lesson=other_lesson,
            passing_score=Decimal("3.50"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=other_assessment,
            status=AssessmentAttempt.Status.GRADED,
            attempt_number=1,
            score=Decimal("100.00"),
            points_earned=Decimal("10.00"),
            passed=True,
        )

        response = self._post_complete()

        self.assertEqual(response.status_code, 400)
        progress = LessonProgress.objects.get(enrollment=self.enrollment, lesson=self.quiz_lesson)
        self.assertFalse(progress.is_completed)


class LessonViewQuizGateTest(TestCase):
    """Frontend gate in templates/courses/lesson_view.html (SD#54)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-issue54-lv@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000543",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student-issue54-lv@test.com",
            password="testpass123",
            first_name="Student",
            last_name="User",
            document_number="900000544",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )
        self.course = Course.objects.create(
            code="ISSUE54-002",
            title="Curso Issue 54 LV",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.module = Module.objects.create(course=self.course, title="Modulo 1", order=1)
        self.quiz_lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion seguridad vial",
            lesson_type=Lesson.Type.QUIZ,
            order=1,
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
        Enrollment.objects.create(user=self.student, course=self.course)
        self.client.force_login(self.student)
        self.url = reverse("courses:lesson", args=[self.course.id, self.quiz_lesson.id])

    def test_lesson_view_hides_generic_complete_button_when_not_passed(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Debes aprobar la evaluaci", content)
        self.assertNotIn("Marcar como completado", content)

    def test_lesson_view_shows_complete_button_when_passed(self):
        AssessmentAttempt.objects.create(
            user=self.student,
            assessment=self.assessment,
            status=AssessmentAttempt.Status.GRADED,
            attempt_number=1,
            score=Decimal("100.00"),
            points_earned=Decimal("10.00"),
            passed=True,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Marcar como completado", content)
