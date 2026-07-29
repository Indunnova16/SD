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

import base64
import re
from datetime import date
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template, render_to_string
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
from apps.courses.views import (
    _attendance_pdf_branding_context,
    _build_course_attendance_summary,
)

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


# =============================================================================
# A6 -- Vistas+URLs course-level: lista + detalle de asistencia por curso
# =============================================================================


class CourseAttendanceReportsListTests(TestCase):
    """course_attendance_reports_list (name=attendance_reports) -- mismo
    gate ADMINISTRADOR+COORDINADOR que el roster/export per-leccion."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.course, _module = _make_course(self.administrador, title="Curso Listado A6")
        self.client = Client()
        self.url = reverse("courses:attendance_reports")

    def test_happy_path_administrador_ve_la_lista(self):
        self.client.force_login(self.administrador)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Curso Listado A6")

    def test_happy_path_coordinador_ve_la_lista(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_edge_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_edge_busqueda_filtra_por_titulo(self):
        _make_course(self.administrador, title="Otro Curso Distinto")
        self.client.force_login(self.administrador)
        response = self.client.get(self.url, {"search": "Listado A6"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Curso Listado A6")
        self.assertNotContains(response, "Otro Curso Distinto")


class CourseAttendanceReportDetailTests(TestCase):
    """course_attendance_report_detail -- roster on-screen + boton
    descargar. Mismo gate que la lista."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.administrador,
            project_name="Proyecto Detalle",
            activity_type=Course.ActivityType.CHARLA,
            instructor=self.instructor,
        )
        self.client = Client()
        self.url = reverse("courses:course_attendance_report_detail", args=[self.course.id])

    def test_happy_path_muestra_roster_correcto(self):
        signed_user = _make_user(first_name="Firmante", last_name="Uno")
        unsigned_user = _make_user(first_name="Pendiente", last_name="Dos")
        signed_enrollment = Enrollment.objects.create(user=signed_user, course=self.course)
        signed_enrollment.completion_signature = _png_file()
        signed_enrollment.completion_signed_at = timezone.now()
        signed_enrollment.save()
        Enrollment.objects.create(user=unsigned_user, course=self.course)

        self.client.force_login(self.administrador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_inscritos"], 2)
        self.assertEqual(response.context["total_presentes"], 1)
        self.assertContains(response, "Firmante Uno")
        self.assertContains(response, "Pendiente Dos")
        self.assertContains(response, "Descargar PDF")

    def test_edge_curso_incompleto_muestra_alerta_y_oculta_boton(self):
        incomplete_course, _m = _make_course(self.administrador)  # sin los 4 campos
        url = reverse("courses:course_attendance_report_detail", args=[incomplete_course.id])

        self.client.force_login(self.administrador)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["missing_fields"])
        self.assertContains(response, "Reporte incompleto")
        self.assertNotContains(response, "Descargar PDF")

    def test_edge_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_happy_path_coordinador_accede(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


# =============================================================================
# A8 -- Navbar: link "Asistencia por Curso" (desktop + movil)
# =============================================================================


class NavbarAttendanceReportsLinkTests(TestCase):
    """Issue #63 (comentario de seguimiento 2026-07-17): el link "Asistencia
    por Curso" debe verse en el navbar (Operaciones) para Coordinador y
    Administrador, igual que "Eventos de asistencia" ya se ve para
    Administrador."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.client = Client()
        self.url = reverse("courses:list")

    def test_happy_path_coordinador_ve_el_link(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asistencia por Curso")

    def test_happy_path_administrador_ve_el_link(self):
        self.client.force_login(self.administrador)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asistencia por Curso")

    def test_edge_ejecutor_no_ve_el_link(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Asistencia por Curso")


# =============================================================================
# A9 -- Test de regresión RBAC consolidado sobre las 3 vistas nuevas
# =============================================================================


class RbacRegressionAttendanceViewsTests(TestCase):
    """Issue #63 punto 4: "ya implementado, no romperlo al mover la lógica
    fuera de la lección manual" -- EJECUTOR bloqueado, COORDINADOR y
    ADMINISTRADOR permitidos, en las 3 vistas NUEVAS de este sprint
    (attendance_reports, course_attendance_report_detail,
    export_course_attendance_pdf). Consolidado en un solo lugar (no
    duplica los tests funcionales de A5/A6, es el guard-rail RBAC
    dedicado -- mismo patrón que test_issue_59_a4.py)."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.administrador,
            project_name="Proyecto RBAC A9",
            activity_type=Course.ActivityType.OTRA,
            instructor=self.instructor,
        )
        self.client = Client()
        self.urls = {
            "attendance_reports": reverse("courses:attendance_reports"),
            "course_attendance_report_detail": reverse(
                "courses:course_attendance_report_detail", args=[self.course.id]
            ),
            "export_course_attendance_pdf": reverse(
                "courses:export_course_attendance_pdf", args=[self.course.id]
            ),
        }

    def test_edge_ejecutor_bloqueado_en_las_3_vistas(self):
        self.client.force_login(self.ejecutor)
        for name, url in self.urls.items():
            with self.subTest(view=name):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    302,
                    f"{name} deberia redirigir (302) a un Ejecutor, obtuvo {response.status_code}",
                )

    def test_happy_path_coordinador_permitido_en_las_3_vistas(self):
        self.client.force_login(self.coordinador)
        for name, url in self.urls.items():
            with self.subTest(view=name):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{name} deberia permitir (200) a un Coordinador, obtuvo {response.status_code}",
                )

    def test_happy_path_administrador_permitido_en_las_3_vistas(self):
        self.client.force_login(self.administrador)
        for name, url in self.urls.items():
            with self.subTest(view=name):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{name} deberia permitir (200) a un Administrador, obtuvo {response.status_code}",
                )


# =============================================================================
# A10 -- Tests unitarios consolidados + smoke E2E (via Django test client)
# =============================================================================
#
# NOTA sobre "dato real de prod (curso id=63)": F3 NO recibe credenciales de
# BD prod por diseño (ver _common.md -- solo F2/F5 las reciben; F1/F3 nunca).
# El journey mutativo m1_i63_gate_bloquea_y_pdf_curso_real del RUN (F5/E2E
# post-deploy, run_e2e_or_die.py) es quien reproduce el escenario contra el
# curso real id=63 "INDUCCIÓN PODA Y TALA" con sus 2 enrollments ya firmados
# via completion_signature (confirmado en BD prod por F2). Este archivo
# cubre la contraparte determinista con fixtures propias -- ambos together
# son la cobertura completa exigida por el protocolo (unit local + E2E
# contra dato real).


class ConsolidatedSmokeE2ETests(TestCase):
    """Happy path consolidado: lista -> detalle -> export PDF sobre el MISMO
    curso, verificando que los 3 vean datos consistentes entre si (A6 + A5
    + A4 integrados)."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.administrador,
            title="Curso Smoke E2E A10",
            project_name="Proyecto Smoke",
            activity_type=Course.ActivityType.SOCIALIZACION,
            instructor=self.instructor,
        )
        for i in range(3):
            user = _make_user()
            enrollment = Enrollment.objects.create(user=user, course=self.course)
            if i < 1:  # 1 de 3 firmado -> 33.3%
                enrollment.completion_signature = _png_file()
                enrollment.completion_signed_at = timezone.now()
                enrollment.save()
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_happy_path_lista_detalle_export_consistentes(self):
        list_response = self.client.get(reverse("courses:attendance_reports"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Curso Smoke E2E A10")

        detail_response = self.client.get(
            reverse("courses:course_attendance_report_detail", args=[self.course.id])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.context["missing_fields"])
        self.assertEqual(detail_response.context["total_inscritos"], 3)
        self.assertEqual(detail_response.context["total_presentes"], 1)
        # 1/3 -> edge case de redondeo (no 33 ni 34 planos)
        self.assertEqual(detail_response.context["porcentaje_asistencia"], 33.3)

        export_response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[self.course.id])
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "application/pdf")
        content = (
            export_response.getvalue()
            if hasattr(export_response, "getvalue")
            else export_response.content
        )
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 800)


class GateEdgeCasesTests(TestCase):
    """Edge cases adicionales del gate de completitud (A5) no cubiertos por
    los tests puntuales de A5/A6: completitud PARCIAL (solo algunos de los
    4 campos)."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_edge_solo_project_name_completo_sigue_bloqueado(self):
        # objectives="" override explicito: _make_course defaultea
        # objectives="obj", este caso necesita los otros 3 campos vacios
        # para probar que 1 campo completo (project_name) no alcanza.
        course, _module = _make_course(
            self.administrador, project_name="Solo esto esta completo", objectives=""
        )
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id]),
            follow=True,
        )
        self.assertRedirects(
            response, reverse("courses:course_full_edit", args=[course.id])
        )
        messages_list = list(response.context["messages"])
        joined = " ".join(str(m) for m in messages_list)
        self.assertNotIn("Proyecto", joined)  # este SI esta completo
        self.assertIn("Instructor", joined)
        self.assertIn("Tipo de actividad", joined)
        self.assertIn("Objetivo", joined)

    def test_edge_falta_solo_instructor_lo_lista(self):
        course, _module = _make_course(
            self.administrador,
            project_name="P",
            activity_type=Course.ActivityType.SIMULACRO,
        )
        # objectives ya viene con default "obj" en _make_course
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id]),
            follow=True,
        )
        self.assertRedirects(
            response, reverse("courses:course_full_edit", args=[course.id])
        )
        messages_list = list(response.context["messages"])
        joined = " ".join(str(m) for m in messages_list)
        self.assertIn("Instructor", joined)
        self.assertNotIn("Proyecto,", joined)


class LegacyAttendanceFlowUntouchedTests(TestCase):
    """Regresion (decision de arquitectura F2 #2 y #4): el flujo LEGACY
    per-lección (Lesson.Type.ATTENDANCE + attendance_pdf.html +
    export_attendance_pdf) sigue intacto y funcionando -- este sprint NO lo
    retira ni lo migra, solo deja de ofrecerlo al CREAR una lección nueva
    (A7)."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, self.module = _make_course(self.administrador)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión Asistencia legacy A10",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        signer = _make_user()
        Enrollment.objects.create(user=signer, course=self.course)
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=signer)
        sig.signature_image.save("sig.png", _png_file(), save=True)
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_edge_legacy_export_attendance_pdf_sigue_funcionando(self):
        response = self.client.get(
            reverse("courses:export_attendance_pdf", args=[self.course.id, self.lesson.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_edge_legacy_attendance_lesson_view_sigue_funcionando(self):
        Enrollment.objects.create(user=self.administrador, course=self.course)
        response = self.client.get(
            reverse("courses:attendance_lesson", args=[self.course.id, self.lesson.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sesión Asistencia legacy A10")


# =============================================================================
# Reproceso 2026-07-22 -- rediseño de los 2 templates PDF contra el oficial
# FT-HSEQ-60 (ver F2_OUTPUT.reproceso_analisis: PR #66 hereda branding
# genérico del aplicativo -- bandas azules, badge Estado, sección "Resumen de
# Asistencia" -- en vez de partir del formato impreso oficial). Cubre los 5
# puntos corregidos:
#   1. blanco y negro (sin #2563eb)
#   2. Tipo de actividad como fila de casillas (Charla/Capacitación/
#      Simulacro/Socialización/Otra+Especifique+Tiempo)
#   3. Firmantes a exactamente 5 columnas (No./Nombre completo/Cédula/
#      Cargo/Firma, sin "Estado")
#   4. eliminada la sección "Resumen de Asistencia" (no existe en el oficial)
#   5. "Eficacia de la Capacitación" completa (texto oficial + los 2 rangos
#      de escala que ya existían, preservados tal cual)
# Oráculo: SPRINTS/RUN_2026-07-22_1403/attachments/SD_63/FT-HSEQ-60.md
# Evidencia visual real (PDFs de prod): F2_OUTPUT.evidencia.
# =============================================================================


def _course_pdf_context(course, rows=None, **overrides):
    rows = rows or []
    context = {
        "course": course,
        "rows": rows,
        "total_inscritos": len(rows),
        "total_presentes": 0,
        "total_ausentes": len(rows),
        "porcentaje_asistencia": 0.0,
        "generated_at": timezone.now(),
        "request_user": None,
        "instructor_signature_url": "",
    }
    # Branding (SD#63) -- wired en produccion via
    # `context.update(_attendance_pdf_branding_context())` en
    # `export_course_attendance_pdf`. Default aqui refleja ese wiring real
    # (logo_data_uri vacio por defecto -- no depende de leer el asset del
    # disco en cada test) para que los tests existentes que NO pasan
    # overrides sigan renderizando el mismo HTML que produccion. NO hay
    # `brand_accent`: FT-HSEQ-60 es blanco y negro (bounce 2026-07-28).
    context.update({"logo_data_uri": ""})
    context.update(overrides)
    return context


def _legacy_pdf_context(course, lesson=None, rows=None, **overrides):
    rows = rows or []
    context = {
        "course": course,
        "lesson": lesson,
        "rows": rows,
        "total_inscritos": len(rows),
        "total_presentes": 0,
        "total_ausentes": len(rows),
        "porcentaje_asistencia": 0.0,
        "generated_at": timezone.now(),
        "request_user": None,
        "responsable": None,
        "responsable_signature_url": "",
        # SD#63 -- branding compartido (solo logo), mismo default que
        # _attendance_pdf_branding_context() en producción; los tests de
        # branding pisan esta clave explícitamente via overrides. NO hay
        # `brand_accent`: FT-HSEQ-60 es blanco y negro (bounce 2026-07-28).
        "logo_data_uri": "",
    }
    context.update(overrides)
    return context


class CourseAttendancePdfOfficialFormatTests(TestCase):
    """course_attendance_pdf.html contra el oficial FT-HSEQ-60 -- asserts
    deterministas sobre el HTML pre-render (sin generar el PDF binario)."""

    def setUp(self):
        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.creator,
            project_name="Proyecto Poda y Tala",
            activity_type=Course.ActivityType.SIMULACRO,
            objectives="Capacitar en procedimiento seguro",
        )
        self.row = {
            "user": self.creator,
            "full_name": self.creator.get_full_name(),
            "document_number": self.creator.document_number,
            "job_position": self.creator.job_position,
            "presente": True,
            "estado": "Presente",
            "signed_at": timezone.now(),
            "signature_image_url": "",
        }

    def test_happy_path_sin_bandas_azules(self):
        html = render_to_string(
            "courses/course_attendance_pdf.html", _course_pdf_context(self.course)
        )
        self.assertNotIn("#2563eb", html)

    def test_happy_path_sin_resumen_de_asistencia(self):
        html = render_to_string(
            "courses/course_attendance_pdf.html", _course_pdf_context(self.course)
        )
        self.assertNotIn("Resumen de Asistencia", html)
        self.assertNotIn("% Asistencia", html)

    def test_happy_path_firmantes_6_columnas_exactas_sin_estado(self):
        """Actualizado en el bounce 2026-07-27 (SD#63, A2): el cliente pidio
        deliberadamente una 6a columna "Fecha de firma" ademas de las 5 del
        oraculo FT-HSEQ-60 original (No./Nombre completo/Cedula/Cargo/Firma).
        Sigue sin "Estado" -- eso NO volvio, es el unico punto del bounce 2
        que se preserva intacto aqui."""
        html = render_to_string(
            "courses/course_attendance_pdf.html",
            _course_pdf_context(self.course, rows=[self.row]),
        )
        self.assertIn(">No.<", html)
        self.assertIn("Nombre completo", html)
        self.assertIn("Cédula", html)
        self.assertIn("Cargo", html)
        self.assertIn("Fecha de firma", html)
        self.assertNotIn(">Estado<", html)
        self.assertNotIn("badge-presente", html)
        self.assertNotIn("badge-ausente", html)

    def test_happy_path_tipo_de_actividad_marca_la_opcion_real(self):
        html = render_to_string(
            "courses/course_attendance_pdf.html",
            _course_pdf_context(self.course, rows=[self.row]),
        )
        for label in ("Charla", "Capacitación", "Simulacro", "Socialización", "Otra"):
            self.assertIn(label, html)
        match = re.search(
            r'activity-checkbox">X</td>\s*<td class="activity-label">([^<]+)</td>', html
        )
        self.assertIsNotNone(match, "ninguna casilla de tipo de actividad quedo marcada")
        self.assertEqual(match.group(1), "Simulacro")
        self.assertEqual(html.count('activity-checkbox">X<'), 1)

    def test_edge_sin_activity_type_ninguna_casilla_marcada(self):
        course, _m = _make_course(self.creator)  # activity_type vacio
        html = render_to_string("courses/course_attendance_pdf.html", _course_pdf_context(course))
        self.assertEqual(html.count('activity-checkbox">X<'), 0)

    def test_happy_path_eficacia_de_la_capacitacion_completa(self):
        html = render_to_string(
            "courses/course_attendance_pdf.html", _course_pdf_context(self.course)
        )
        self.assertIn("Se determina por medio de evaluación", html)
        self.assertIn(
            "Promedio de los resultados de la evaluación realizados a los "
            "trabajadores que asistieron a la capacitación.",
            html,
        )
        # Rangos de escala (NOTA1 del oficial) preservados tal cual
        self.assertIn("Requiere refuerzo", html)
        self.assertIn("Aprueba", html)


class LegacyAttendancePdfOfficialFormatTests(TestCase):
    """attendance_pdf.html (legacy per-lección) -- mismo rediseño oficial.
    Confirma ademas que la vista SI pasa el objeto Course completo al
    contexto de este template (``export_attendance_pdf``,
    apps/courses/views.py: ``"course": course,``), por lo que
    ``course.activity_type``/``course.duration_hours`` son accesibles sin
    tocar vista ni modelo -- contrario a lo que F2 asumió en su narrativa
    ("la lección legacy no tiene esos campos de curso en su contexto de
    lesson-level"), se agregaron por consistencia ya que el dato SI existe."""

    def setUp(self):
        self.creator = _make_user(
            rol=User.Rol.ADMINISTRADOR, is_staff=True, job_position="Ingeniero HSEQ"
        )
        self.course, self.module = _make_course(
            self.creator, activity_type=Course.ActivityType.CHARLA
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión Asistencia legacy",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        self.row = {
            "user": self.creator,
            "full_name": self.creator.get_full_name(),
            "document_number": self.creator.document_number,
            "presente": True,
            "estado": "Presente",
            "signed_at": timezone.now(),
            "signature_image_url": "",
        }

    def test_happy_path_sin_bandas_azules(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson),
        )
        self.assertNotIn("#2563eb", html)

    def test_happy_path_sin_resumen_de_asistencia(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson),
        )
        self.assertNotIn("Resumen de Asistencia", html)

    def test_happy_path_firmantes_5_columnas_exactas(self):
        """Bounce 2026-07-27: el cliente ahora pide DELIBERADAMENTE una 6a
        columna "Fecha de firma" -- este test (correccion valida del bounce
        anterior, que fijaba el formato del oracle FT-HSEQ-60 a 5 columnas)
        se actualiza a la nueva realidad de 6 columnas, no se borra."""
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        self.assertIn(">No.<", html)
        self.assertIn("Nombre completo", html)
        self.assertIn("Cédula", html)
        self.assertIn("Cargo", html)
        self.assertIn("Fecha de firma", html)
        self.assertNotIn(">Estado<", html)
        self.assertEqual(html.count("<th "), 6)
        # Cargo sale de row.user.job_position -- el dict de fila de
        # _build_attendance_summary YA trae el objeto user completo, no
        # requirió tocar la vista.
        self.assertIn("Ingeniero HSEQ", html)

    def test_happy_path_tipo_de_actividad_y_eficacia_agregados_por_consistencia(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        match = re.search(
            r'activity-checkbox">X</td>\s*<td class="activity-label">([^<]+)</td>', html
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "Charla")
        self.assertIn("Se determina por medio de evaluación", html)

    def test_edge_firma_del_responsable_no_se_toco(self):
        """Fuera de scope de los 5 fixes -- regresión: la sección se
        preserva intacta (SD#51)."""
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, responsable=self.creator),
        )
        self.assertIn("Firma del Responsable", html)
        self.assertIn(self.creator.get_full_name(), html)


def _extract_pdf_text(testcase, pdf_bytes):
    """Genera texto real con pdftotext (poppler) a partir de bytes de PDF --
    confirma que xhtml2pdf/pisa efectivamente soporta el markup nuevo
    (colspan mixto en .activity-type-table), no solo que el HTML fuente sea
    correcto. Se salta (no falla) si pdftotext no está en el entorno."""
    import shutil
    import subprocess
    import tempfile

    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        testcase.skipTest("pdftotext no disponible en este entorno")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        result = subprocess.run(
            [pdftotext, "-layout", f.name, "-"],
            capture_output=True,
            text=True,
            check=True,
        )
    return result.stdout


class CoursePdfRealRenderTests(TestCase):
    """Genera el PDF real (misma ruta que la vista: xhtml2pdf/pisa) para el
    reporte por-curso y extrae texto -- valida que el motor de render, no
    solo el HTML fuente, produzca las 5 correcciones."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.administrador,
            title="Curso Render Real 63",
            project_name="Proyecto Render",
            activity_type=Course.ActivityType.CAPACITACION,
            instructor=self.instructor,
        )
        signed_user = _make_user(job_position="Operario")
        enrollment = Enrollment.objects.create(user=signed_user, course=self.course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_happy_path_pdf_real_contiene_las_5_correcciones(self):
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[self.course.id])
        )
        self.assertEqual(response.status_code, 200)
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

        text_lower = _extract_pdf_text(self, content).lower()
        self.assertNotIn("resumen de asistencia", text_lower)
        self.assertNotIn("estado", text_lower)
        self.assertIn("capacit", text_lower)  # CAPACITACIÓN marcada
        self.assertIn("firmantes", text_lower)
        self.assertIn("cargo", text_lower)
        self.assertIn("eficacia", text_lower)


class LegacyPdfRealRenderTests(TestCase):
    """Mismo chequeo de render real sobre el flujo legacy per-lección."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, self.module = _make_course(
            self.administrador, activity_type=Course.ActivityType.OTRA
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión Asistencia legacy render",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        signer = _make_user(job_position="Supervisor")
        Enrollment.objects.create(user=signer, course=self.course)
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=signer)
        sig.signature_image.save("sig.png", _png_file(), save=True)
        self.client = Client()
        self.client.force_login(self.administrador)

    def test_happy_path_pdf_real_contiene_las_correcciones(self):
        response = self.client.get(
            reverse("courses:export_attendance_pdf", args=[self.course.id, self.lesson.id])
        )
        self.assertEqual(response.status_code, 200)
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

        text_lower = _extract_pdf_text(self, content).lower()
        self.assertNotIn("resumen de asistencia", text_lower)
        self.assertNotIn("fecha y hora de firma", text_lower)
        self.assertNotIn("estado", text_lower)
        self.assertIn("cargo", text_lower)
        self.assertIn("supervisor", text_lower)
        self.assertIn("firmantes", text_lower)
        self.assertIn("eficacia", text_lower)


# =============================================================================
# A1 -- Helper compartido _attendance_pdf_branding_context() (logo + acento
# #e4020f). Sub-item aislado de este mismo issue (bounce 2026-07-27): NO se
# llama todavia desde las vistas PDF -- eso lo hacen A2/A3/A4 en sus propios
# worktrees, mergeados despues por el orquestador. Testeado aqui de forma
# aislada, sin depender de ninguna vista.
# =============================================================================


class AttendancePdfBrandingContextTests(TestCase):
    """Helper puro, sin request/DB -- lee el asset del logo desde disco
    (apps/certifications/migrations/assets/sd_sas_logo_v2_real.png, confirmado
    presente en el contenedor de Cloud Run por F2) y arma el data URI +
    color de marca compartido por las 3 vistas PDF."""

    def test_happy_path_logo_data_uri_decodifica_a_png_valido(self):
        context = _attendance_pdf_branding_context()
        self.assertTrue(context["logo_data_uri"].startswith("data:image/png;base64,"))
        b64_payload = context["logo_data_uri"].split(",", 1)[1]
        decoded = base64.b64decode(b64_payload)
        self.assertTrue(decoded.startswith(b"\x89PNG"))

    def test_regresion_no_expone_color_de_marca(self):
        """Bounce 2026-07-28: el cliente rechazo el rojo corporativo en este
        documento -- FT-HSEQ-60 es un formato regulado blanco y negro. El
        helper NO debe volver a exponer un acento de marca; si alguien lo
        reintroduce aqui, los templates volverian a pintarse de rojo."""
        context = _attendance_pdf_branding_context()
        self.assertNotIn("brand_accent", context)
        self.assertEqual(set(context), {"logo_data_uri"})

    def test_edge_archivo_ausente_no_levanta_excepcion(self):
        """Si el asset no se puede leer (FileNotFoundError/OSError), el
        helper NUNCA debe propagar la excepcion -- las vistas PDF deben
        seguir renderizando sin logo (logo_data_uri=''), nunca 500."""
        with mock.patch("apps.courses.views.open", side_effect=FileNotFoundError, create=True):
            context = _attendance_pdf_branding_context()
        self.assertEqual(context["logo_data_uri"], "")


# =============================================================================
# A2 -- Wiring de branding (logo + acento #e4020f) + columna "Fecha de firma"
# en course_attendance_pdf.html (PDF "Grupal"). Bounce 2026-07-27 (SD#63):
# el cliente pidio (a) el logo de la empresa en el encabezado, (b) el rojo
# corporativo como acento (NUNCA como banda de fondo -- eso fue removido
# explicitamente en el bounce 2 y reintroducirlo seria una regresion), y (c)
# una 6a columna "Fecha de firma" en la tabla de firmantes. El helper
# `_attendance_pdf_branding_context()` (A1) ya esta probado de forma aislada
# arriba -- esta clase prueba el WIRING en el template real (contexto ->
# HTML), no el helper.
# =============================================================================


class CourseAttendancePdfBrandingAndSignedAtColumnTests(TestCase):
    """course_attendance_pdf.html con branding (solo logo) + columna Fecha de
    firma via _course_pdf_context(), que incluye logo_data_uri por defecto
    reflejando el wiring real de export_course_attendance_pdf. El documento NO
    lleva color de marca: es un formato regulado blanco y negro (bounce
    2026-07-28), cubierto por los tests de regresion de esta clase.

    Usa `get_template(...).render(context)` (equivalente a `render_to_string`,
    mismo motor de templates) en vez de `render_to_string` directo: aserta
    explicitamente contra el HTML SERVIDO por el template real, no solo
    contra el contexto/form -- la superficie que rompio NOVAPCR (#328)."""

    @staticmethod
    def _render(context):
        return get_template("courses/course_attendance_pdf.html").render(context)

    def setUp(self):
        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, _module = _make_course(
            self.creator,
            project_name="Proyecto Poda y Tala",
            activity_type=Course.ActivityType.SIMULACRO,
            objectives="Capacitar en procedimiento seguro",
        )
        self.row = {
            "user": self.creator,
            "full_name": self.creator.get_full_name(),
            "document_number": self.creator.document_number,
            "job_position": self.creator.job_position,
            "presente": True,
            "estado": "Presente",
            "signed_at": timezone.now(),
            "signature_image_url": "",
        }

    def test_happy_path_logo_embebido_en_el_header(self):
        context = _course_pdf_context(
            self.course,
            rows=[self.row],
            logo_data_uri="data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode("ascii"),
        )
        html = self._render(context)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn('class="header-logo"', html)

    def test_regresion_sin_rojo_corporativo_bounce_2026_07_28(self):
        """El cliente rechazo el acento rojo en este documento: FT-HSEQ-60 es
        un formato regulado que replica el papel oficial, blanco y negro. El
        rojo de SD#69 es para la UI general de la app, no para este PDF."""
        html = self._render(_course_pdf_context(self.course, rows=[self.row]))
        self.assertNotIn("#e4020f", html)
        self.assertIn("#1a1a1a", html)

    def test_regresion_logo_con_tamano_explicito_no_max_height(self):
        """xhtml2pdf ignora max-width/max-height sobre <img>: con `max-height`
        el logo se dibujaba a 524,7 x 349,8 pt (todo el ancho util de la
        pagina). El tamano debe declararse con width/height explicitos."""
        html = self._render(
            _course_pdf_context(
                self.course,
                rows=[self.row],
                logo_data_uri="data:image/png;base64,"
                + base64.b64encode(_PNG_BYTES).decode("ascii"),
            )
        )
        logo_css = html.split(".header-logo {")[1].split("}")[0]
        self.assertIn("width: 90pt", logo_css)
        self.assertIn("height: 60pt", logo_css)
        self.assertNotIn("max-height", logo_css)
        self.assertNotIn("max-width", logo_css)

    def test_happy_path_columna_fecha_de_firma_con_valor_formateado(self):
        from django.utils.formats import date_format
        from django.utils.timezone import template_localtime

        signed_at = timezone.now()
        row = dict(self.row, signed_at=signed_at)
        html = self._render(_course_pdf_context(self.course, rows=[row]))
        self.assertIn("Fecha de firma", html)
        expected = date_format(template_localtime(signed_at), "d/m/Y H:i")
        self.assertIn(expected, html)

    def test_edge_signed_at_none_renderiza_placeholder_sin_error(self):
        row = dict(self.row, signed_at=None)
        html = self._render(_course_pdf_context(self.course, rows=[row]))
        self.assertIn("Fecha de firma", html)
        self.assertIn("—", html)

    def test_edge_logo_data_uri_vacio_no_renderiza_img_roto(self):
        html = self._render(
            _course_pdf_context(self.course, rows=[self.row], logo_data_uri="")
        )
        self.assertNotIn("data:image/png;base64,", html)
        self.assertNotIn('class="header-logo"', html)

    def test_regresion_sigue_sin_banda_azul(self):
        html = self._render(_course_pdf_context(self.course, rows=[self.row]))
        self.assertNotIn("#2563eb", html)

    def test_edge_roster_vacio_colspan_ajustado_a_6(self):
        html = self._render(_course_pdf_context(self.course, rows=[]))
        self.assertIn('colspan="6"', html)


# =============================================================================
# A4 -- PDF Individual (feature nueva): vista + URL + boton. Decision de
# arquitectura F2 (no reabierta): reusa course_attendance_pdf.html
# parametrizado con rows=[fila_unica] + is_individual=True -- NO se crea un
# template course_attendance_pdf_individual.html nuevo, el Individual hereda
# logo/color/columna "Fecha de firma" de A2 gratis.
# =============================================================================


class ExportCourseAttendancePdfIndividualTests(TestCase):
    """export_course_attendance_pdf_individual (name=
    export_course_attendance_pdf_individual). Mismo gate ADMINISTRADOR +
    COORDINADOR y mismo gate de completitud de curso que
    export_course_attendance_pdf (A2) -- `user_id` se resuelve contra el
    roster de ESE curso especifico via _build_course_attendance_summary, no
    un lookup global de User."""

    def setUp(self):
        self.administrador = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.instructor = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.client = Client()

    def _complete_course(self):
        course, _module = _make_course(
            self.administrador,
            project_name="Proyecto Poda y Tala Individual",
            activity_type=Course.ActivityType.CAPACITACION,
            objectives="Capacitar en procedimiento seguro",
            instructor=self.instructor,
        )
        return course

    def test_happy_path_user_inscrito_devuelve_pdf_con_1_fila_de_firmante(self):
        course = self._complete_course()
        signed_user = _make_user(job_position="Operario Uno")
        other_enrolled = _make_user(job_position="Operario Dos")
        enrollment = Enrollment.objects.create(user=signed_user, course=course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()
        Enrollment.objects.create(user=other_enrolled, course=course)

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse(
                "courses:export_course_attendance_pdf_individual",
                args=[course.id, signed_user.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

        # HTML fuente (pre-render final): reconstruye el MISMO contexto que
        # arma la vista (misma llamada a _build_course_attendance_summary +
        # el mismo filtro por user.id) y lo renderiza con
        # get_template(...).render(context), igual que A2 -- confirma
        # EXACTAMENTE 1 fila de firmante, no las 2 del roster completo.
        summary = _build_course_attendance_summary(course)
        row = next(r for r in summary["rows"] if r["user"].id == signed_user.id)
        html = get_template("courses/course_attendance_pdf.html").render(
            _course_pdf_context(course, rows=[row], is_individual=True)
        )
        tbody_html = html[html.index("<tbody>") : html.index("</tbody>")]
        self.assertEqual(tbody_html.count("<tr>"), 1)
        self.assertIn(signed_user.get_full_name(), tbody_html)
        self.assertNotIn(other_enrolled.get_full_name(), tbody_html)
        self.assertIn("Reporte Individual de Asistencia", html)

    def test_edge_user_no_inscrito_en_este_curso_da_404(self):
        """Un user_id valido que existe como User pero esta inscrito en
        OTRO curso (no en `course`) debe dar 404 -- NUNCA un lookup global
        de User que ignore el curso, ni un PDF vacio con 200."""
        course = self._complete_course()
        other_course = self._complete_course()
        outsider = _make_user()
        Enrollment.objects.create(user=outsider, course=other_course)

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse(
                "courses:export_course_attendance_pdf_individual",
                args=[course.id, outsider.id],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_edge_user_id_inexistente_da_404(self):
        course = self._complete_course()
        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse(
                "courses:export_course_attendance_pdf_individual",
                args=[course.id, 9_999_999],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_edge_ejecutor_es_bloqueado(self):
        course = self._complete_course()
        signed_user = _make_user()
        Enrollment.objects.create(user=signed_user, course=course)

        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse(
                "courses:export_course_attendance_pdf_individual",
                args=[course.id, signed_user.id],
            )
        )
        self.assertEqual(response.status_code, 302)

    def test_happy_path_coordinador_tambien_exporta_individual(self):
        course = self._complete_course()
        signed_user = _make_user()
        Enrollment.objects.create(user=signed_user, course=course)

        self.client.force_login(self.coordinador)
        response = self.client.get(
            reverse(
                "courses:export_course_attendance_pdf_individual",
                args=[course.id, signed_user.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_regresion_grupal_sigue_devolviendo_todas_las_filas(self):
        """El endpoint Grupal (export_course_attendance_pdf, A2) sigue
        devolviendo TODAS las filas del roster -- confirma que A4 no filtro
        el Grupal por accidente."""
        course = self._complete_course()
        user_a = _make_user(job_position="Operario A")
        user_b = _make_user(job_position="Operario B")
        Enrollment.objects.create(user=user_a, course=course)
        Enrollment.objects.create(user=user_b, course=course)

        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("courses:export_course_attendance_pdf", args=[course.id])
        )
        self.assertEqual(response.status_code, 200)
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

        summary = _build_course_attendance_summary(course)
        self.assertEqual(len(summary["rows"]), 2)
        html = get_template("courses/course_attendance_pdf.html").render(
            _course_pdf_context(course, rows=summary["rows"])
        )
        tbody_html = html[html.index("<tbody>") : html.index("</tbody>")]
        self.assertEqual(tbody_html.count("<tr>"), 2)
        self.assertIn(user_a.get_full_name(), tbody_html)
        self.assertIn(user_b.get_full_name(), tbody_html)


# =============================================================================
# A3 -- Legado (attendance_pdf.html): logo + acento #e4020f + columna
# "Fecha de firma". Mismo tratamiento que A2 (course_attendance_pdf.html)
# pero sobre el template legacy per-lección y `export_attendance_pdf` --
# evita repetir el patron exacto de bounce 1 (arreglar solo el flujo nuevo
# y dejar el legado desactualizado). Wiring real cubierto por
# `LegacyPdfRealRenderTests` (arriba, pre-existente) contra la vista real;
# esta clase cubre el HTML-fuente vía `_legacy_pdf_context()`.
# =============================================================================


class LegacyAttendancePdfBrandingTests(TestCase):
    """attendance_pdf.html -- logo + acento de marca + columna de fecha de
    firma, mismos requisitos que A2 aplicados al flujo legacy."""

    def setUp(self):
        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course, self.module = _make_course(
            self.creator, activity_type=Course.ActivityType.CHARLA
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Sesión Asistencia legacy branding",
            lesson_type=Lesson.Type.ATTENDANCE,
            order=0,
        )
        self.signed_at = timezone.now()
        self.row = {
            "user": self.creator,
            "full_name": self.creator.get_full_name(),
            "document_number": self.creator.document_number,
            "presente": True,
            "estado": "Presente",
            "signed_at": self.signed_at,
            "signature_image_url": "",
        }

    def test_happy_path_logo_embebido(self):
        context = _attendance_pdf_branding_context()
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(
                self.course,
                lesson=self.lesson,
                rows=[self.row],
                logo_data_uri=context["logo_data_uri"],
            ),
        )
        self.assertIn("data:image/png;base64,", html)

    def test_regresion_sin_rojo_corporativo_bounce_2026_07_28(self):
        """Mismo criterio que el PDF por curso: FT-HSEQ-60 en blanco y negro.
        Se aplica tambien al legado para no repetir el patron de bounce 1
        (arreglar una superficie y dejar la otra desactualizada)."""
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        self.assertNotIn("#e4020f", html)
        self.assertIn("#1a1a1a", html)

    def test_regresion_logo_con_tamano_explicito_no_max_height(self):
        """Ver equivalente en CourseAttendancePdfBrandingTests: max-* es
        ignorado por xhtml2pdf y el logo se dibujaba a tamano natural."""
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        logo_css = html.split(".header .brand-logo {")[1].split("}")[0]
        self.assertIn("width: 90pt", logo_css)
        self.assertIn("height: 60pt", logo_css)
        self.assertNotIn("max-height", logo_css)
        self.assertNotIn("max-width", logo_css)

    def test_happy_path_columna_fecha_de_firma_con_valor_real(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        self.assertIn("Fecha de firma", html)
        # localtime -- el filtro `date` de Django convierte a TIME_ZONE local
        # antes de formatear, comparar en UTC crudo desfasa el assert.
        self.assertIn(timezone.localtime(self.signed_at).strftime("%H:%M"), html)

    def test_edge_fecha_de_firma_ausente_renderiza_placeholder_sin_error(self):
        row_sin_firma = dict(self.row, signed_at=None)
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[row_sin_firma]),
        )
        self.assertIn("Fecha de firma", html)
        self.assertIn("—", html)

    def test_edge_logo_ausente_html_valido_sin_img(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(
                self.course, lesson=self.lesson, rows=[self.row], logo_data_uri=""
            ),
        )
        self.assertNotIn("<img class=\"brand-logo\"", html)
        # el resto del documento sigue renderizando sin error
        self.assertIn("Lista de Asistencia", html)

    def test_regresion_sin_azul_bounce_2(self):
        html = render_to_string(
            "courses/attendance_pdf.html",
            _legacy_pdf_context(self.course, lesson=self.lesson, rows=[self.row]),
        )
        self.assertNotIn("#2563eb", html)

    def test_happy_path_render_real_via_vista_contiene_columna_de_fecha(self):
        """A diferencia de los tests de arriba (render_to_string directo
        contra el template), este pega la vista real `export_attendance_pdf`
        -- confirma que el wiring `context.update(_attendance_pdf_branding_context())`
        efectivamente llega al PDF servido, no solo al template en aislado
        (#328 -- caso NOVAPCR: template bien, vista real sin el wiring)."""
        signer = _make_user(job_position="Operario Render")
        Enrollment.objects.create(user=signer, course=self.course)
        sig = AttendanceSignature.objects.create(lesson=self.lesson, user=signer)
        sig.signature_image.save("sig.png", _png_file(), save=True)
        client = Client()
        client.force_login(self.creator)

        response = client.get(
            reverse("courses:export_attendance_pdf", args=[self.course.id, self.lesson.id])
        )
        self.assertEqual(response.status_code, 200)
        content = response.getvalue() if hasattr(response, "getvalue") else response.content
        self.assertTrue(content.startswith(b"%PDF"))

        text = _extract_pdf_text(self, content)
        # "Fecha de firma" es el encabezado nuevo -- columna ancha, sale sin
        # wrap. El cargo del firmante ("Operario Render") sí puede envolver
        # en 2 líneas por el ancho reducido de esa columna -- se checkea por
        # palabras sueltas para no depender del layout exacto de pdftotext.
        self.assertIn("Fecha de firma", text)
        self.assertIn("Operario", text)
        self.assertIn("Render", text)
