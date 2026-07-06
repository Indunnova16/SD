"""
Tests for issue #58 sub-item A9 — filtrado de datos de Gamificación por rol
de acceso (RBAC, ver `apps/accounts/permissions.py` A4 y `User.rol`/
`User.supervisor` A1):

  - Ejecutor: solo su dashboard personal (`dashboard`/`stats`/`overview`,
    sin cambio de comportamiento — A9 no los toca), bloqueado de las vistas
    `equipo/*` y `admin/*`.
  - Coordinador: vista NUEVA `equipo/` (`team_dashboard`/`team_analytics`/
    `team_top_earners`) — ranking/puntos SOLO de los usuarios que reportan
    a él vía `User.supervisor` FK (`related_name='equipo'`, A1). NO ve el
    equipo de otro Coordinador ni el resto del sistema.
  - Administrador: `admin/*` (ya migrado por A4 a `require_rol`) ve el
    sistema completo; además puede usar `equipo/*` para ver a quien
    supervisa directamente (alcance distinto de "todo").

Sigue el mismo patrón de diseño que A7 (certifications): scope resuelto por
`user.rol` + FK `supervisor`. A diferencia de A7 (que usa un query param
`?scope=` sobre una única URL), acá "equipo" y "todo" ya vivían en URLs
separadas (`admin/*`) desde antes de A9, así que la degradación de acceso
se hace vía `require_rol` sobre la URL nueva `equipo/*`, no un query param.
"""

import itertools
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.gamification.services.dashboard import GamificationDashboardService
from apps.gamification.tests.factories import (
    PointCategoryFactory,
    PointTransactionFactory,
)

_SEQ = itertools.count(1)


def _make_user(*, rol=None, supervisor=None, is_staff=False, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a9_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A9",
        "document_type": "CC",
        "document_number": f"72{n:07d}",
        "job_position": "Técnico",
        "job_profile": None,
        "hire_date": date(2022, 1, 1),
        "is_staff": is_staff,
        "rol": rol,
        "supervisor": supervisor,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class _A9BaseTestCase(TestCase):
    """Fixture compartida: 2 equipos (Coordinador->2 Ejecutores, uno
    "legacy" con `rol=None`) + 1 Administrador + 1 Ejecutor de otro equipo,
    cada uno con puntos otorgados esta semana."""

    @classmethod
    def setUpTestData(cls):
        cls.administrador = _make_user(
            rol=User.Rol.ADMINISTRADOR, is_staff=True, first_name="Admin"
        )
        cls.coordinador1 = _make_user(rol=User.Rol.COORDINADOR, first_name="CoordUno")
        cls.coordinador2 = _make_user(rol=User.Rol.COORDINADOR, first_name="CoordDos")
        cls.ejecutor1 = _make_user(
            rol=User.Rol.EJECUTOR, supervisor=cls.coordinador1, first_name="EjecUno"
        )
        # "Legacy": reporta a coordinador1 (un Administrador ya le asignó
        # `supervisor` tras A1/A2) pero el backfill de A1 NUNCA le asignó
        # `rol` explícito (bucket "sin sugerencia confiable" del PLAN) —
        # dato real pre-existente al feature, mismo patrón que A7.
        cls.ejecutor_legacy = _make_user(
            rol=None, supervisor=cls.coordinador1, is_staff=True, first_name="Legacy"
        )
        cls.ejecutor3 = _make_user(
            rol=User.Rol.EJECUTOR, supervisor=cls.coordinador2, first_name="EjecTres"
        )

        cls.category = PointCategoryFactory()

        # `PointTransaction.created_at` es `auto_now_add` (siempre "ahora"),
        # así que estas transacciones caen dentro de "esta semana" sin
        # necesidad de forzar la fecha — mismo patrón que
        # `test_get_admin_analytics` (test_services.py) ya usa.
        cls.tx_e1 = PointTransactionFactory(user=cls.ejecutor1, category=cls.category, points=100)
        cls.tx_legacy = PointTransactionFactory(
            user=cls.ejecutor_legacy, category=cls.category, points=50
        )
        cls.tx_e3 = PointTransactionFactory(user=cls.ejecutor3, category=cls.category, points=200)
        cls.tx_coord1 = PointTransactionFactory(
            user=cls.coordinador1, category=cls.category, points=30
        )


class GetTeamAnalyticsServiceTests(_A9BaseTestCase):
    """`GamificationDashboardService.get_team_analytics` — unit tests del
    aggregate scoping (sin pasar por HTTP)."""

    def test_team_analytics_incluye_solo_al_equipo_del_supervisor(self):
        data = GamificationDashboardService.get_team_analytics(self.coordinador1)

        self.assertEqual(data["points"]["total"], 150)  # 100 (e1) + 50 (legacy)
        self.assertEqual(data["users"]["active_this_week"], 2)
        emails = {e["user__email"] for e in data["users"]["top_earners"]}
        self.assertEqual(emails, {self.ejecutor1.email, self.ejecutor_legacy.email})

    def test_team_analytics_no_filtra_por_rol_del_integrante_dato_legacy(self):
        """El usuario legacy (`rol=None`) SÍ cuenta en el equipo de su
        supervisor — el scope de equipo filtra por `User.supervisor`, nunca
        por el `rol` del integrante (issue #58, decisión #2: `rol` es la
        fuente de verdad de PERMISOS, no de pertenencia a equipo)."""
        data = GamificationDashboardService.get_team_analytics(self.coordinador1)
        emails = {e["user__email"] for e in data["users"]["top_earners"]}
        self.assertIn(self.ejecutor_legacy.email, emails)

    def test_team_analytics_no_incluye_a_otro_equipo(self):
        """Edge case: aislamiento entre equipos — coordinador1 no ve nada
        del equipo de coordinador2."""
        data = GamificationDashboardService.get_team_analytics(self.coordinador1)
        emails = {e["user__email"] for e in data["users"]["top_earners"]}
        self.assertNotIn(self.ejecutor3.email, emails)

    def test_team_analytics_no_incluye_al_propio_coordinador(self):
        """Los puntos del propio Coordinador no cuentan como "equipo" —
        mismo criterio que A7 (certificado propio no es "equipo")."""
        data = GamificationDashboardService.get_team_analytics(self.coordinador1)
        emails = {e["user__email"] for e in data["users"]["top_earners"]}
        self.assertNotIn(self.coordinador1.email, emails)

    def test_team_analytics_equipo_vacio_no_rompe(self):
        """Edge case: un supervisor sin nadie a cargo (el Administrador acá
        no supervisa a nadie) obtiene ceros/listas vacías, no una excepción."""
        data = GamificationDashboardService.get_team_analytics(self.administrador)

        self.assertEqual(data["points"]["total"], 0)
        self.assertEqual(data["users"]["active_this_week"], 0)
        self.assertEqual(data["users"]["top_earners"], [])

    def test_admin_analytics_sigue_siendo_global_tras_el_refactor(self):
        """Regresión: `get_admin_analytics()` (sin argumentos) sigue
        agregando TODO el sistema tras refactorizar `_compute_analytics`
        para aceptar `supervisor` — no debe quedar filtrando por nadie."""
        data = GamificationDashboardService.get_admin_analytics()

        self.assertEqual(data["points"]["total"], 380)  # 100+50+200+30
        self.assertEqual(data["users"]["active_this_week"], 4)


class TeamDashboardViewAuthzTests(_A9BaseTestCase):
    """`gamification:team-dashboard`/`team-analytics`/`team-top-earners` —
    autorización (Coordinador/Administrador sí, Ejecutor no) y aislamiento
    de datos servidos por HTTP."""

    def test_login_requerido_en_team_dashboard(self):
        response = self.client.get(reverse("gamification:team-dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_ejecutor_bloqueado_de_team_dashboard(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(reverse("gamification:team-dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("gamification:dashboard"), response.url)

    def test_ejecutor_bloqueado_de_team_analytics(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(reverse("gamification:team-analytics"))
        self.assertEqual(response.status_code, 302)

    def test_ejecutor_bloqueado_de_team_top_earners(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(reverse("gamification:team-top-earners"))
        self.assertEqual(response.status_code, 302)

    def test_coordinador_accede_a_team_dashboard(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(reverse("gamification:team-dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_coordinador_ve_puntos_de_su_equipo_en_team_analytics(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(reverse("gamification:team-analytics"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Puntos totales del equipo (100 e1 + 50 legacy = 150), NO los 380
        # del sistema completo.
        self.assertIn("150", content)

    def test_coordinador_ve_su_equipo_en_team_top_earners_sin_fuga(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(reverse("gamification:team-top-earners"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.ejecutor1.first_name, content)
        self.assertIn(self.ejecutor_legacy.first_name, content)
        self.assertNotIn(self.ejecutor3.first_name, content)  # equipo de coordinador2

    def test_administrador_accede_a_team_views(self):
        """Administrador puede usar `equipo/*` para ver a quien supervisa
        directamente (equipo vacío en este fixture, alcance distinto de
        `admin/*` que sí ve TODO el sistema)."""
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("gamification:team-dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_ejecutor_bloqueado_de_admin_dashboard(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(reverse("gamification:admin-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_coordinador_bloqueado_de_admin_dashboard(self):
        """Regresión — no ampliar por error el acceso a `admin/*` (alcance
        TODO el sistema) a Coordinador; sigue siendo solo Administrador (A4)."""
        self.client.force_login(self.coordinador1)
        response = self.client.get(reverse("gamification:admin-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_administrador_ve_admin_analytics_completo(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("gamification:admin-analytics"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("380", content)  # total del sistema, no de un equipo
