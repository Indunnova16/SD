"""
Tests for course builder web views (HTMX endpoints).
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Assessment, Question
from apps.courses.models import Category, Course, Lesson, Module


class BuilderEditAssessmentViewTests(TestCase):
    """Tests for builder_edit_assessment view (issue SD#38)."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_edit@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="User",
            document_number="20000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.creator = User.objects.create_user(
            email="creator_edit@test.com",
            password="testpass123",
            first_name="Creator",
            last_name="User",
            document_number="20000002",
            job_position="Instructor",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.other = User.objects.create_user(
            email="other_edit@test.com",
            password="testpass123",
            first_name="Other",
            last_name="User",
            document_number="20000003",
            job_position="Tech",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )

        self.category = Category.objects.create(
            name="Seguridad SD38",
            slug="seguridad-sd38",
            description="cat",
            color="#FF0000",
        )
        self.course = Course.objects.create(
            code="COURSE-SD38-1",
            title="Curso SD38",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        self.assessment = Assessment.objects.create(
            title="Quiz inicial",
            description="desc original",
            assessment_type="quiz",
            passing_score=70,
            time_limit=30,
            max_attempts=3,
            shuffle_questions=True,
            shuffle_answers=True,
            show_correct_answers=True,
            status="draft",
            course=self.course,
            created_by=self.creator,
        )
        # Issue SD#84: publicar (status="published") ahora requiere >=1
        # Question real (ver AssessmentEditForm.clean_status). Este quiz
        # SÍ tiene contenido -- las pruebas de esta clase ejercitan la
        # edición de propiedades, no el guard de "sin preguntas" (para eso
        # ver BuilderEditAssessmentPublishGuardIssue84Tests más abajo).
        Question.objects.create(
            assessment=self.assessment,
            question_type="single_choice",
            text="Pregunta inicial",
            points=1,
            order=0,
        )

        self.url = reverse(
            "courses:builder_edit_assessment",
            kwargs={"course_id": self.course.id, "assessment_id": self.assessment.id},
        )

    def test_get_renders_form_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editar propiedades")
        self.assertContains(resp, "Quiz inicial")

    def test_get_renders_form_for_creator(self):
        self.client.force_login(self.creator)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editar propiedades")

    def test_get_forbidden_for_other_user_htmx(self):
        self.client.force_login(self.other)
        resp = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 403)

    def test_post_valid_updates_assessment(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            self.url,
            data={
                "title": "Quiz actualizado",
                "description": "nueva desc",
                "assessment_type": "exam",
                "passing_score": "3.50",
                "time_limit": 45,
                "max_attempts": 5,
                "shuffle_questions": "on",
                "shuffle_answers": "on",
                "show_correct_answers": "on",
                "status": "published",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # HX-Trigger header set
        self.assertEqual(resp.headers.get("HX-Trigger"), "assessment-updated")

        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.title, "Quiz actualizado")
        self.assertEqual(self.assessment.description, "nueva desc")
        self.assertEqual(self.assessment.assessment_type, "exam")
        self.assertEqual(self.assessment.passing_score, 3.5)
        self.assertEqual(self.assessment.time_limit, 45)
        self.assertEqual(self.assessment.max_attempts, 5)
        self.assertEqual(self.assessment.status, "published")

    def test_post_invalid_passing_score_returns_400(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            self.url,
            data={
                "title": "Quiz",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": 150,  # invalid
                "time_limit": "",
                "max_attempts": 3,
                "status": "draft",
            },
        )
        self.assertEqual(resp.status_code, 400)
        # assessment unchanged
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.passing_score, 70)

    def test_post_forbidden_for_other_user(self):
        self.client.force_login(self.other)
        resp = self.client.post(
            self.url,
            data={
                "title": "Hack",
                "assessment_type": "quiz",
                "passing_score": 50,
                "max_attempts": 1,
                "status": "draft",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 403)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.title, "Quiz inicial")

    def test_anonymous_redirected(self):
        resp = self.client.get(self.url)
        # @login_required redirects to login
        self.assertIn(resp.status_code, (302, 301))

    def test_post_does_not_change_created_by(self):
        """Regression: created_by must NEVER be editable via this form."""
        self.client.force_login(self.staff)
        original_creator_id = self.assessment.created_by_id
        self.client.post(
            self.url,
            data={
                "title": "Quiz",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": "3.50",
                "time_limit": "",
                "max_attempts": 3,
                "status": "draft",
                "created_by": self.staff.id,  # attempt to overwrite
            },
        )
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.created_by_id, original_creator_id)


class BuilderEditAssessmentPublishGuardIssue84Tests(TestCase):
    """Issue SD#84 — punto 2 del fix (guard de creación/publicación).

    Root cause: `builder_edit_assessment` (via `AssessmentEditForm`) es el
    endpoint real de "publicar" una evaluación desde el builder (el campo
    `status` es editable ahí). Antes de este fix, nada impedía guardar
    status='published' sobre una evaluación con 0 preguntas -- exactamente
    el estado en el que quedó el caso real de prod (assessment_id=28,
    'Evaluacion seguridad vial', confirmado por F2 contra BD prod), que
    luego permitía intentos con resultado 0/0.
    """

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_sd84@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD84",
            document_number="84000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD84",
            slug="cat-sd84",
            description="cat",
            color="#00AACC",
        )
        self.course = Course.objects.create(
            code="COURSE-SD84-1",
            title="Curso SD84",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        # Mirrors the real broken prod row (assessment_id=28): draft,
        # 0 questions, about to be (incorrectly) published.
        self.assessment_no_questions = Assessment.objects.create(
            title="Evaluacion sin preguntas SD84",
            description="",
            assessment_type="quiz",
            passing_score=80,
            max_attempts=0,
            status="draft",
            course=self.course,
            created_by=self.staff,
        )
        self.url = reverse(
            "courses:builder_edit_assessment",
            kwargs={"course_id": self.course.id, "assessment_id": self.assessment_no_questions.id},
        )
        self.client.force_login(self.staff)

    def _post_status(self, status):
        return self.client.post(
            self.url,
            data={
                "title": self.assessment_no_questions.title,
                "description": "",
                "assessment_type": "quiz",
                "passing_score": "3.50",
                "time_limit": "",
                "max_attempts": 0,
                "status": status,
            },
        )

    def test_cannot_publish_assessment_with_zero_questions(self):
        """EDGE CASE (SD#84): intentar publicar (status='published') una
        evaluación con 0 preguntas debe rechazarse (400) y la evaluación
        debe permanecer en 'draft' -- NO debe repetirse el caso
        assessment_id=28."""
        resp = self._post_status("published")
        self.assertEqual(resp.status_code, 400)
        self.assessment_no_questions.refresh_from_db()
        self.assertEqual(self.assessment_no_questions.status, "draft")
        self.assertContains(
            resp, "no tiene preguntas todavía", status_code=400
        )

    def test_can_still_save_as_draft_with_zero_questions(self):
        """Guardar explícitamente como 'draft' (sin preguntas) sigue
        funcionando -- el guard solo bloquea 'published'."""
        resp = self._post_status("draft")
        self.assertEqual(resp.status_code, 200)
        self.assessment_no_questions.refresh_from_db()
        self.assertEqual(self.assessment_no_questions.status, "draft")

    def test_can_publish_once_it_has_at_least_one_question(self):
        """HAPPY PATH: agregar 1 pregunta real habilita la publicación
        normalmente -- el guard no bloquea el caso correcto."""
        Question.objects.create(
            assessment=self.assessment_no_questions,
            question_type="single_choice",
            text="Pregunta real",
            points=1,
            order=0,
        )
        resp = self._post_status("published")
        self.assertEqual(resp.status_code, 200)
        self.assessment_no_questions.refresh_from_db()
        self.assertEqual(self.assessment_no_questions.status, "published")


class BuilderAddAttendanceLessonViewTests(TestCase):
    """Reproduce SD#33: creating an "Asistencia" lesson from the course builder.

    Client (anasofiamc1-cpu) report: "El tipo de lección no permite guardar, si
    selecciono Asistencia... no queda guardada la nueva lección de asistencia."

    Root cause (bounce 1, FIX_INCOMPLETO): the required ``scheduled_date`` field
    was hidden by a JS toggle scoped to ``document.querySelector('form[x-data]')``
    (the FIRST x-data form). When the module ALREADY had a lesson, that lookup hit
    the wrong form, so picking "Asistencia" never revealed ``scheduled_date`` and
    ``LessonBuilderForm.clean()`` rejected the POST. The visual fix is template/JS
    (Alpine x-show, validated by the E2E journey); these view tests pin the
    server-side contract and the legacy-data case (module not empty).
    """

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_att@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="Att",
            document_number="33000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD33",
            slug="cat-sd33",
            description="cat",
            color="#00AA00",
        )
        self.course = Course.objects.create(
            code="COURSE-SD33-1",
            title="Curso SD33",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        self.module = Module.objects.create(
            course=self.course, title="Modulo SD33", description="m", order=1
        )
        # Legacy data: the module already has a prior lesson (mirrors the
        # client's screenshot where the module had an EVALUACION_PT lesson).
        self.legacy_lesson = Lesson.objects.create(
            module=self.module,
            title="EVALUACION_PT legacy",
            description="leccion previa",
            lesson_type=Lesson.Type.QUIZ,
            order=0,
        )
        self.url = reverse(
            "courses:builder_add_lesson",
            kwargs={"course_id": self.course.id, "module_id": self.module.id},
        )

    def test_attendance_without_scheduled_date_is_created(self):
        """SD#57.1: scheduled_date ya NO es obligatorio para Asistencia (decision
        de Miguel, cambio de requisito). POST attendance SIN scheduled_date ->
        la leccion SE CREA con scheduled_date=None.

        (Este test invierte el comportamiento anterior, pinneado por
        test_attendance_without_scheduled_date_is_rejected antes de SD#57:
        antes clean() rechazaba el POST cuando faltaba la fecha; ahora se
        permite guardar sin fecha.)
        """
        self.client.force_login(self.staff)
        before = Lesson.objects.filter(
            module=self.module, lesson_type=Lesson.Type.ATTENDANCE
        ).count()
        resp = self.client.post(
            self.url,
            data={
                "title": "Asistencia sin fecha",
                "lesson_type": "attendance",
                "is_mandatory": "on",
                "duration": "0",
                # scheduled_date intentionally omitted -> ahora debe permitirse
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        after = Lesson.objects.filter(
            module=self.module, lesson_type=Lesson.Type.ATTENDANCE
        ).count()
        self.assertEqual(after, before + 1)
        lesson = Lesson.objects.get(module=self.module, title="Asistencia sin fecha")
        self.assertEqual(lesson.lesson_type, Lesson.Type.ATTENDANCE)
        self.assertIsNone(lesson.scheduled_date)

    def test_attendance_with_scheduled_date_is_created(self):
        """Happy path: attendance + scheduled_date persists with type attendance."""
        self.client.force_login(self.staff)
        resp = self.client.post(
            self.url,
            data={
                "title": "QA_E2E_M33 Asistencia OK",
                "lesson_type": "attendance",
                "is_mandatory": "on",
                "duration": "0",
                "scheduled_date": "2030-01-15T09:30",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M33 Asistencia OK")
        self.assertEqual(lesson.lesson_type, Lesson.Type.ATTENDANCE)
        self.assertIsNotNone(lesson.scheduled_date)
        self.assertEqual(lesson.scheduled_date.year, 2030)
        self.assertEqual(lesson.scheduled_date.month, 1)
        self.assertEqual(lesson.scheduled_date.day, 15)
        # Badge text comes from get_lesson_type_display -> "Asistencia".
        self.assertEqual(lesson.get_lesson_type_display(), "Asistencia")

    def test_attendance_created_even_when_module_not_empty(self):
        """Legacy-data case: the module already has a prior lesson (the bug
        condition). Creating the attendance lesson must still work."""
        self.client.force_login(self.staff)
        self.assertTrue(
            Lesson.objects.filter(module=self.module, pk=self.legacy_lesson.pk).exists()
        )
        resp = self.client.post(
            self.url,
            data={
                "title": "QA_E2E_M33 Asistencia con legacy",
                "lesson_type": "attendance",
                "is_mandatory": "on",
                "duration": "0",
                "scheduled_date": "2030-02-20T14:00",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M33 Asistencia con legacy")
        self.assertEqual(lesson.lesson_type, Lesson.Type.ATTENDANCE)
        self.assertIsNotNone(lesson.scheduled_date)
        # The legacy lesson is untouched and both coexist in the module.
        self.legacy_lesson.refresh_from_db()
        self.assertEqual(self.legacy_lesson.lesson_type, Lesson.Type.QUIZ)
        self.assertEqual(self.module.lessons.count(), 2)
