"""
Regression tests for issues SD#37 / SD#38 / SD#33.

Root cause: an HTML formatter (commit f34a371) reflowed the builder partials and
split the single-line Alpine ``x-data`` JS string literal across several physical
lines.  A single-quoted JS string cannot contain raw newlines, so ``new Function``
(used by Alpine to evaluate ``x-data``) raised ``SyntaxError: unterminated string
literal``.  Alpine then failed to initialise the whole component, which meant:

  * lesson_form.html  -> the ``<select x-model="lessonType">`` did nothing, the
    "Asistencia" lesson could not be configured/saved (SD#33).
  * question_form.html -> the ``<select x-model="questionType">`` did nothing and
    the answer editors (``x-if="questionType === ...">``) never rendered, so
    questions other than Verdadero/Falso could not be added/edited (SD#37/#38).

These tests render the partials and assert the ``x-data`` initial values are emitted
on a single line (no raw newline inside the JS string literal), so a future
formatter run cannot silently re-break Alpine.
"""

import re
from datetime import date
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import Assessment, Question
from apps.courses.models import Category, Course, Lesson, Module


def _xdata_values(html):
    """Return every ``x-data`` attribute value found in ``html``."""
    return re.findall(r'x-data="([^"]*)"', html, re.DOTALL)


class BuilderAlpineXDataRegressionTests(TestCase):
    """The Alpine x-data string literals must stay on a single line."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="builder_xdata@test.com",
            password="testpass123",
            first_name="Build",
            last_name="Er",
            document_number="30000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        cls.category = Category.objects.create(
            name="Cat XData", slug="cat-xdata", description="c", color="#0a0a0a"
        )
        cls.course = Course.objects.create(
            code="COURSE-XDATA-1",
            title="Curso XData",
            description="d",
            objectives="o",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=cls.category,
            created_by=cls.user,
        )
        cls.module = Module.objects.create(
            course=cls.course, title="Modulo 1", description="m", order=1
        )
        cls.lesson_attendance = Lesson.objects.create(
            module=cls.module,
            title="Lista asistencia",
            description="l",
            lesson_type="attendance",
            order=2,
        )
        cls.assessment = Assessment.objects.create(
            title="Evaluacion XData",
            description="d",
            assessment_type="quiz",
            passing_score=Decimal("3.50"),
            time_limit=30,
            max_attempts=3,
            status="draft",
            course=cls.course,
            created_by=cls.user,
        )
        cls.question_mc = Question.objects.create(
            assessment=cls.assessment,
            question_type=Question.Type.MULTIPLE_CHOICE,
            text="¿Cuáles aplican?",
            points=5,
            order=1,
        )

    def _assert_no_raw_newline_in_strings(self, x_data):
        """No single-quoted segment of the x-data expression may span a newline."""
        # Strip the JS string literals; if any contained a newline, the regex below
        # (which only matches single-line single-quoted strings) would leave a
        # dangling quote followed by a newline.
        self.assertNotRegex(
            x_data,
            r":\s*'[^']*\n",
            "x-data has a JS string literal broken across lines -> breaks Alpine",
        )

    def test_lesson_form_new_xdata_single_line(self):
        html = render_to_string(
            "courses/partials/builder/lesson_form.html",
            {"is_new": True, "course": self.course, "module": self.module},
        )
        x_datas = _xdata_values(html)
        self.assertTrue(x_datas)
        self.assertIn("lessonType: 'video'", html)
        for xd in x_datas:
            self._assert_no_raw_newline_in_strings(xd)

    def test_lesson_form_edit_attendance_xdata_single_line(self):
        html = render_to_string(
            "courses/partials/builder/lesson_form.html",
            {
                "is_new": False,
                "course": self.course,
                "module": self.module,
                "lesson": self.lesson_attendance,
            },
        )
        self.assertIn("lessonType: 'attendance'", html)
        for xd in _xdata_values(html):
            self._assert_no_raw_newline_in_strings(xd)

    def test_question_form_new_xdata_single_line(self):
        html = render_to_string(
            "courses/partials/builder/question_form.html",
            {"is_edit": False, "course": self.course, "assessment": self.assessment},
        )
        self.assertIn("questionType: 'single_choice'", html)
        for xd in _xdata_values(html):
            self._assert_no_raw_newline_in_strings(xd)

    def test_question_form_edit_xdata_single_line(self):
        html = render_to_string(
            "courses/partials/builder/question_form.html",
            {
                "is_edit": True,
                "course": self.course,
                "assessment": self.assessment,
                "question": self.question_mc,
            },
        )
        self.assertIn("questionType: 'multiple_choice'", html)
        for xd in _xdata_values(html):
            self._assert_no_raw_newline_in_strings(xd)
