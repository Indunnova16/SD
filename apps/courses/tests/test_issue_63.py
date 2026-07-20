"""
Tests for SD#63 -- Asistencia automatica por curso (reporte PDF FT-HSEQ-60).

Sprint unico (A1-A10), ejecutado como bundle en un solo worktree (ver
SPRINTS/PLAN_2026-07-20_asistencia_automatica_pdf_hseq60.md). Este archivo
concentra TODOS los tests nuevos del issue -- se amplia incrementalmente en
cada sub-item (A2, A4, A5, A6, A7, A9, A10) en vez de crear un archivo por
sub-item, siguiendo lo que F2 ya dejo declarado en `archivos_a_tocar` de A9
y A10.

Decisiones de arquitectura de F2 (ver F2_OUTPUT.decision_arquitectura_autonoma,
implementadas tal cual, pendientes de confirmacion explicita de Miguel):
  1. La firma que alimenta el reporte es `Enrollment.completion_signature`
     (ya existe para TODO curso via `sign_course_completion`) -- NO se
     construye un mecanismo de firma nuevo.
  2. La leccion manual `Lesson.Type.ATTENDANCE` NO se retira ni se migra
     este sprint -- coexiste intacta, solo se oculta del selector al crear
     una leccion NUEVA (A7).
  3. "Tema" del PDF reusa `Course.title` (no se crea un campo nuevo).
  4. El PDF nuevo vive en un template SEPARADO (`course_attendance_pdf.html`),
     `attendance_pdf.html` (flujo legacy per-leccion) queda intacto.

NOTA (detect_hot_files.py): apps/courses/tests.py es compartido con otros
sub-items de este mismo RUN -- este archivo de test es POR-ISSUE
(test_issue_63.py), nunca se apendea a tests.py.
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.forms import CourseCreateForm, CourseEditParamsForm, CourseFullEditForm
from apps.courses.models import (
    AttendanceSignature,
    Category,
    Course,
    Enrollment,
    Lesson,
    Module,
)
from apps.courses.views import _build_course_attendance_summary

# Minimal valid 1x1 transparent PNG, same fixture used across courses tests
# (test_attendance_pdf.py / test_issue_59_a4.py) so ImageField validation
# passes without needing real image bytes.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)

_SEQ = [6300]


def _png_file(name="sig.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


def _make_user(rol=None, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue63_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "SD63",
        "document_number": f"7{n:08d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
        "is_active": True,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_category(n):
    return Category.objects.create(
        name=f"Cat SD63 {n}", slug=f"cat-sd63-{n}", description="c", color="#3B82F6"
    )


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = _make_category(n)
    defaults = {
        "code": f"ISSUE63-{n}",
        "title": f"Curso SD63 {n}",
        "description": "desc",
        "objectives": "obj",
        "course_type": Course.Type.MANDATORY,
        "status": Course.Status.PUBLISHED,
        "category": category,
        "created_by": creator,
    }
    defaults.update(overrides)
    course = Course.objects.create(**defaults)
    module = Module.objects.create(course=course, title="M1", description="d", order=0)
    return course, module


# =============================================================================
# A2 -- Forms: project_name / activity_type / instructor expuestos en las 3
# forms de curso (CourseCreateForm, CourseEditParamsForm, CourseFullEditForm)
# =============================================================================


class CourseAttendanceFieldsFormTestsBase(TestCase):
    """Shared minimal valid data for the 3 course forms."""

    def setUp(self):
        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.category = _make_category("form-a2")


class CourseCreateFormAttendanceFieldsTests(CourseAttendanceFieldsFormTestsBase):
    def _base_data(self):
        return {
            "code": "SD63-CREATE-1",
            "title": "Curso Nuevo",
            "description": "Descripcion",
            "objectives": "Objetivos",
            "course_type": Course.Type.MANDATORY,
            "category": self.category.id,
            "validity_months": "",
            "status": Course.Status.DRAFT,
            "target_profiles": [],
        }

    def test_happy_path_form_valido_con_los_3_campos_completos(self):
        data = self._base_data()
        data.update(
            {
                "project_name": "Proyecto Poda y Tala",
                "activity_type": Course.ActivityType.CAPACITACION,
                "instructor": self.instructor.id,
            }
        )
        form = CourseCreateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        course = form.save(commit=False)
        self.assertEqual(course.project_name, "Proyecto Poda y Tala")
        self.assertEqual(course.activity_type, Course.ActivityType.CAPACITACION)

    def test_edge_form_valido_con_los_3_vacios(self):
        """blank=True a nivel de modelo -> el form tambien debe validar sin
        completarlos (no romper la creacion de un curso que aun no tiene
        estos datos, decision de F2)."""
        data = self._base_data()
        data.update({"project_name": "", "activity_type": "", "instructor": ""})
        form = CourseCreateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_edge_instructor_acepta_none(self):
        data = self._base_data()
        data["instructor"] = ""
        form = CourseCreateForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        course = form.save(commit=False)
        self.assertIsNone(course.instructor_id)

    def test_edge_instructor_queryset_excluye_usuarios_inactivos(self):
        inactive = _make_user(rol=User.Rol.ADMINISTRADOR, is_active=False)
        form = CourseCreateForm()
        self.assertNotIn(inactive, form.fields["instructor"].queryset)
        self.assertIn(self.instructor, form.fields["instructor"].queryset)


class CourseFullEditFormAttendanceFieldsTests(CourseAttendanceFieldsFormTestsBase):
    def setUp(self):
        super().setUp()
        self.course, _ = _make_course(self.creator, category=self.category)

    def _base_data(self):
        return {
            "code": self.course.code,
            "title": self.course.title,
            "description": self.course.description,
            "objectives": self.course.objectives,
            "course_type": self.course.course_type,
            "category": self.category.id,
            "theme_color": "",
            "validity_months": "",
            "status": self.course.status,
            "target_profiles": [],
        }

    def test_happy_path_form_valido_con_los_3_campos_completos(self):
        data = self._base_data()
        data.update(
            {
                "project_name": "Proyecto Poda y Tala",
                "activity_type": Course.ActivityType.CAPACITACION,
                "instructor": self.instructor.id,
            }
        )
        form = CourseFullEditForm(data=data, instance=self.course)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.project_name, "Proyecto Poda y Tala")
        self.assertEqual(saved.instructor_id, self.instructor.id)

    def test_edge_form_valido_con_los_3_vacios(self):
        data = self._base_data()
        data.update({"project_name": "", "activity_type": "", "instructor": ""})
        form = CourseFullEditForm(data=data, instance=self.course)
        self.assertTrue(form.is_valid(), form.errors)


class CourseEditParamsFormAttendanceFieldsTests(CourseAttendanceFieldsFormTestsBase):
    def setUp(self):
        super().setUp()
        self.course, _ = _make_course(self.creator, category=self.category)

    def _base_data(self):
        return {
            "title": self.course.title,
            "description": self.course.description,
            "course_type": self.course.course_type,
            "category": self.category.id,
            "validity_months": "",
            "status": self.course.status,
            "target_profiles": [],
        }

    def test_happy_path_form_valido_con_los_3_campos_completos(self):
        data = self._base_data()
        data.update(
            {
                "project_name": "Proyecto Poda y Tala",
                "activity_type": Course.ActivityType.SIMULACRO,
                "instructor": self.instructor.id,
            }
        )
        form = CourseEditParamsForm(data=data, instance=self.course)
        self.assertTrue(form.is_valid(), form.errors)

    def test_edge_form_valido_con_los_3_vacios(self):
        data = self._base_data()
        data.update({"project_name": "", "activity_type": "", "instructor": ""})
        form = CourseEditParamsForm(data=data, instance=self.course)
        self.assertTrue(form.is_valid(), form.errors)


# =============================================================================
# A4 -- Helper _build_course_attendance_summary(course)
# =============================================================================


class BuildCourseAttendanceSummaryTests(TestCase):
    """Paralelo a _build_attendance_summary (por-lección) pero a nivel de
    curso completo, derivando "presente" de Enrollment.completion_signature
    (SD#63, decisión de arquitectura: reusar la firma de finalización que
    ya existe para todo curso via sign_course_completion)."""

    def setUp(self):
        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(self.creator)

    def test_happy_path_2_enrollments_1_firmado(self):
        signed_user = _make_user()
        unsigned_user = _make_user()
        signed_enrollment = Enrollment.objects.create(
            user=signed_user, course=self.course, status=Enrollment.Status.COMPLETED
        )
        signed_enrollment.completion_signature = _png_file()
        signed_enrollment.completion_signed_at = timezone.now()
        signed_enrollment.save()
        Enrollment.objects.create(user=unsigned_user, course=self.course)

        summary = _build_course_attendance_summary(self.course)

        self.assertEqual(summary["total_inscritos"], 2)
        self.assertEqual(summary["total_presentes"], 1)
        self.assertEqual(summary["total_ausentes"], 1)
        self.assertEqual(summary["porcentaje_asistencia"], 50.0)

        rows_by_doc = {row["document_number"]: row for row in summary["rows"]}
        signed_row = rows_by_doc[signed_user.document_number]
        self.assertTrue(signed_row["presente"])
        self.assertEqual(signed_row["estado"], "Presente")
        self.assertIsNotNone(signed_row["signed_at"])
        self.assertTrue(signed_row["signature_image_url"])
        self.assertEqual(signed_row["job_position"], signed_user.job_position)

        unsigned_row = rows_by_doc[unsigned_user.document_number]
        self.assertFalse(unsigned_row["presente"])
        self.assertEqual(unsigned_row["estado"], "Ausente")
        self.assertIsNone(unsigned_row["signed_at"])
        self.assertEqual(unsigned_row["signature_image_url"], "")

    def test_edge_0_inscritos_no_zero_division_error(self):
        summary = _build_course_attendance_summary(self.course)

        self.assertEqual(summary["total_inscritos"], 0)
        self.assertEqual(summary["total_presentes"], 0)
        self.assertEqual(summary["total_ausentes"], 0)
        self.assertEqual(summary["porcentaje_asistencia"], 0.0)
        self.assertEqual(summary["rows"], [])

    def test_edge_todos_firmados_100_porciento(self):
        for _i in range(3):
            user = _make_user()
            enrollment = Enrollment.objects.create(user=user, course=self.course)
            enrollment.completion_signature = _png_file()
            enrollment.completion_signed_at = timezone.now()
            enrollment.save()

        summary = _build_course_attendance_summary(self.course)

        self.assertEqual(summary["total_inscritos"], 3)
        self.assertEqual(summary["total_presentes"], 3)
        self.assertEqual(summary["porcentaje_asistencia"], 100.0)


# =============================================================================
# A7 -- Builder: ocultar opción "Asistencia" SOLO para lecciones NUEVAS
# =============================================================================


class BuilderHideAttendanceForNewLessonsTests(TestCase):
    """La opción 'Asistencia' del <select name=lesson_type> se oculta al
    crear una lección NUEVA (is_new=True), pero se preserva al editar una
    lección Asistencia ya existente (is_new=False) -- decisión de
    arquitectura F2: cierra la causa raíz de los duplicados sin arriesgar
    corromper el tipo de lecciones reales ya existentes en prod."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, self.module = _make_course(self.administrador)
        self.attendance_lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión Asistencia legacy",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_happy_path_builder_nueva_leccion_no_ofrece_asistencia(self):
        response = self.client.get(
            reverse("courses:course_builder", args=[self.course.id])
        )
        self.assertEqual(response.status_code, 200)
        # El modulo existe -> module_card.html se incluye -> el partial
        # is_new=True de "agregar leccion" esta en el DOM (oculto por Alpine,
        # pero presente en el HTML fuente que ve el test client).
        self.assertContains(response, 'name="lesson_type"')
        self.assertNotContains(response, 'value="attendance"')

    def test_edge_editar_leccion_asistencia_existente_la_conserva(self):
        response = self.client.get(
            reverse(
                "courses:builder_edit_lesson",
                args=[self.course.id, self.module.id, self.attendance_lesson.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="attendance"')
        self.assertContains(response, ">Asistencia<")

    def test_edge_editar_leccion_no_asistencia_existente_si_ofrece_la_opcion(self):
        """El gate de A7 es exclusivamente is_new (creacion) vs edicion, NO
        el lesson_type de la leccion que se esta editando -- por diseno
        (snippet literal de F2): editar CUALQUIER leccion existente
        (is_new=False), sea o no de tipo Asistencia, sigue ofreciendo la
        opcion en el <select>. Solo la creacion de una leccion NUEVA la
        oculta. Documenta el alcance real del fix para que no se asuma un
        filtrado mas fino por accidente en un cambio futuro."""
        video_lesson = Lesson.objects.create(
            module=self.module,
            title="Video existente",
            lesson_type=Lesson.Type.VIDEO,
            order=1,
        )
        response = self.client.get(
            reverse(
                "courses:builder_edit_lesson",
                args=[self.course.id, self.module.id, video_lesson.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="attendance"')


# =============================================================================
# A5 -- Vista+URL export_course_attendance_pdf + gate de validación
# (issue punto 2)
# =============================================================================


class ExportCourseAttendancePdfTests(TestCase):
    """Reusa _attendance_export_required (ADMINISTRADOR + COORDINADOR, ya
    validado en SD#59 A4). Antes de renderizar, exige project_name/
    activity_type/objectives/instructor -- si falta alguno, redirige a
    course_full_edit con un mensaje, sin generar un PDF incompleto."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.client = Client()

    def _complete_course(self):
        course, _module = _make_course(
            self.administrador,
            project_name="Proyecto Poda y Tala",
            activity_type=Course.ActivityType.CAPACITACION,
            objectives="Capacitar en procedimiento seguro",
            instructor=self.instructor,
        )
        return course

    def test_happy_path_curso_completo_devuelve_pdf(self):
        course = self._complete_course()
        signed_user = _make_user()
        enrollment = Enrollment.objects.create(user=signed_user, course=course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

    def test_edge_curso_incompleto_redirige_a_full_edit_con_mensaje(self):
        """Los 8 cursos reales de prod hoy no tienen estos campos -- deben
        bloquear el export con un mensaje, no un PDF a medias."""
        course, _module = _make_course(self.administrador)  # sin los 4 campos

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(
            response, reverse("courses:course_full_edit", args=[course.id])
        )
        messages_list = list(response.context["messages"])
        self.assertTrue(any("Proyecto" in str(m) for m in messages_list))
        self.assertTrue(any("Instructor" in str(m) for m in messages_list))

    def test_edge_curso_incompleto_no_gatea_duration_hours(self):
        """duration_hours NO forma parte del gate -- decision de scope: un
        curso completo en los otros 4 campos pero sin modulos/lecciones
        (0 horas) SI debe poder exportar el PDF."""
        course = self._complete_course()
        self.assertEqual(course.duration_hours, 0)

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_happy_path_coordinador_tambien_exporta(self):
        course = self._complete_course()
        self.client.force_login(self.coordinador)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_edge_ejecutor_es_bloqueado(self):
        course = self._complete_course()
        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id])
        )
        self.assertEqual(response.status_code, 302)
