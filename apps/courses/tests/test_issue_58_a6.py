"""Tests for filtrado de datos por rol en Aprendizaje — courses (SD#58, A6).

`course_list` filtra por rol (issue #58, decisión de Miguel HITL 2026-07-06,
PLAN.md sub-item A6): Ejecutor (o `rol` sin asignar tras el backfill de A1)
ve solo el subconjunto de cursos dirigidos a su `job_profile` vía
`target_profiles`, más los cursos "genéricos" (`target_profiles=[]`, sin
perfil objetivo asignado — se tratan como visibles a todos, ver
`notas_para_orquestador` del output de A6 para la justificación de este
default). Coordinador/Administrador ven el catálogo completo sin filtrar.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.courses.models import Course
from apps.courses.tests.factories import JobProfileTypeFactory, PublishedCourseFactory, UserFactory


def _make_user(rol=None, job_profile=None, **overrides):
    return UserFactory(rol=rol, job_profile=job_profile, **overrides)


class CourseListRolFilterTests(TestCase):
    """Filtrado de `course_list` por rol de acceso."""

    def setUp(self):
        self.client = Client()

        self.liniero_profile = JobProfileTypeFactory(code="LINIERO", name="Liniero")
        self.tecnico_profile = JobProfileTypeFactory(code="TECNICO", name="Técnico")

        self.course_liniero = PublishedCourseFactory(
            code="A6-COURSE-LINIERO",
            title="Curso para Linieros",
            target_profiles=["LINIERO"],
        )
        self.course_tecnico = PublishedCourseFactory(
            code="A6-COURSE-TECNICO",
            title="Curso para Técnicos",
            target_profiles=["TECNICO"],
        )
        self.course_generico = PublishedCourseFactory(
            code="A6-COURSE-GENERICO",
            title="Curso Genérico (sin target_profiles)",
            target_profiles=[],
        )
        # Curso legacy pre-existente (dato "legacy" — creado antes de A6,
        # simula un registro real de BD sin tocarlo el fix): mismo patrón
        # target_profiles=["LINIERO"], distinto code para no colisionar.
        self.course_legacy_liniero = PublishedCourseFactory(
            code="A6-LEGACY-LINIERO",
            title="Curso Legado para Linieros",
            target_profiles=["LINIERO"],
        )

        self.ejecutor = _make_user(
            rol="EJECUTOR",
            job_profile=self.liniero_profile,
            email="a6_ejecutor@test.com",
            document_number="580000001",
        )
        self.coordinador = _make_user(
            rol="COORDINADOR",
            job_profile=self.liniero_profile,
            email="a6_coordinador@test.com",
            document_number="580000002",
        )
        self.administrador = _make_user(
            rol="ADMINISTRADOR",
            job_profile=self.tecnico_profile,
            email="a6_admin@test.com",
            document_number="580000003",
        )
        self.sin_rol = _make_user(
            rol=None,
            job_profile=self.liniero_profile,
            email="a6_sinrol@test.com",
            document_number="580000004",
        )
        self.sin_perfil = _make_user(
            rol="EJECUTOR",
            job_profile=None,
            email="a6_sinperfil@test.com",
            document_number="580000005",
        )

    def _titles(self, response):
        return {c.title for c in response.context["courses"]}

    def test_ejecutor_ve_subconjunto_por_perfil(self):
        """Happy path: Ejecutor LINIERO ve cursos LINIERO + genéricos, no TECNICO."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertIn(self.course_liniero.title, titles)
        self.assertIn(self.course_legacy_liniero.title, titles)
        self.assertIn(self.course_generico.title, titles)
        self.assertNotIn(self.course_tecnico.title, titles)

    def test_coordinador_ve_superset_incluye_otros_perfiles(self):
        """Coordinador (job_profile=LINIERO, igual que el Ejecutor) ve TAMBIÉN
        el curso de TECNICO — el catálogo no se filtra por rol Coordinador."""
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertIn(self.course_liniero.title, titles)
        self.assertIn(self.course_tecnico.title, titles)
        self.assertIn(self.course_generico.title, titles)
        self.assertIn(self.course_legacy_liniero.title, titles)

    def test_administrador_ve_todo(self):
        """Administrador ve el catálogo completo sin filtrar, aunque su
        job_profile (TECNICO) no coincida con la mayoría de los cursos."""
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertIn(self.course_liniero.title, titles)
        self.assertIn(self.course_tecnico.title, titles)
        self.assertIn(self.course_generico.title, titles)
        self.assertIn(self.course_legacy_liniero.title, titles)

    def test_rol_sin_asignar_se_trata_como_ejecutor_restrictivo(self):
        """Edge case: `rol=None` (bucket sin asignar del backfill A1) NO
        otorga acceso amplio — mismo filtrado restrictivo que Ejecutor,
        consistente con la regla de A4 (`rol is None` = sin permisos
        elevados)."""
        self.client.force_login(self.sin_rol)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertIn(self.course_liniero.title, titles)
        self.assertIn(self.course_generico.title, titles)
        self.assertNotIn(self.course_tecnico.title, titles)

    def test_ejecutor_sin_job_profile_solo_ve_cursos_genericos(self):
        """Edge case: Ejecutor sin `job_profile` asignado (dato legacy /
        usuario incompleto) no puede matchear ningún target_profiles
        específico — ve solo los cursos genéricos, no una lista vacía total
        ni el catálogo completo."""
        self.client.force_login(self.sin_perfil)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertIn(self.course_generico.title, titles)
        self.assertNotIn(self.course_liniero.title, titles)
        self.assertNotIn(self.course_tecnico.title, titles)

    def test_no_hay_cursos_no_publicados_filtrados_incorrectamente(self):
        """Regresión: el filtro de rol no reintroduce cursos DRAFT/ARCHIVED
        que ya estaban excluidos por `status=PUBLISHED` antes de A6."""
        draft = Course.objects.create(
            code="A6-DRAFT",
            title="Curso Borrador",
            created_by=self.administrador,
            status=Course.Status.DRAFT,
            target_profiles=["LINIERO"],
        )
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("courses:list"))

        titles = self._titles(response)
        self.assertNotIn(draft.title, titles)
