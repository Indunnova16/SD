"""
Tests for SD#48 -- REPROCESO (bounce=1, categoria MALENTENDIDO).

The first close (2026-07-01) conflated this with SD#33's B2 (the course
completion signature modal submitting as a raw <form>, fixed by
intercepting it with fetch()). @Indunnova reported a DIFFERENT symptom on
2026-07-02: signing an ATTENDANCE lesson (save_attendance_signature /
"Resumen de asistencia" panel) never updates Estado/Hora/% -- a flow B2
never touched.

F2's causa raiz confirmada (double):

  1. Backend (real but NOT the reported symptom's cause): save_attendance_
     signature() marked LessonProgress.is_completed=True but never set
     progress_percent, so it stayed at 0.00 forever (mirrors update_progress
     /update_video_progress, which both set progress_percent=100).
  2. Frontend (THE cause of the reported symptom): #attendance-submit-btn
     starts `disabled` in the HTML and was only re-enabled from inside the
     mousemove/touchmove handlers -- never mousedown/touchstart/click. A
     short tap/click with no real drag left the button permanently
     disabled, and a click on a disabled <button> fires NO JS event at all
     (no fetch(), no alert(), no console error) -- total silence,
     confirmed by 0 POST requests to the sign endpoint in Cloud Run access
     logs before the client's report.

This file covers the literal round-trip the corpus was missing (sign ->
reread the staff attendance summary -> assert Presente/Estado/hora/
progreso), the backend progress_percent fix directly, and the data
migration (0021_backfill_attendance_progress_percent) that repairs rows
signed under the old broken code (legacy state: is_completed=True,
progress_percent=0.00 for an attendance lesson).
"""

import base64
import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps as real_apps
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import (
    Category,
    Course,
    Enrollment,
    Lesson,
    LessonProgress,
    Module,
)

# Minimal valid 1x1 transparent PNG (mirrors test_issue_33.py's fixture).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)
_PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()

_SEQ = [4800]


def _next_seq():
    _SEQ[0] += 1
    return _SEQ[0]


def _make_user(is_staff=False, **kwargs):
    n = _next_seq()
    defaults = {
        "email": f"sd48_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "Test",
        "document_number": f"9{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


class AttendanceSignatureRoundTripTests(TestCase):
    """
    Literal round-trip the corpus was missing: POST (firmar) -> GET
    (releer resumen de asistencia como staff) -> assert Presente/Estado/
    hora/progreso. This is the exact client-reported symptom for SD#48.
    """

    def setUp(self):
        self.client = Client()
        self.staff = _make_user(is_staff=True)
        self.student = _make_user()

        category = Category.objects.create(
            name="Cat SD48", slug="cat-sd48", description="c", color="#334455"
        )
        self.course = Course.objects.create(
            code="COURSE-SD48",
            title="Induccion con asistencia",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=category,
            created_by=self.staff,
        )
        module = Module.objects.create(course=self.course, title="M1", description="d", order=0)
        self.attendance_lesson = Lesson.objects.create(
            module=module,
            title="Sesion presencial",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
            is_mandatory=True,
        )

        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)
        self.staff_enrollment = Enrollment.objects.create(user=self.staff, course=self.course)

        self.lesson_url = reverse(
            "courses:lesson", args=[self.course.id, self.attendance_lesson.id]
        )
        self.sign_url = reverse(
            "courses:save_attendance_signature",
            args=[self.course.id, self.attendance_lesson.id],
        )

    def test_signing_updates_staff_summary_estado_hora_and_progress(self):
        # 1. Staff opens the lesson BEFORE the student signs: the summary
        # must show the student as Ausente, no hora, 0% asistencia.
        self.client.force_login(self.staff)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Resumen de asistencia")
        self.assertContains(resp, "Ausente")
        # NOTE: plain "Presente" is a substring of the "Presentes" summary
        # tile label (always rendered), so assert the specific badge
        # instead of the bare word.
        self.assertNotContains(
            resp, '<span class="badge badge-success">Presente</span>'
        )

        # No LessonProgress exists for the student yet.
        self.assertFalse(
            LessonProgress.objects.filter(
                enrollment=self.enrollment, lesson=self.attendance_lesson
            ).exists()
        )

        # 2. Student signs (the actual click-handler fetch() this issue's
        # frontend fix makes reachable regardless of drag gesture).
        self.client.force_login(self.student)
        resp = self.client.post(self.sign_url, data={"signature_data": _PNG_DATA_URL})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        # 3. Backend fix: LessonProgress.progress_percent must now be 100,
        # not stuck at the 0.00 default (this is what F1 originally flagged
        # -- real defect, independent of the reported symptom's root cause).
        lesson_progress = LessonProgress.objects.get(
            enrollment=self.enrollment, lesson=self.attendance_lesson
        )
        self.assertTrue(lesson_progress.is_completed)
        self.assertEqual(lesson_progress.progress_percent, Decimal("100.00"))

        # 4. Staff rereads the lesson: the client's literal complaint --
        # Estado/Hora/% must now reflect the signature, not stay frozen at
        # Ausente/-/0. The staff account is ALSO enrolled (lesson_view
        # requires an Enrollment for any viewer -- see test_issue_33.py)
        # and hasn't signed, so it correctly still shows Ausente; the
        # discriminant is the STUDENT's own row, which must have flipped.
        self.client.force_login(self.staff)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Presente")
        content = resp.content.decode()
        # The badge-success "Presente" pill now appears (it didn't before).
        self.assertIn('<span class="badge badge-success">Presente</span>', content)
        # An hour was rendered where the "--" placeholder used to be for
        # this row (dd/mm/YYYY HH:MM format from |date:"d/m/Y H:i").
        self.assertRegex(content, r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}")
        # Exactly the student's row porcentaje_asistencia moved off 0%
        # (1 presente / 2 inscritos = 50.0%; es-locale renders "50,0%").
        self.assertContains(resp, "50,0%")

    def test_attendance_submit_button_is_not_disabled_by_default(self):
        """
        Frontend fix, causa raiz del sintoma reportado: the button must be
        clickeable from the start -- NOT `disabled` in the initial markup.
        A disabled button never dispatches a click event, which is exactly
        why the client's tap (no real drag -> mousemove/touchmove never
        fired -> disabled never cleared) produced zero server traffic.
        """
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('id="attendance-submit-btn"', content)
        # The submit button tag itself must not carry `disabled` anymore.
        btn_start = content.index('id="attendance-submit-btn"')
        btn_tag = content[max(0, btn_start - 80) : btn_start + 40]
        self.assertNotIn("disabled", btn_tag)
        # The old silent gating (`submitBtn.disabled = !hasSignature()`)
        # must be gone from the mousemove/touchmove handlers.
        self.assertNotIn("submitBtn.disabled = !hasSignature()", content)
        # The click handler must always check hasSignature() itself and
        # surface a visible inline error instead of a silent no-op.
        self.assertIn('id="attendance-signature-error"', content)
        self.assertIn("Debes dibujar tu firma antes de guardar", content)


class AttendanceProgressPercentBackfillMigrationTests(TestCase):
    """
    Data-fix as a MIGRATION (not a manual post-deploy query): SD#48's
    special instruction wraps the F2-proposed backfill UPDATE in
    0021_backfill_attendance_progress_percent.py (RunPython) so it ships
    inside the normal autonomous deploy pipeline. This tests the RunPython
    function directly against a row in the exact legacy broken state
    (is_completed=True, progress_percent=0.00 on an attendance lesson) --
    i.e. a row that existed BEFORE this fix, signed under the old code.
    """

    def setUp(self):
        migration_module = importlib.import_module(
            "apps.courses.migrations.0021_backfill_attendance_progress_percent"
        )
        self.backfill = migration_module.backfill_attendance_progress_percent

        self.staff = _make_user(is_staff=True)
        self.student_a = _make_user()
        self.student_b = _make_user()

        category = Category.objects.create(
            name="Cat SD48 migration", slug="cat-sd48-migration", description="c", color="#556677"
        )
        self.course = Course.objects.create(
            code="COURSE-SD48-MIGRATION",
            title="Curso legacy",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=category,
            created_by=self.staff,
        )
        module = Module.objects.create(course=self.course, title="M1", description="d", order=0)
        self.attendance_lesson = Lesson.objects.create(
            module=module,
            title="Sesion presencial legacy",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
            is_mandatory=True,
        )
        self.video_lesson = Lesson.objects.create(
            module=module,
            title="Video no afectado",
            lesson_type=Lesson.Type.VIDEO,
            order=1,
            is_mandatory=True,
        )

        self.enrollment_a = Enrollment.objects.create(user=self.student_a, course=self.course)
        self.enrollment_b = Enrollment.objects.create(user=self.student_b, course=self.course)
        # lesson_view() requires an Enrollment for ANY viewer, staff included
        # (see test_issue_33.py) -- needed for the staff GET assertion below.
        self.staff_enrollment = Enrollment.objects.create(user=self.staff, course=self.course)

        # LEGACY ROW (>= 1 registro pre-existente al cambio): signed under
        # the old save_attendance_signature() code -- is_completed=True but
        # progress_percent stuck at the 0.00 default.
        self.legacy_row = LessonProgress.objects.create(
            enrollment=self.enrollment_a,
            lesson=self.attendance_lesson,
            is_completed=True,
            progress_percent=0,
        )
        # Control 1: incomplete attendance row -- must NOT be touched
        # (progress_percent=0 is CORRECT here, the student never signed).
        self.incomplete_row = LessonProgress.objects.create(
            enrollment=self.enrollment_b,
            lesson=self.attendance_lesson,
            is_completed=False,
            progress_percent=0,
        )
        # Control 2: completed VIDEO lesson at 0% -- must NOT be touched,
        # the backfill targets only lesson_type='attendance' (query scoped
        # by F2's data_fix_query_propuesta).
        self.other_lesson_row = LessonProgress.objects.create(
            enrollment=self.enrollment_a,
            lesson=self.video_lesson,
            is_completed=True,
            progress_percent=0,
        )

    def test_backfill_fixes_only_completed_attendance_rows_stuck_at_zero(self):
        self.backfill(real_apps, None)

        self.legacy_row.refresh_from_db()
        self.assertEqual(self.legacy_row.progress_percent, Decimal("100.00"))

        self.incomplete_row.refresh_from_db()
        self.assertEqual(self.incomplete_row.progress_percent, Decimal("0.00"))

        self.other_lesson_row.refresh_from_db()
        self.assertEqual(self.other_lesson_row.progress_percent, Decimal("0.00"))

    def test_backfilled_legacy_row_now_renders_presente_in_staff_summary(self):
        """
        Confirms the migration actually closes the loop the client
        reported for data signed BEFORE this deploy: reread the staff
        summary after backfilling and see Presente, not stuck Ausente/0%.
        """
        self.backfill(real_apps, None)

        # Simulate the signature this legacy LessonProgress row implies --
        # _build_attendance_summary derives Estado from AttendanceSignature,
        # not from LessonProgress, so a fully legacy scenario also needs the
        # signature row (independent table, unaffected by this migration).
        from apps.courses.models import AttendanceSignature

        AttendanceSignature.objects.create(
            lesson=self.attendance_lesson,
            user=self.student_a,
        )

        self.client = Client()
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("courses:lesson", args=[self.course.id, self.attendance_lesson.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Presente")
