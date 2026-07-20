"""Tests para el reproceso de issue #58 reportado por el cliente el
2026-07-17 (2 bugs puntuales, RBAC A1-A11 ya deployado y fuera de scope acá):

1. `default_password` (templatetag, `apps/accounts/templatetags/account_tags.py`)
   recalculaba la fórmula de la contraseña generada con minúsculas + relleno
   'x', en vez de reusar `PasswordService.generate_password()` (mayúsculas +
   relleno 'X'). Era la 3ra recurrencia del mismo defecto — ya corregido en
   `UserCreateForm.save()` y `BulkUploadService` (commit 9be59a0, ver
   `test_issue_58.py`), pero seguía roto en el "ojito" del listado de
   usuarios (`user_list_table.html`), que renderiza este templatetag.

2. El dashboard personal (`templates/accounts/dashboard.html`, vista
   `accounts.views.dashboard`) embebía 9 `hx-get` a endpoints
   Administrador-only de `reports:*` SIN ningún chequeo de rol alrededor.
   Como esas 9 vistas SÍ tienen `@require_rol(ADMINISTRADOR,
   redirect_url="reports:list")` pero `require_rol` no detecta `HX-Request`
   (responde un redirect normal, no `HX-Redirect`), HTMX embebía la página
   completa de `reports:list` (incluido su navbar) DENTRO del widget pequeño
   del dashboard de cualquier rol no-Administrador — fuga visible reportada
   con 3 screenshots.

   Nota importante (corrección sobre el diagnóstico F1, verificada leyendo
   `apps/reports/tests/test_views.py`): NO se gateó `reports:list` en sí —
   es diseño intencional de A10 (ya deployado, ya testeado) que esa vista
   quede accesible a cualquier rol, porque solo lista PLANTILLAS de reporte
   (sin datos cross-usuario) y es el `redirect_url` "puerto seguro" de las
   10 vistas de dashboard + 3 `scheduled_*`. El fix real es que el dashboard
   personal deje de disparar esos 9 `hx-get` para roles no-Administrador —
   sin esa petición, nunca se llega a embeber ninguna página redirigida.

Este suite es exclusivo de este issue/fix (archivo nuevo, no se apendea a
`test_issue_58.py` ni a `test_issue_58_aN.py` para no pisar esos módulos
hermanos — convención de `f3_fix.md`).
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol
from apps.accounts.services import PasswordService

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"i58bug_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "I58Bug",
        "document_type": "CC",
        "document_number": f"80{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _render_default_password(user):
    """Renderiza el templatetag `default_password` tal como lo usa
    `user_list_table.html` ({% load account_tags %}{% default_password u %})."""
    tpl = Template(
        "{% load account_tags %}{% default_password u %}"
    )
    return tpl.render(Context({"u": user}))


class DefaultPasswordTemplatetagMatchesRealPasswordTests(TestCase):
    """Bug 1 — la contraseña MOSTRADA en el listado (templatetag) debe ser
    SIEMPRE idéntica a la contraseña REAL generada por
    `PasswordService.generate_password()` (la que efectivamente permite
    loguearse), en los 3 formatos de nombre que la fórmula contempla."""

    def test_nombre_de_3_o_mas_letras(self):
        """Caso del cliente: doc 12345678, nombre 'Miguel' -> antes se
        mostraba '12345678mig' (minúsculas) mientras la real era
        '12345678MIG' (mayúsculas) — nunca coincidían."""
        user = _make_user(
            document_number="12345678",
            first_name="Miguel",
            last_name="Rodriguez",
        )
        shown = _render_default_password(user)
        real = PasswordService.generate_password(user.document_number, user.first_name)
        self.assertEqual(shown, real)
        self.assertEqual(shown, "12345678MIG")

    def test_nombre_con_menos_de_3_letras_padding(self):
        """Nombre de 2 letras -> padding con 'X' (no 'x')."""
        user = _make_user(document_number="99887766", first_name="Al", last_name="Corto")
        shown = _render_default_password(user)
        real = PasswordService.generate_password(user.document_number, user.first_name)
        self.assertEqual(shown, real)
        self.assertEqual(shown, "99887766ALX")

    def test_sin_nombre_usa_usr_mayuscula(self):
        """Sin `first_name` -> fallback 'USR' (no 'usr')."""
        user = _make_user(document_number="55443322", first_name="", last_name="SinNombre")
        shown = _render_default_password(user)
        real = PasswordService.generate_password(user.document_number, user.first_name)
        self.assertEqual(shown, real)
        self.assertEqual(shown, "55443322USR")

    def test_password_mostrada_es_utilizable_para_login(self):
        """Regresión de fondo: la contraseña que muestra el templatetag debe
        ser la MISMA que quedó persistida (set_password) al crear el
        usuario — o sea, debe servir para loguearse de verdad."""
        raw_password = PasswordService.generate_password("11223344", "Andrea")
        user = _make_user(document_number="11223344", first_name="Andrea", last_name="Test")
        user.set_password(raw_password)
        user.save(update_fields=["password"])

        shown = _render_default_password(user)
        self.assertEqual(shown, raw_password)

        client = Client()
        login_ok = client.login(username=user.email, password=shown)
        self.assertTrue(login_ok, "la contraseña mostrada por el templatetag debe permitir login real")


class DashboardReportsWidgetsGatingTests(TestCase):
    """Bug 2 — el dashboard personal NO debe disparar/embeber ningún
    endpoint `reports:*` para roles no-Administrador."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.sin_rol = _make_user(rol=None)

    def test_administrador_si_ve_los_9_widgets_de_reportes(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("reports:dashboard-stats"), content)
        self.assertIn(reverse("reports:dashboard-compliance-chart"), content)
        self.assertIn(reverse("reports:dashboard-training-trend"), content)
        self.assertIn(reverse("reports:dashboard-course-progress"), content)
        self.assertIn(reverse("reports:dashboard-course-types"), content)
        self.assertIn(reverse("reports:dashboard-assessment-performance"), content)
        self.assertIn(reverse("reports:dashboard-expiring-certs"), content)
        self.assertIn(reverse("reports:dashboard-overdue-assignments"), content)
        self.assertIn(reverse("reports:dashboard-recent-activity"), content)

    def test_ejecutor_no_ve_ningun_widget_de_reportes(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for url_name in (
            "reports:dashboard-stats",
            "reports:dashboard-compliance-chart",
            "reports:dashboard-training-trend",
            "reports:dashboard-course-progress",
            "reports:dashboard-course-types",
            "reports:dashboard-assessment-performance",
            "reports:dashboard-expiring-certs",
            "reports:dashboard-overdue-assignments",
            "reports:dashboard-recent-activity",
        ):
            with self.subTest(url_name=url_name):
                self.assertNotIn(reverse(url_name), content)

    def test_coordinador_no_ve_ningun_widget_de_reportes(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(reverse("reports:dashboard-stats"), content)
        self.assertNotIn(reverse("reports:dashboard-recent-activity"), content)

    def test_usuario_sin_rol_asignar_no_ve_widgets(self):
        """Bucket 'sin asignar' del backfill de A1 -> tampoco es Administrador."""
        self.client.force_login(self.sin_rol)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(reverse("reports:dashboard-stats"), content)

    def test_dashboard_view_expone_es_administrador_en_contexto(self):
        """El view debe calcular `es_administrador` vía `user_has_rol`
        (no comparar string inline en el template) — regresión de la
        variable de contexto que consume el `{% if %}` del template."""
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertTrue(response.context["es_administrador"])

        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertFalse(response.context["es_administrador"])


class ReportsListStaysOpenRegressionTests(TestCase):
    """Regresión explícita: `reports:list` NO se gateó (a diferencia de lo
    que proponía el diagnóstico F1 antes de verificar el código) — sigue
    siendo el "puerto seguro" accesible a cualquier rol, diseño intencional
    de A10 ya testeado en `apps/reports/tests/test_views.py`. Este test
    documenta la decisión acá también, para que un futuro fix no lo gatee
    por error basándose solo en este issue."""

    def test_reports_list_accesible_para_cualquier_rol(self):
        client = Client()
        for rol in (Rol.EJECUTOR, Rol.COORDINADOR, Rol.ADMINISTRADOR, None):
            user = _make_user(rol=rol)
            client.force_login(user)
            response = client.get(reverse("reports:list"))
            self.assertEqual(response.status_code, 200, f"reports:list falló para rol={rol}")
