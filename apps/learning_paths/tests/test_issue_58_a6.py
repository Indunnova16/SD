"""Tests for filtrado de datos por rol en Aprendizaje — learning_paths (SD#58, A6).

`learning_path_list` filtra por rol (issue #58, PLAN.md sub-item A6): Ejecutor
(o `rol` sin asignar) ve solo el subconjunto de rutas dirigidas a su
`job_profile` vía `target_profiles`, más las rutas "genéricas"
(`target_profiles=[]`). Coordinador/Administrador ven todas las rutas.

También cubre la migración de `learning_path_create` (antes gateado con
`request.user.is_staff` crudo — un check que había quedado fuera del alcance
de A4, ya que `learning_paths` no estaba en su lista de 8 archivos — ahora
migrado a `require_rol(Rol.ADMINISTRADOR)`, consistente con la decisión de
Miguel #2 del PLAN: `rol` es la única fuente de verdad).
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import JobProfileType
from apps.learning_paths.models import LearningPath

_SEQ_ITER = iter(range(9_000_000, 9_999_999))


def _make_user(rol=None, job_profile=None, is_staff=False, **overrides):
    n = next(_SEQ_ITER)
    defaults = {
        "email": f"a6_lp_user_{n}@test.com",
        "password": "testpass123",
        "first_name": "A6",
        "last_name": "LearningPaths",
        "document_type": "CC",
        "document_number": str(n),
        "job_position": "Tech",
        "job_profile": job_profile,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class LearningPathListRolFilterTests(TestCase):
    """Filtrado de `learning_path_list` por rol de acceso."""

    def setUp(self):
        self.client = Client()

        self.liniero_profile, _ = JobProfileType.objects.get_or_create(
            code="LINIERO", defaults={"name": "Liniero"}
        )
        self.tecnico_profile, _ = JobProfileType.objects.get_or_create(
            code="TECNICO", defaults={"name": "Técnico"}
        )

        self.admin_creator = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)

        self.path_liniero = LearningPath.objects.create(
            name="Ruta Linieros A6",
            description="Ruta para linieros",
            estimated_duration=30,
            created_by=self.admin_creator,
            status=LearningPath.Status.ACTIVE,
            target_profiles=["LINIERO"],
        )
        self.path_tecnico = LearningPath.objects.create(
            name="Ruta Tecnicos A6",
            description="Ruta para tecnicos",
            estimated_duration=30,
            created_by=self.admin_creator,
            status=LearningPath.Status.ACTIVE,
            target_profiles=["TECNICO"],
        )
        self.path_generica = LearningPath.objects.create(
            name="Ruta Generica A6",
            description="Ruta sin perfil objetivo",
            estimated_duration=30,
            created_by=self.admin_creator,
            status=LearningPath.Status.ACTIVE,
            target_profiles=[],
        )

        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR, job_profile=self.liniero_profile)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR, job_profile=self.liniero_profile)
        self.administrador = _make_user(
            rol=User.Rol.ADMINISTRADOR, job_profile=self.tecnico_profile
        )
        self.sin_rol = _make_user(rol=None, job_profile=self.liniero_profile)

    def _names(self, response):
        return {item["path"].name for item in response.context["paths"]}

    def test_ejecutor_ve_subconjunto_por_perfil(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("learning_paths:list"))

        names = self._names(response)
        self.assertIn(self.path_liniero.name, names)
        self.assertIn(self.path_generica.name, names)
        self.assertNotIn(self.path_tecnico.name, names)

    def test_coordinador_ve_superset_incluye_otros_perfiles(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("learning_paths:list"))

        names = self._names(response)
        self.assertIn(self.path_liniero.name, names)
        self.assertIn(self.path_tecnico.name, names)
        self.assertIn(self.path_generica.name, names)

    def test_administrador_ve_todo(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("learning_paths:list"))

        names = self._names(response)
        self.assertIn(self.path_liniero.name, names)
        self.assertIn(self.path_tecnico.name, names)
        self.assertIn(self.path_generica.name, names)

    def test_rol_sin_asignar_se_trata_como_ejecutor_restrictivo(self):
        """Edge case: `rol=None` no otorga acceso amplio."""
        self.client.force_login(self.sin_rol)
        response = self.client.get(reverse("learning_paths:list"))

        names = self._names(response)
        self.assertIn(self.path_liniero.name, names)
        self.assertIn(self.path_generica.name, names)
        self.assertNotIn(self.path_tecnico.name, names)

    def test_ejecutor_sin_job_profile_solo_ve_rutas_genericas(self):
        """Edge case: sin `job_profile` asignado, no matchea ningún
        target_profiles específico."""
        sin_perfil = _make_user(rol=User.Rol.EJECUTOR, job_profile=None)
        self.client.force_login(sin_perfil)
        response = self.client.get(reverse("learning_paths:list"))

        names = self._names(response)
        self.assertIn(self.path_generica.name, names)
        self.assertNotIn(self.path_liniero.name, names)
        self.assertNotIn(self.path_tecnico.name, names)


class LearningPathCreateRolGateTests(TestCase):
    """Regresión: `learning_path_create` migrado de `is_staff` crudo a
    `require_rol(Rol.ADMINISTRADOR)` (gap fuera del alcance original de A4,
    cerrado en A6 al tocar el mismo archivo)."""

    def setUp(self):
        self.client = Client()

    def test_administrador_puede_acceder(self):
        admin = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.client.force_login(admin)
        response = self.client.get(reverse("learning_paths:create"))
        self.assertEqual(response.status_code, 200)

    def test_ejecutor_bloqueado(self):
        ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.client.force_login(ejecutor)
        response = self.client.get(reverse("learning_paths:create"), follow=True)
        self.assertRedirects(response, reverse("learning_paths:list"))

    def test_is_staff_solo_sin_rol_ya_no_alcanza(self):
        """Regresión central: un usuario legacy `is_staff=True` con
        `rol=None` (estado real entre el deploy de A1 y el backfill) ya NO
        pasa el gate — `rol` es la única fuente de verdad (decisión #2)."""
        legacy_staff = _make_user(rol=None, is_staff=True, is_superuser=True)
        self.client.force_login(legacy_staff)
        response = self.client.get(reverse("learning_paths:create"), follow=True)
        self.assertRedirects(response, reverse("learning_paths:list"))
