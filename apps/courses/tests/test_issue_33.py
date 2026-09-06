"""
Tests for SD#33 -- second bounce (FIX_INCOMPLETO reproceso).

The first close (2026-06-09) only validated the ALTA of an "Asistencia"
lesson from the course builder (see ``test_views.py::
BuilderAddAttendanceLessonViewTests``). It never exercised the CONSUMPTION
path: a student opening an already-created attendance lesson through the
normal course navigation, signing it, completing the course, and (for
staff) downloading the attendance PDF. @Indunnova (2026-06-29) reported
exactly that path broken:

  B1: ``lesson_view`` had no branch for ``lesson_type == 'attendance'`` and
      fell through to the generic "Contenido ... no soportado" message
      (views.py / lesson_view.html).
  B2: the course-completion signature modal (``course_completion_signature
      .html``) submitted as a plain ``<form>``, so the browser navigated to
      the raw JSON ``sign_course_completion`` returns instead of staying on
      the page (same root cause as SD#48).
  B3: NOT a bug -- the PDF export URL works; the client's URL had a typo
      ("admin-courses/") never present in the real route. No code change,
      covered already by ``test_attendance_pdf.py``.

This file also pins a related fix discovered while implementing B1:
``save_attendance_signature`` created the ``LessonProgress`` row but never
called ``EnrollmentService.update_enrollment_progress`` (unlike
``update_progress``/``update_video_progress``), so ``enrollment.progress``
never reached 100 for a course ending in an attendance lesson -- "Finalizar
Curso" would never appear even after signing. Left unfixed, the reproceso
would still be incomplete (signing attendance would dead-end instead of
unlocking course completion).
"""

import base64
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
from apps.courses.services import EnrollmentService

# Minimal valid 1x1 transparent PNG, so the base64 payload decodes to real
# image bytes (mirrors test_attendance_pdf.py's fixture).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)
_PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()

_SEQ = [3300]


def _next_seq():
    _SEQ[0] += 1
    return _SEQ[0]


def _make_user(is_staff=False, **kwargs):
    n = _next_seq()
    defaults = {
        "email": f"sd33_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "Test",
        "document_number": f"9{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
    }
    # issue #58 (RBAC): is_staff ya no gatea nada de negocio, el gating lee
    # `rol`. Un `_make_user(is_staff=True)` en estos tests representa al
    # usuario admin/staff del escenario -> le asignamos rol=ADMINISTRADOR
    # tambien, salvo que el caller ya haya pasado `rol` explicito.
    if is_staff:
        defaults.setdefault("rol", User.Rol.ADMINISTRADOR)
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def _png_file(name="sig.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


class LessonViewAttendanceRenderTests(TestCase):
    """B1: attendance lessons must render inline, not the generic fallback."""

    def setUp(self):
        self.client = Client()
        self.staff = _make_user(is_staff=True)
        self.student = _make_user()

        category = Category.objects.create(
            name="Cat SD33 consumo", slug="cat-sd33-consumo", description="c", color="#00AA00"
        )
        self.course = Course.objects.create(
            code="COURSE-SD33-CONSUMO",
            title="Induccion Poda y Tala",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=category,
            created_by=self.staff,
        )
        module = Module.objects.create(course=self.course, title="M1", description="d", order=0)

        # Two lessons: a video first, the attendance lesson LAST -- mirrors
        # the exact prod shape (course 63 / lesson 103) that F2 flagged as
        # the regression risk for a hard redirect() fix.
        self.video_lesson = Lesson.objects.create(
            module=module,
            title="Video intro",
            lesson_type=Lesson.Type.VIDEO,
            order=0,
            is_mandatory=True,
        )
        self.attendance_lesson = Lesson.objects.create(
            module=module,
            title="Sesion presencial",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=1,
            is_mandatory=True,
        )

        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)
        # Simulate the student already watched/completed the first lesson.
        LessonProgress.objects.create(
            enrollment=self.enrollment,
            lesson=self.video_lesson,
            is_completed=True,
        )
        EnrollmentService.update_enrollment_progress(self.enrollment)
        self.enrollment.refresh_from_db()

        self.lesson_url = reverse(
            "courses:lesson", args=[self.course.id, self.attendance_lesson.id]
        )
        self.sign_url = reverse(
            "courses:save_attendance_signature",
            args=[self.course.id, self.attendance_lesson.id],
        )

    def test_attendance_lesson_no_longer_shows_unsupported_message(self):
        """Core B1 regression: the literal string the client quoted must be gone."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "no soportado en visualizacion web")
        # The signature capture UI must be present instead.
        self.assertContains(resp, 'id="attendance-signature-canvas"')
        self.assertContains(resp, "Por favor, firma para registrar tu asistencia")

    def test_finalizar_curso_survives_when_attendance_is_last_lesson(self):
        """
        F2's flagged regression risk: a hard redirect() to the dedicated
        attendance_lesson_view would have dropped the "Finalizar Curso"
        block entirely for this exact shape (attendance = last lesson).
        The inline-elif fix must keep it reachable end-to-end.
        """
        self.client.force_login(self.student)

        # Before signing: enrollment.progress is 50% (1/2 mandatory lessons).
        # "Finalizar Curso" (a plain link back to the course) always renders
        # at the last lesson regardless of completion -- the discriminant is
        # whether it opens the completion-signature MODAL (progress >= 100
        # and not yet signed), which is the actual thing a redirect() out of
        # lesson_view.html would have broken.
        self.assertEqual(float(self.enrollment.progress), 50.0)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "'completion-signature-modal').showModal()")
        self.assertNotContains(resp, 'id="completion-signature-modal"')

        # Sign the attendance lesson via the same fetch endpoint the new
        # inline JS calls (save_attendance_signature).
        resp = self.client.post(self.sign_url, data={"signature_data": _PNG_DATA_URL})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        # The missing EnrollmentService.update_enrollment_progress() call
        # (fixed alongside B1) must have pushed progress to 100.
        self.enrollment.refresh_from_db()
        self.assertEqual(float(self.enrollment.progress), 100.0)

        # Reloading the SAME lesson_view page (no redirect involved) must
        # now show: the signed state + the "Finalizar Curso" button that
        # opens the completion-signature modal -- none of which would exist
        # if B1 had been fixed with a redirect() out of lesson_view.html.
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "no soportado en visualizacion web")
        self.assertContains(resp, "Ya has firmado esta lección")
        self.assertContains(resp, "'completion-signature-modal').showModal()")
        self.assertContains(resp, 'id="completion-signature-modal"')

    def test_staff_sees_attendance_summary_inline(self):
        # lesson_view() requires an Enrollment for ANY viewer, staff included
        # (same precondition attendance_lesson_view already enforces), and
        # sequential locking applies regardless of is_staff -- complete the
        # first lesson so the attendance lesson is accessible.
        staff_enrollment = Enrollment.objects.create(user=self.staff, course=self.course)
        LessonProgress.objects.create(
            enrollment=staff_enrollment, lesson=self.video_lesson, is_completed=True
        )
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("courses:lesson", args=[self.course.id, self.attendance_lesson.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Resumen de asistencia")
        self.assertContains(
            resp,
            reverse(
                "courses:export_attendance_pdf",
                args=[self.course.id, self.attendance_lesson.id],
            ),
        )

    def test_non_staff_does_not_see_attendance_summary(self):
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Resumen de asistencia")

    def test_pre_existing_signature_legacy_data_renders_signed_state(self):
        """
        Test against a pre-existing (legacy) row: a signature saved via the
        OLD flow (the dedicated attendance_lesson_view, which existed before
        this fix and is untouched by it) must render correctly through the
        NEWLY fixed lesson_view code path -- not just signatures created via
        the new inline UI.
        """
        legacy_signature = AttendanceSignature.objects.create(
            lesson=self.attendance_lesson,
            user=self.student,
        )
        legacy_signature.signature_image.save("legacy_sig.png", _png_file(), save=True)

        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "no soportado en visualizacion web")
        self.assertContains(resp, "Ya has firmado esta lección")
        self.assertContains(resp, legacy_signature.signature_image.url)
        # No unsigned canvas/CTA should render once already signed.
        self.assertNotContains(resp, 'id="attendance-signature-canvas"')

    def test_anonymous_redirected(self):
        resp = self.client.get(self.lesson_url)
        self.assertIn(resp.status_code, (302, 301))


class CourseCompletionSignatureTemplateTests(TestCase):
    """
    B2: the completion-signature modal must no longer navigate the browser
    to raw JSON. Django's test client does not execute JS, so we assert the
    RENDERED HTML/script directly (the fetch()+preventDefault() wiring),
    the same technique used elsewhere in this repo for template-only fixes.
    """

    def setUp(self):
        self.client = Client()
        self.staff = _make_user(is_staff=True)
        self.student = _make_user()

        category = Category.objects.create(
            name="Cat SD33 completion", slug="cat-sd33-completion", description="c", color="#1122AA"
        )
        self.course = Course.objects.create(
            code="COURSE-SD33-COMPLETION",
            title="Curso a punto de terminar",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=category,
            created_by=self.staff,
        )
        module = Module.objects.create(course=self.course, title="M1", description="d", order=0)
        self.lesson = Lesson.objects.create(
            module=module,
            title="Unica leccion",
            lesson_type=Lesson.Type.TEXT,
            content="contenido",
            order=0,
            is_mandatory=True,
        )
        self.enrollment = Enrollment.objects.create(
            user=self.student, course=self.course, progress=100
        )
        LessonProgress.objects.create(
            enrollment=self.enrollment, lesson=self.lesson, is_completed=True
        )

        self.lesson_url = reverse("courses:lesson", args=[self.course.id, self.lesson.id])
        self.sign_completion_url = reverse("courses:sign_course_completion", args=[self.course.id])

    def test_modal_form_no_longer_navigates_to_raw_json(self):
        """
        Regression for SD#33/SD#48: the <form> must be intercepted by JS
        (preventDefault + fetch) instead of letting the browser submit it
        natively to the JSON-returning endpoint.
        """
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="completion-signature-modal"')
        content = resp.content.decode()
        self.assertIn("e.preventDefault()", content)
        self.assertIn("fetch(form.action", content)
        # The action attribute must still point at the real endpoint.
        self.assertIn(f'action="{self.sign_completion_url}"', content)

    def test_sign_course_completion_endpoint_still_returns_json(self):
        """Backend contract unchanged (F2: both branches already returned
        identical JSON) -- only the client-side consumption was broken."""
        self.client.force_login(self.student)
        resp = self.client.post(
            self.sign_completion_url,
            data={"signature": _PNG_DATA_URL},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("signed_at", data)

        self.enrollment.refresh_from_db()
        self.assertIsNotNone(self.enrollment.completion_signature)
        self.assertIsNotNone(self.enrollment.completion_signed_at)
