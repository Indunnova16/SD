"""Tests for filtrado de datos por rol en Aprendizaje — assessments (SD#58, A6).

`assessment_list` filtra por rol (issue #58, PLAN.md sub-item A6): Ejecutor (o
`rol` sin asignar) ve solo evaluaciones cuyo curso asociado — directo
(`Assessment.course`) o heredado (`Assessment.lesson.module.course`) — esté
dirigido a su `job_profile` vía `target_profiles`, más las evaluaciones
"genéricas" (sin curso asociado, o cuyo curso no tiene `target_profiles`
asignado). Coordinador/Administrador ven todas las evaluaciones.
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.courses.models import Course, JobProfileType, Lesson, Module

_SEQ_ITER = iter(range(9_000_000, 9_999_999))


def _make_user(rol=None, job_profile=None, **overrides):
    n = next(_SEQ_ITER)
    defaults = {
        "email": f"a6_assess_user_{n}@test.com",
        "password": "testpass123",
        "first_name": "A6",
        "last_name": "Assessments",
        "document_type": "CC",
        "document_number": str(n),
        "job_position": "Tech",
        "job_profile": job_profile,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class AssessmentListRolFilterTests(TestCase):
    """Filtrado de `assessment_list` por rol de acceso."""

    def setUp(self):
        self.client = Client()

        self.liniero_profile, _ = JobProfileType.objects.get_or_create(
            code="LINIERO", defaults={"name": "Liniero"}
        )
        self.tecnico_profile, _ = JobProfileType.objects.get_or_create(
            code="TECNICO", defaults={"name": "Técnico"}
        )

        self.creator = _make_user(rol=User.Rol.ADMINISTRADOR)

        # Curso directo (Assessment.course) dirigido a LINIERO.
        self.course_liniero = Course.objects.create(
            code="A6-ASSESS-LINIERO",
            title="Curso Assess Liniero",
            created_by=self.creator,
            target_profiles=["LINIERO"],
        )
        self.assessment_directo_liniero = Assessment.objects.create(
            title="Evaluación directa Liniero",
            course=self.course_liniero,
            created_by=self.creator,
            status=Assessment.Status.PUBLISHED,
        )

        # Curso heredado vía lesson.module.course, dirigido a TECNICO.
        self.course_tecnico = Course.objects.create(
            code="A6-ASSESS-TECNICO",
            title="Curso Assess Tecnico",
            created_by=self.creator,
            target_profiles=["TECNICO"],
        )
        module = Module.objects.create(course=self.course_tecnico, title="Modulo 1")
        lesson = Lesson.objects.create(
            module=module, title="Leccion 1", lesson_type=Lesson.Type.QUIZ
        )
        self.assessment_heredado_tecnico = Assessment.objects.create(
            title="Evaluación heredada Tecnico",
            lesson=lesson,
            created_by=self.creator,
            status=Assessment.Status.PUBLISHED,
        )

        # Evaluación standalone (sin course ni lesson) — genérica, visible a todos.
        self.assessment_standalone = Assessment.objects.create(
            title="Evaluación standalone",
            created_by=self.creator,
            status=Assessment.Status.PUBLISHED,
        )

        # Evaluación de un curso sin target_profiles (genérico) — visible a todos.
        self.course_generico = Course.objects.create(
            code="A6-ASSESS-GENERICO",
            title="Curso Assess Generico",
            created_by=self.creator,
            target_profiles=[],
        )
        self.assessment_curso_generico = Assessment.objects.create(
            title="Evaluación curso genérico",
            course=self.course_generico,
            created_by=self.creator,
            status=Assessment.Status.PUBLISHED,
        )

        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR, job_profile=self.liniero_profile)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR, job_profile=self.liniero_profile)
        self.administrador = _make_user(
            rol=User.Rol.ADMINISTRADOR, job_profile=self.tecnico_profile
        )
        self.sin_rol = _make_user(rol=None, job_profile=self.liniero_profile)

    def _titles(self, response):
        return {a.title for a in response.context["assessments"]}

    def test_ejecutor_ve_subconjunto_por_perfil(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("assessments:list"))

        titles = self._titles(response)
        self.assertIn(self.assessment_directo_liniero.title, titles)
        self.assertIn(self.assessment_standalone.title, titles)
        self.assertIn(self.assessment_curso_generico.title, titles)
        self.assertNotIn(self.assessment_heredado_tecnico.title, titles)

    def test_coordinador_ve_superset_incluye_otros_perfiles(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("assessments:list"))

        titles = self._titles(response)
        self.assertIn(self.assessment_directo_liniero.title, titles)
        self.assertIn(self.assessment_heredado_tecnico.title, titles)
        self.assertIn(self.assessment_standalone.title, titles)
        self.assertIn(self.assessment_curso_generico.title, titles)

    def test_administrador_ve_todo(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("assessments:list"))

        titles = self._titles(response)
        self.assertIn(self.assessment_directo_liniero.title, titles)
        self.assertIn(self.assessment_heredado_tecnico.title, titles)
        self.assertIn(self.assessment_standalone.title, titles)
        self.assertIn(self.assessment_curso_generico.title, titles)

    def test_rol_sin_asignar_se_trata_como_ejecutor_restrictivo(self):
        """Edge case: `rol=None` no otorga acceso amplio."""
        self.client.force_login(self.sin_rol)
        response = self.client.get(reverse("assessments:list"))

        titles = self._titles(response)
        self.assertIn(self.assessment_directo_liniero.title, titles)
        self.assertIn(self.assessment_standalone.title, titles)
        self.assertNotIn(self.assessment_heredado_tecnico.title, titles)

    def test_ejecutor_sin_job_profile_solo_ve_evaluaciones_genericas(self):
        """Edge case: sin `job_profile` asignado, solo ve evaluaciones sin
        curso targeteado (standalone o curso genérico)."""
        sin_perfil = _make_user(rol=User.Rol.EJECUTOR, job_profile=None)
        self.client.force_login(sin_perfil)
        response = self.client.get(reverse("assessments:list"))

        titles = self._titles(response)
        self.assertIn(self.assessment_standalone.title, titles)
        self.assertIn(self.assessment_curso_generico.title, titles)
        self.assertNotIn(self.assessment_directo_liniero.title, titles)
        self.assertNotIn(self.assessment_heredado_tecnico.title, titles)
