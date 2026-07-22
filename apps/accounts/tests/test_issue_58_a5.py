"""Tests for el navbar RBAC-gated (SD#58, A5).

Cubre:
  - Render real del navbar (desktop + mobile, ambos viven en el mismo
    partial `templates/partials/navbar.html`) contra 3 fixtures de rol
    EJECUTOR/COORDINADOR/ADMINISTRADOR: los ítems admin-only (Gestión de
    Usuarios, Parametrización, Reportes y Analytics, Manual de
    Administrador) solo aparecen para ADMINISTRADOR — SIN ampliación a
    COORDINADOR todavía (A5 es un swap 1:1 de `is_staff` a
    `rol == 'ADMINISTRADOR'`, igual que hizo A4 en las vistas; ampliar a
    COORDINADOR es scope de A6-A10).
    (Asistencia facial (QR)/Eventos de asistencia se probaban acá también;
    se quitaron en issue #64 junto con el borrado completo de
    `apps.attendance`, reemplazado por `apps.courses.AttendanceSignature`
    #63.)
  - "Notificaciones" presente para los 3 roles (decisión Miguel #4 del
    PLAN — bandeja personal, nunca se gatea por rol).
  - Regresión central: un usuario legacy `is_staff=True` con `rol=None`
    (estado real de cualquier fila entre el deploy de A1 y que corra el
    backfill 0016, o cualquier fixture de test vieja no actualizada) YA NO
    ve las secciones admin del navbar — `is_staff` dejó de ser fuente de
    verdad también acá, no solo en las vistas migradas por A4.
  - Excepción documentada (PLAN.md sección "Riesgos y mitigaciones"): el
    link nativo "Administración" (`admin:index`, el propio admin de
    Django) sigue gateado por `user.is_staff`, a propósito NO se migra a
    `rol` — el admin site de Django exige `is_staff=True` para su propio
    login, así que mostrar ese link a un ADMINISTRADOR-por-rol sin
    `is_staff` sería un link muerto. Se prueba ambos lados de esa excepción.
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, is_staff=False, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a5_navbar_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A5",
        "document_type": "CC",
        "document_number": f"71{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class NavbarRolGatingTests(TestCase):
    """Render vía `Client` real (no `RequestFactory`) — el navbar se renderiza
    como parte de `base/base.html`, incluido por `accounts:profile` (vista
    simple, sin dependencias de datos de otras apps)."""

    def setUp(self):
        self.client = Client()

    def _render_navbar(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    # --- Administrador: ve TODO lo admin-only ---

    def test_administrador_ve_gestion_usuarios_y_parametrizacion(self):
        admin = _make_user(rol=Rol.ADMINISTRADOR)
        html = self._render_navbar(admin)
        self.assertIn("Gestión de Usuarios", html)
        self.assertIn("Parametrización", html)

    def test_administrador_ve_reportes_y_analytics_desktop_y_mobile(self):
        admin = _make_user(rol=Rol.ADMINISTRADOR)
        html = self._render_navbar(admin)
        self.assertIn("Reportes y Analytics", html)  # texto desktop
        self.assertIn("📊 Reportes</a>", html)  # texto mobile (sin "y Analytics")

    def test_administrador_ve_manual_administrador_no_trabajador(self):
        admin = _make_user(rol=Rol.ADMINISTRADOR)
        html = self._render_navbar(admin)
        self.assertIn("Manual de Administrador", html)
        self.assertNotIn("Manual del Trabajador", html)

    def test_administrador_ve_notificaciones(self):
        admin = _make_user(rol=Rol.ADMINISTRADOR)
        html = self._render_navbar(admin)
        self.assertIn("Notificaciones", html)

    # --- Ejecutor: NO ve nada admin-only, SÍ ve Notificaciones ---

    def test_ejecutor_no_ve_gestion_usuarios_ni_parametrizacion(self):
        ejecutor = _make_user(rol=Rol.EJECUTOR)
        html = self._render_navbar(ejecutor)
        self.assertNotIn("Gestión de Usuarios", html)
        self.assertNotIn("Parametrización", html)

    def test_ejecutor_no_ve_reportes_y_analytics(self):
        ejecutor = _make_user(rol=Rol.EJECUTOR)
        html = self._render_navbar(ejecutor)
        self.assertNotIn("Reportes y Analytics", html)
        self.assertNotIn("📊 Reportes</a>", html)

    def test_ejecutor_ve_manual_trabajador_no_administrador(self):
        ejecutor = _make_user(rol=Rol.EJECUTOR)
        html = self._render_navbar(ejecutor)
        self.assertIn("Manual del Trabajador", html)
        self.assertNotIn("Manual de Administrador", html)

    def test_ejecutor_ve_notificaciones(self):
        ejecutor = _make_user(rol=Rol.EJECUTOR)
        html = self._render_navbar(ejecutor)
        self.assertIn("Notificaciones", html)

    # --- Coordinador: swap 1:1 SIN ampliación todavía (scope de A6-A10) ---

    def test_coordinador_no_ve_secciones_admin_sin_ampliacion_todavia(self):
        coordinador = _make_user(rol=Rol.COORDINADOR)
        html = self._render_navbar(coordinador)
        self.assertNotIn("Gestión de Usuarios", html)
        self.assertNotIn("Parametrización", html)
        self.assertNotIn("Reportes y Analytics", html)
        self.assertNotIn("Manual de Administrador", html)
        self.assertNotIn("Asistencia facial (QR)", html)
        self.assertNotIn("Eventos de asistencia", html)

    def test_coordinador_ve_notificaciones(self):
        coordinador = _make_user(rol=Rol.COORDINADOR)
        html = self._render_navbar(coordinador)
        self.assertIn("Notificaciones", html)

    # --- Regresión central: legacy is_staff=True + rol=None ya NO alcanza ---

    def test_legacy_is_staff_sin_rol_ya_no_ve_secciones_admin_del_navbar(self):
        """Estado real de cualquier fila entre el deploy de A1 (schema) y que
        corra el backfill 0016 (data): `is_staff=True` histórico, `rol` aún
        sin poblar. El navbar (igual que las vistas migradas por A4) debe
        tratarlo como sin permisos elevados — `rol` es la única fuente de
        verdad de acá en adelante (decisión de Miguel #2)."""
        legacy = _make_user(rol=None, is_staff=True, is_superuser=True)
        html = self._render_navbar(legacy)
        self.assertNotIn("Gestión de Usuarios", html)
        self.assertNotIn("Parametrización", html)
        self.assertNotIn("Reportes y Analytics", html)
        self.assertNotIn("Manual de Administrador", html)
        self.assertNotIn("Asistencia facial (QR)", html)
        self.assertNotIn("Eventos de asistencia", html)
        self.assertIn("Manual del Trabajador", html)
        self.assertIn("Notificaciones", html)

    # --- Excepción documentada: "Administración" (admin:index) sigue is_staff ---

    def test_link_administracion_no_aparece_para_rol_administrador_sin_is_staff(self):
        """El link nativo a `/admin/` sigue gateado por `is_staff` a
        propósito (PLAN.md, sección Riesgos): el admin de Django exige
        `is_staff=True` para su propio login, así que un ADMINISTRADOR por
        `rol` sin `is_staff` vería un link muerto si se migrara. El resto de
        secciones admin del navbar SÍ deben aparecerle (gating por `rol`)."""
        rol_admin_sin_staff = _make_user(rol=Rol.ADMINISTRADOR, is_staff=False)
        html = self._render_navbar(rol_admin_sin_staff)
        self.assertIn("Gestión de Usuarios", html)
        self.assertNotIn(">Administración<", html)

    def test_link_administracion_aparece_con_is_staff_y_rol_administrador(self):
        admin_real = _make_user(rol=Rol.ADMINISTRADOR, is_staff=True)
        html = self._render_navbar(admin_real)
        self.assertIn(">Administración<", html)

    def test_link_administracion_no_aparece_para_ejecutor(self):
        ejecutor = _make_user(rol=Rol.EJECUTOR, is_staff=False)
        html = self._render_navbar(ejecutor)
        self.assertNotIn(">Administración<", html)
