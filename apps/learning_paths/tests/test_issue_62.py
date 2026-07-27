"""
Tests for SD#62 A4 — LearningPath.duration_hours (nueva @property).

`total_duration` tenia un bug preexistente (`Sum(F("course__total_duration"))`
sobre una @property de Python, ajeno a SD#62) que quedaba fuera de alcance de
este issue -- corregido aparte en PR #65 (fix root-cause de las 3 fallas
preexistentes que bloqueaban el gate de SD#62/#63). `duration_hours` es una
property NUEVA con un aggregate correcto sobre la cadena FK real
(`path_courses__course__modules__lessons__duration`), usada por
path_detail.html en lugar de `total_duration`.
"""

from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.courses.models import Category, Course, Lesson, Module
from apps.learning_paths.models import LearningPath, PathCourse

_SEQ = [6200]


def _make_user(**overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue62_lp_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "SD62",
        "document_number": f"63{n:08d}",
        "job_position": "Admin",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": True,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat SD62LP {n}", slug=f"cat-sd62lp-{n}", description="c", color="#654321"
    )
    defaults = {
        "code": f"ISSUE62LP-{n}",
        "title": f"Curso SD62LP {n}",
        "description": "desc",
        "objectives": "obj",
        "course_type": Course.Type.MANDATORY,
        "status": Course.Status.PUBLISHED,
        "category": category,
        "created_by": creator,
    }
    defaults.update(overrides)
    return Course.objects.create(**defaults)


def _make_path(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "name": f"Ruta SD62 {n}",
        "description": "desc",
        "estimated_duration": 30,
        "created_by": creator,
    }
    defaults.update(overrides)
    return LearningPath.objects.create(**defaults)


class LearningPathDurationHoursTests(TestCase):
    """A4: LearningPath.duration_hours con el aggregate correcto (sobre la
    cadena FK real, no sobre la @property rota de total_duration)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_user()

    def test_happy_path_one_course_known_duration(self):
        course = _make_course(self.staff)
        module = Module.objects.create(course=course, title="M1", description="", order=0)
        Lesson.objects.create(
            module=module, title="L1", lesson_type=Lesson.Type.VIDEO, duration=100, order=0
        )
        # 100 min -> 1.6666... -> redondea hacia arriba a 2.0 h (SD#62; mismo
        # redondeo que Course.duration_hours).
        self.assertEqual(course.duration_hours, 2.0)

        path = _make_path(self.staff)
        PathCourse.objects.create(learning_path=path, course=course, order=0)

        self.assertEqual(path.duration_hours, 2.0)

    def test_edge_zero_courses_is_zero_no_exception(self):
        path = _make_path(self.staff)
        self.assertEqual(path.duration_hours, 0.0)

    def test_edge_multiple_courses_sum_across_path(self):
        course_a = _make_course(self.staff)
        module_a = Module.objects.create(course=course_a, title="MA", description="", order=0)
        Lesson.objects.create(
            module=module_a, title="LA", lesson_type=Lesson.Type.VIDEO, duration=60, order=0
        )
        course_b = _make_course(self.staff)
        module_b = Module.objects.create(course=course_b, title="MB", description="", order=0)
        Lesson.objects.create(
            module=module_b, title="LB", lesson_type=Lesson.Type.VIDEO, duration=30, order=0
        )

        path = _make_path(self.staff)
        PathCourse.objects.create(learning_path=path, course=course_a, order=0)
        PathCourse.objects.create(learning_path=path, course=course_b, order=1)

        # 60 + 30 = 90 min -> 1.5 h.
        self.assertEqual(path.duration_hours, 1.5)
