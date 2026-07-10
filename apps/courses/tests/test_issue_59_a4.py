"""
Tests for SD#59, A4 — Asistencia: ampliar acceso de roster+export a
Coordinador (sin tocar `_staff_required`).

`attendance_lesson_view` y `lesson_view` gateaban el roster/resumen de
asistencia solo con `Rol.ADMINISTRADOR`; `export_attendance_pdf` usaba
`_staff_required` (idem). Fix en 3 sitios de `apps/courses/views.py`:
`attendance_lesson_view`/`lesson_view` amplían a
`user_has_rol(ADMINISTRADOR, COORDINADOR)` y agregan SIEMPRE el flag
`is_attendance_admin_view` al contexto; `export_attendance_pdf` usa un
helper NUEVO `_attendance_export_required` (NO se toca `_staff_required`,
compartido con 9 vistas más).

HALLAZGO CRÍTICO DE F2 no capturado por F1: el roster tenía un SEGUNDO
gate independiente `{% if request.user.is_staff %}` duplicado en 2
templates (`attendance_lesson.html:128` y `lesson_view.html:328`) — un
Coordinador normalmente NO tiene `is_staff=True` (decisión #58 #2: rol y
is_staff desacoplados a propósito), así que arreglar solo la vista no
alcanzaba; ambos templates ahora leen `is_attendance_admin_view`.

NOTA (detect_hot_files.py): apps/courses/tests.py es compartido con SD#54
en este mismo RUN — este archivo de test es POR-ISSUE
(test_issue_59_a4.py), nunca se apendea a tests.py.
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import (
    AttendanceSignature,
    Category,
    Course,
    Enrollment,
    Lesson,
    LessonProgress,
    Module,
)

# Minimal valid 1x1 transparent PNG, same fixture used across courses tests
# (test_attendance_pdf.py) so ImageField validation passes.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)

_SEQ = [3000]


def _png_file(name="sig.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


def _make_user(rol=None, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue59_a4_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A4",
        "document_number": f"6{n:08d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat A4 {n}", slug=f"cat-a4-{n}", description="c", color="#FF0000"
    )
    course = Course.objects.create(
        code=f"ISSUE59-A4-{n}",
        title=f"Curso A4 {n}",
        description="desc",
        objectives="obj",
        course_type=Course.Type.MANDATORY,
        status=Course.Status.PUBLISHED,
        category=category,
        created_by=creator,
    )
    module = Module.objects.create(course=course, title="M1", description="d", order=0)
    return course, module


class AttendanceRosterAccessTestBase(TestCase):
    """Shared fixtures: 1 course + 1 attendance lesson + 3 roles."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)

        self.course, self.module = _make_course(self.administrador)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión de asistencia",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        # 1 enrolled + signed attendee, so the roster has real rows to show.
        # attendance_lesson_view/lesson_view both require the VIEWER to have
        # their own Enrollment too (`get_object_or_404(Enrollment, ...
        # user=request.user)`) -- unrelated to A4, so every role that will
        # GET these views in a test must be enrolled, including Administrador.
        self.signer = _make_user()
        Enrollment.objects.create(user=self.signer, course=self.course)
        Enrollment.objects.create(user=self.coordinador, course=self.course)
        Enrollment.objects.create(user=self.ejecutor, course=self.course)
        Enrollment.objects.create(user=self.administrador, course=self.course)
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=self.signer)
        sig.signature_image.save("sig.png", _png_file(), save=True)


class AttendanceLessonViewRosterAccessTests(AttendanceRosterAccessTestBase):
    """attendance_lesson_view: roster visible to Coordinador, hidden to Ejecutor."""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            "courses:attendance_lesson", args=[self.course.id, self.lesson.id]
        )

    def test_happy_path_coordinador_sees_roster(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_attendance_admin_view"])
        self.assertIn("attendance_summary", response.context)
        self.assertContains(response, "Resumen de asistencia")

    def test_administrador_still_sees_roster(self):
        """Regression: the pre-existing ADMINISTRADOR path keeps working."""
        self.client.force_login(self.administrador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_attendance_admin_view"])
        self.assertContains(response, "Resumen de asistencia")

    def test_edge_ejecutor_does_not_see_roster(self):
        """Regression guard: Ejecutor still cannot see the admin roster
        (only their own signature capture form)."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_attendance_admin_view"])
        self.assertNotIn("attendance_summary", response.context)
        self.assertNotContains(response, "Resumen de asistencia")


class LessonViewRosterAccessTests(AttendanceRosterAccessTestBase):
    """lesson_view (inline attendance path, SD#33): same roster gate,
    reached via the normal prev/next lesson navigation instead of the
    dedicated attendance_lesson_view URL."""

    def setUp(self):
        super().setUp()
        self.url = reverse("courses:lesson", args=[self.course.id, self.lesson.id])

    def test_happy_path_coordinador_sees_roster(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_attendance_admin_view"])
        self.assertContains(response, "Resumen de asistencia")

    def test_edge_ejecutor_does_not_see_roster(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_attendance_admin_view"])
        self.assertNotContains(response, "Resumen de asistencia")

    def test_edge_is_attendance_admin_view_present_for_non_attendance_lesson(self):
        """Edge case: `is_attendance_admin_view` must be present in the
        context (and truthy for Coordinador) even for a NON-attendance
        lesson — it's set unconditionally now, not just inside the
        `lesson_type == 'attendance'` branch, so the template can safely
        reference it without a KeyError/silent-failure risk elsewhere."""
        video_lesson = Lesson.objects.create(
            module=self.module,
            title="Video",
            lesson_type=Lesson.Type.VIDEO,
            order=1,
        )
        # Unlock it: sequential locking requires the previous (attendance,
        # order=0) mandatory lesson completed first -- unrelated to A4.
        coordinador_enrollment = Enrollment.objects.get(
            user=self.coordinador, course=self.course
        )
        LessonProgress.objects.create(
            enrollment=coordinador_enrollment, lesson=self.lesson, is_completed=True
        )
        url = reverse("courses:lesson", args=[self.course.id, video_lesson.id])

        self.client.force_login(self.coordinador)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("is_attendance_admin_view", response.context)
        self.assertTrue(response.context["is_attendance_admin_view"])


class ExportAttendancePdfAccessTests(AttendanceRosterAccessTestBase):
    """export_attendance_pdf: now gated by `_attendance_export_required`
    (ADMINISTRADOR + COORDINADOR), not the shared `_staff_required`."""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            "courses:export_attendance_pdf", args=[self.course.id, self.lesson.id]
        )

    def test_happy_path_coordinador_exports_pdf(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

    def test_administrador_still_exports_pdf(self):
        """Regression: the pre-existing ADMINISTRADOR path keeps working."""
        self.client.force_login(self.administrador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_edge_ejecutor_is_redirected(self):
        """Regression guard: Ejecutor is still blocked from exporting."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_edge_staff_required_helper_untouched_for_other_views(self):
        """Guard rail for the A4 constraint itself: `_staff_required` (used
        by 9+ other views) must still reject COORDINADOR — only the new
        `_attendance_export_required` widens access, not the shared
        helper. Exercised indirectly via `course_builder`, one of the
        views still gated by `_staff_required`."""
        self.client.force_login(self.coordinador)
        response = self.client.get(
            reverse("courses:course_builder", args=[self.course.id])
        )
        self.assertEqual(response.status_code, 302)
