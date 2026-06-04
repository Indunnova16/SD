"""
Tests for attendance scheduled_date, the admin attendance summary and the
attendance PDF export (issues SD#33 + SD#40).

Covered:
  - Lesson.scheduled_date persists through the builder form (A1/A2).
  - LessonBuilderForm validation: attendance requires scheduled_date,
    accepts the datetime-local "T" format; non-attendance does not (A2).
  - export_attendance_pdf returns application/pdf bytes for staff (A5/A7).
  - Permission: non-staff is redirected (A5).
  - 404 when the lesson is not an attendance lesson (A5).
  - Attendance percentage per session, including the 0-enrollee edge case
    with no ZeroDivisionError (B1/B3).
  - Derived Presente/Ausente status against a pre-existing (legacy) signature.

Users are created with ``job_profile=None`` (FK to JobProfileType) following
the established pattern in test_views.py — the factory_boy UserFactory still
assigns a string to that FK and is unrelated to this feature.
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.forms import LessonBuilderForm
from apps.courses.models import (
    AttendanceSignature,
    Category,
    Course,
    Enrollment,
    Lesson,
    Module,
)
from apps.courses.views import _build_attendance_summary


# Minimal valid 1x1 transparent PNG, so ImageField validation passes.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)

_USER_SEQ = [1000]


def _png_file(name="sig.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


def _make_user(is_staff=False, **kwargs):
    _USER_SEQ[0] += 1
    n = _USER_SEQ[0]
    defaults = {
        "email": f"att_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "Test",
        "document_number": f"5{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def _make_course(creator):
    _USER_SEQ[0] += 1
    n = _USER_SEQ[0]
    category = Category.objects.create(
        name=f"Cat {n}", slug=f"cat-{n}", description="c", color="#FF0000"
    )
    course = Course.objects.create(
        code=f"COURSE-ATT-{n}",
        title=f"Curso {n}",
        description="desc",
        objectives="obj",
        course_type=Course.Type.MANDATORY,
        status=Course.Status.PUBLISHED,
        category=category,
        created_by=creator,
    )
    module = Module.objects.create(course=course, title="M1", description="d", order=0)
    return course, module


class AttendanceFormTests(TestCase):
    """LessonBuilderForm scheduled_date behavior (A1/A2)."""

    def setUp(self):
        creator = _make_user(is_staff=True)
        _, self.module = _make_course(creator)

    def _base_data(self, **overrides):
        data = {
            "title": "Sesión",
            "lesson_type": Lesson.Type.ATTENDANCE,
            "description": "",
            "content": "",
            "video_url": "",
            "duration": 0,
            "is_mandatory": True,
            "scheduled_date": "2026-06-10T14:30",
        }
        data.update(overrides)
        return data

    def test_attendance_with_datetime_local_format_is_valid(self):
        """datetime-local sends 'YYYY-MM-DDTHH:MM' and must validate."""
        form = LessonBuilderForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNotNone(form.cleaned_data["scheduled_date"])

    def test_attendance_without_scheduled_date_is_invalid(self):
        form = LessonBuilderForm(data=self._base_data(scheduled_date=""))
        self.assertFalse(form.is_valid())
        self.assertIn("scheduled_date", form.errors)

    def test_video_lesson_without_scheduled_date_is_valid(self):
        form = LessonBuilderForm(
            data=self._base_data(
                title="Video intro",
                lesson_type=Lesson.Type.VIDEO,
                video_url="https://www.youtube.com/watch?v=abcdefghijk",
                duration=10,
                scheduled_date="",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_scheduled_date_persists_on_save(self):
        form = LessonBuilderForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)
        lesson = form.save(commit=False)
        lesson.module = self.module
        lesson.save()
        lesson.refresh_from_db()
        self.assertIsNotNone(lesson.scheduled_date)
        # Compare in local time: with USE_TZ the value is stored as UTC, the
        # form parses the naive "14:30" against the active timezone.
        from django.utils import timezone

        local = timezone.localtime(lesson.scheduled_date)
        self.assertEqual((local.year, local.month, local.day), (2026, 6, 10))
        self.assertEqual((local.hour, local.minute), (14, 30))


class AttendanceSummaryTests(TestCase):
    """_build_attendance_summary percentage-per-session logic (B1/B3)."""

    def setUp(self):
        creator = _make_user(is_staff=True)
        self.course, self.module = _make_course(creator)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Asistencia",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )

    def _enroll(self, n):
        users = []
        for _ in range(n):
            user = _make_user()
            Enrollment.objects.create(user=user, course=self.course)
            users.append(user)
        return users

    def _sign(self, user):
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=user)
        sig.signature_image.save("sig.png", _png_file(), save=True)
        return sig

    def test_percentage_two_of_three(self):
        users = self._enroll(3)
        self._sign(users[0])
        self._sign(users[1])

        summary = _build_attendance_summary(self.course, self.lesson)

        self.assertEqual(summary["total_inscritos"], 3)
        self.assertEqual(summary["total_presentes"], 2)
        self.assertEqual(summary["total_ausentes"], 1)
        self.assertEqual(summary["porcentaje_asistencia"], 66.7)
        estados = {r["document_number"]: r["estado"] for r in summary["rows"]}
        self.assertEqual(estados[users[0].document_number], "Presente")
        self.assertEqual(estados[users[2].document_number], "Ausente")

    def test_zero_enrollees_no_division_error(self):
        summary = _build_attendance_summary(self.course, self.lesson)
        self.assertEqual(summary["total_inscritos"], 0)
        self.assertEqual(summary["porcentaje_asistencia"], 0.0)
        self.assertEqual(summary["rows"], [])

    def test_full_attendance_is_100(self):
        users = self._enroll(2)
        for u in users:
            self._sign(u)
        summary = _build_attendance_summary(self.course, self.lesson)
        self.assertEqual(summary["porcentaje_asistencia"], 100.0)


class ExportAttendancePdfViewTests(TestCase):
    """export_attendance_pdf view (A5/A6/A7 + B3)."""

    def setUp(self):
        self.client = Client()
        self.staff = _make_user(is_staff=True)
        self.regular = _make_user()
        self.course, self.module = _make_course(self.staff)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Asistencia",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        # One enrolled signer (Presente) + one enrolled non-signer (Ausente).
        self.signer = _make_user()
        Enrollment.objects.create(user=self.signer, course=self.course)
        Enrollment.objects.create(user=self.regular, course=self.course)
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=self.signer)
        sig.signature_image.save("sig.png", _png_file(), save=True)

        self.url = reverse(
            "courses:export_attendance_pdf",
            args=[self.course.id, self.lesson.id],
        )

    def test_staff_gets_pdf(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        content = resp.getvalue() if hasattr(resp, "getvalue") else resp.content
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 1000)
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_non_staff_redirected(self):
        self.client.force_login(self.regular)
        resp = self.client.get(self.url)
        # _staff_required redirects non-staff (no HX header) to courses:list.
        self.assertEqual(resp.status_code, 302)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_non_attendance_lesson_404(self):
        video_lesson = Lesson.objects.create(
            module=self.module,
            title="Video",
            lesson_type=Lesson.Type.VIDEO,
            order=1,
        )
        self.client.force_login(self.staff)
        url = reverse(
            "courses:export_attendance_pdf",
            args=[self.course.id, video_lesson.id],
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_summary_reflects_enrollment(self):
        """Legacy-style data: enrollment + pre-existing signature -> 50%."""
        summary = _build_attendance_summary(self.course, self.lesson)
        self.assertEqual(summary["total_inscritos"], 2)
        self.assertEqual(summary["total_presentes"], 1)
        self.assertEqual(summary["porcentaje_asistencia"], 50.0)
