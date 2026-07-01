"""
Tests for SD#43 — Course.duration_hours property (B2).

certificate_template.html previously referenced `course.estimated_duration`,
an attribute removed from the Course model (see the comment at
apps/courses/models.py:184: "duration is now calculated as total_duration
property"), which Django silently resolved to an empty value, always
falling into the `|default:"N/A"` filter (never raising, never showing a
real number).

`duration_hours` converts `total_duration` (sum of Lesson.duration) into
hours. IMPORTANT: Lesson.duration is stored in MINUTES, not seconds —
confirmed by the "min" labels in templates/courses/course_list.html:115 /
course_detail.html:22,166, the lesson form's "Minutos" placeholder
(apps/courses/forms.py:352), and the explicit JS comment in
templates/courses/lesson_view.html:483
(`{{ lesson.duration }} * 60 // Convert minutes to seconds`).
"""

from datetime import date

from django.template.loader import render_to_string
from django.test import TestCase

from apps.accounts.models import User
from apps.courses.models import Course, Lesson, Module


class CourseDurationHoursTest(TestCase):
    """Unit tests for Course.duration_hours."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-issue43-courses@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="900000401",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )

    def _make_course(self, code="ISSUE43-DUR-001"):
        return Course.objects.create(
            code=code,
            title="Curso Duracion Issue 43",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )

    def test_duration_hours_no_lessons(self):
        course = self._make_course()
        self.assertEqual(course.total_duration, 0)
        self.assertEqual(course.duration_hours, 0.0)

    def test_duration_hours_converts_minutes_to_hours(self):
        course = self._make_course(code="ISSUE43-DUR-002")
        module = Module.objects.create(course=course, title="Modulo 1", order=1)
        # 120 min + 90 min = 210 min total = 3.5 hours
        Lesson.objects.create(
            module=module,
            title="Leccion 1",
            lesson_type=Lesson.Type.VIDEO,
            duration=120,
            order=1,
        )
        Lesson.objects.create(
            module=module,
            title="Leccion 2",
            lesson_type=Lesson.Type.VIDEO,
            duration=90,
            order=2,
        )
        self.assertEqual(course.total_duration, 210)
        self.assertEqual(course.duration_hours, 3.5)

    def test_duration_hours_rounds_to_one_decimal(self):
        course = self._make_course(code="ISSUE43-DUR-003")
        module = Module.objects.create(course=course, title="Modulo 1", order=1)
        # 100 minutes -> 100/60 = 1.6666... -> rounds to 1.7
        Lesson.objects.create(
            module=module,
            title="Leccion 1",
            lesson_type=Lesson.Type.VIDEO,
            duration=100,
            order=1,
        )
        self.assertEqual(course.duration_hours, 1.7)

    def test_certificate_template_renders_duration_hours_not_estimated_duration(self):
        """
        Regression: the certificate template must render a real number via
        `course.duration_hours`, not silently fall back to "N/A" via the
        removed `course.estimated_duration` attribute.
        """
        course = self._make_course(code="ISSUE43-DUR-004")
        module = Module.objects.create(course=course, title="Modulo 1", order=1)
        Lesson.objects.create(
            module=module,
            title="Leccion 1",
            lesson_type=Lesson.Type.VIDEO,
            duration=60,  # 1 hour
            order=1,
        )

        html = render_to_string(
            "certifications/certificate_template.html",
            {
                "course": course,
                "user": self.admin,
                "certificate_number": "SD-ISSUE43-TPL-001",
                "issued_date": None,
                "verification_url": (
                    "https://example.com/certifications/verify/SD-ISSUE43-TPL-001/"
                ),
            },
        )
        # LANGUAGE_CODE=es-co (config/settings/base.py) localizes the
        # decimal separator to a comma in template output, so 1.0 renders
        # as "1,0" (not "1.0") in prod.
        self.assertIn("1,0 horas", html)
        self.assertNotIn("N/A horas", html)

        # Confirm the removed attribute really doesn't exist (would have
        # silently rendered "" -> "N/A" via the |default filter).
        self.assertFalse(hasattr(course, "estimated_duration"))
