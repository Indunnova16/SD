"""Tests para issue #90: banner de aviso de pago vencido con 5 dias de gracia.

`alerta_pago_vencido` es una property NUEVA, separada de `requiere_pago`
(esa sigue igual -- controla el widget de pago, visible desde el dia 1 del
vencimiento). `alerta_pago_vencido` es mas estricta: solo dispara desde el
dia 5+ de vencimiento, y alimenta el banner global via context processor
(`pagos.context_processors.alertas_pago`), gateado a Rol.ADMINISTRADOR --
mismo publico que ya ve el link "Portal de Pagos" en el navbar (issue #85
A3) -- y renderizado en `templates/partials/navbar.html`, separado del link
del navbar (ese no cambia).

Cubre:
1. Property `alerta_pago_vencido` -- dia del vencimiento, dias 1-4 despues
   (False), dia 5+ despues (True), y los casos que ya bloqueaba
   `requiere_pago`/`fecha_proximo_pago` (False).
2. El banner aparece en el HTML SOLO para ADMINISTRADOR y SOLO cuando
   `alerta_pago_vencido` es True, en cualquier pagina (no solo el portal de
   pagos) -- prueba que vive en el layout global, no en portal.html.
3. El link "Portal de Pagos" del navbar (issue #85, no tocado por este
   issue) sigue sin depender de `alerta_pago_vencido` -- sigue siendo
   ADMINISTRADOR-only desde el dia 1.
"""

import itertools
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from pagos.context_processors import alertas_pago
from pagos.models import DatosFacturacion, PlanServicio, Suscripcion

User = get_user_model()

_SEQ = itertools.count(1)

WOMPI_SETTINGS = {
    "WOMPI_PUBLIC_KEY": "pub_test",
    "WOMPI_PRIVATE_KEY": "priv_test",
    "WOMPI_EVENTS_KEY": "events_test",
    "WOMPI_INTEGRITY_KEY": "integrity_test",
    "WOMPI_SANDBOX": True,
    "WOMPI_REFERENCE_PREFIX": "TEST",
}

BANNER_TEXT = "5 o más días vencido"


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "document_number": f"92{n:07d}",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "I90",
        "document_type": "CC",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


# ---------------------------------------------------------------------------
# 1. Property `alerta_pago_vencido`
# ---------------------------------------------------------------------------
class AlertaPagoVencidoPropertyTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre="Plan Test", precio=100000)

    def _suscripcion_vencida_hace(self, dias):
        fecha = timezone.localdate() - timedelta(days=dias)
        return Suscripcion.objects.create(
            plan=self.plan,
            estado="ACTIVA",
            fecha_proximo_pago=fecha,
        )

    def test_vence_hoy_no_dispara_banner(self):
        s = self._suscripcion_vencida_hace(0)
        self.assertTrue(s.requiere_pago, "requiere_pago si debe activarse el mismo dia")
        self.assertFalse(s.alerta_pago_vencido)

    def test_dia_1_despues_del_vencimiento_no_dispara_banner(self):
        self.assertFalse(self._suscripcion_vencida_hace(1).alerta_pago_vencido)

    def test_dia_2_despues_del_vencimiento_no_dispara_banner(self):
        self.assertFalse(self._suscripcion_vencida_hace(2).alerta_pago_vencido)

    def test_dia_3_despues_del_vencimiento_no_dispara_banner(self):
        self.assertFalse(self._suscripcion_vencida_hace(3).alerta_pago_vencido)

    def test_dia_4_despues_del_vencimiento_no_dispara_banner(self):
        self.assertFalse(self._suscripcion_vencida_hace(4).alerta_pago_vencido)

    def test_dia_5_despues_del_vencimiento_si_dispara_banner(self):
        self.assertTrue(self._suscripcion_vencida_hace(5).alerta_pago_vencido)

    def test_dia_10_despues_del_vencimiento_sigue_disparando_banner(self):
        self.assertTrue(self._suscripcion_vencida_hace(10).alerta_pago_vencido)

    def test_activa_vigente_no_dispara_banner(self):
        futuro = timezone.localdate() + timedelta(days=10)
        s = Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=futuro)
        self.assertFalse(s.requiere_pago)
        self.assertFalse(s.alerta_pago_vencido)

    def test_activa_sin_fecha_proximo_pago_no_dispara_banner(self):
        # requiere_pago es False (no hay fecha) -- alerta_pago_vencido hereda
        # ese False, no intenta restar sobre None.
        s = Suscripcion.objects.create(plan=self.plan, estado="ACTIVA")
        self.assertFalse(s.requiere_pago)
        self.assertFalse(s.alerta_pago_vencido)

    def test_pendiente_sin_fecha_proximo_pago_no_dispara_banner(self):
        # requiere_pago es True (estado != ACTIVA) pero sin fecha_proximo_pago
        # no hay "dias vencidos" que contar -- el guard `or not
        # self.fecha_proximo_pago` debe cubrir este caso.
        s = Suscripcion.objects.create(plan=self.plan, estado="PENDIENTE")
        self.assertTrue(s.requiere_pago)
        self.assertFalse(s.alerta_pago_vencido)


# ---------------------------------------------------------------------------
# 2. Context processor -- unit test directo (sin pasar por el template)
# ---------------------------------------------------------------------------
class AlertasPagoContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.plan = PlanServicio.objects.create(nombre="Plan Test", precio=100000)

    def _request_como(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_administrador_con_alerta_activa_ve_true(self):
        vencida = timezone.localdate() - timedelta(days=6)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        ctx = alertas_pago(self._request_como(admin))
        self.assertTrue(ctx["alerta_pago_vencido"])

    def test_administrador_sin_alerta_activa_ve_false(self):
        vencida = timezone.localdate() - timedelta(days=2)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        ctx = alertas_pago(self._request_como(admin))
        self.assertFalse(ctx["alerta_pago_vencido"])

    def test_ejecutor_nunca_ve_alerta_aunque_este_activa(self):
        vencida = timezone.localdate() - timedelta(days=30)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        ctx = alertas_pago(self._request_como(ejecutor))
        self.assertFalse(ctx["alerta_pago_vencido"])

    def test_coordinador_nunca_ve_alerta_aunque_este_activa(self):
        vencida = timezone.localdate() - timedelta(days=30)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        coordinador = _make_user(rol=User.Rol.COORDINADOR)
        ctx = alertas_pago(self._request_como(coordinador))
        self.assertFalse(ctx["alerta_pago_vencido"])

    def test_anonimo_nunca_ve_alerta(self):
        from django.contrib.auth.models import AnonymousUser

        vencida = timezone.localdate() - timedelta(days=30)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        ctx = alertas_pago(self._request_como(AnonymousUser()))
        self.assertFalse(ctx["alerta_pago_vencido"])

    def test_sin_suscripcion_no_rompe_y_da_false(self):
        admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        ctx = alertas_pago(self._request_como(admin))
        self.assertFalse(ctx["alerta_pago_vencido"])


# ---------------------------------------------------------------------------
# 3. Banner renderizado en el layout global (navbar.html) -- no solo en el
#    portal de pagos, en CUALQUIER pagina (accounts:dashboard, @login_required
#    generico sin gate de rol).
# ---------------------------------------------------------------------------
class BannerGlobalEnLayoutTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre="Plan Test", precio=100000, activo=True)
        self.client = Client()

    def test_administrador_ve_banner_en_dashboard_cuando_vencido_5_dias(self):
        vencida = timezone.localdate() - timedelta(days=5)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(admin)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, BANNER_TEXT)
        # El link al portal sigue ahi -- el banner no lo reemplaza.
        self.assertContains(response, "Portal de Pagos")

    def test_administrador_no_ve_banner_en_dashboard_cuando_vencido_2_dias(self):
        vencida = timezone.localdate() - timedelta(days=2)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(admin)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, BANNER_TEXT)
        # El link al portal sigue visible desde el dia 1 -- eso no cambia.
        self.assertContains(response, "Portal de Pagos")

    def test_ejecutor_nunca_ve_banner_aunque_lleve_30_dias_vencido(self):
        vencida = timezone.localdate() - timedelta(days=30)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.client.force_login(ejecutor)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, BANNER_TEXT)
        # Tampoco ve el link del navbar -- ese gate ya existia (issue #85/#89).
        self.assertNotContains(response, "Portal de Pagos")

    def test_coordinador_nunca_ve_banner_aunque_lleve_30_dias_vencido(self):
        vencida = timezone.localdate() - timedelta(days=30)
        Suscripcion.objects.create(plan=self.plan, estado="ACTIVA", fecha_proximo_pago=vencida)
        coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.client.force_login(coordinador)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, BANNER_TEXT)


@override_settings(**WOMPI_SETTINGS)
class BannerEnPortalDePagosTests(TestCase):
    """El banner tambien debe verse dentro del propio portal de pagos (extiende
    el mismo layout), coexistiendo con el widget de pago que sigue activo
    desde el dia 1 (requiere_pago)."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre="Plan Test", precio=100000, activo=True)
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client = Client()
        self.client.force_login(self.admin)
        # El widget WOMPI solo se renderiza si ya hay datos_facturacion
        # cargados (ver templates/pagos/portal.html) -- sin esto ambos tests
        # caerian en la rama "Completar Datos de Facturacion", nunca en el
        # widget, sin relacion con alerta_pago_vencido.
        self.datos = DatosFacturacion.objects.create(
            tipo_persona="NATURAL",
            razon_social="Cliente Test",
            tipo_identificacion="CC",
            numero_identificacion="123456",
            email="cliente@test.com",
            telefono="3000000000",
            direccion="Calle 1 # 2-3",
            ciudad="Bogota",
            departamento="Bogota",
        )

    def test_banner_y_widget_de_pago_coexisten_desde_dia_5(self):
        vencida = timezone.localdate() - timedelta(days=5)
        Suscripcion.objects.create(
            plan=self.plan,
            estado="ACTIVA",
            fecha_proximo_pago=vencida,
            datos_facturacion=self.datos,
        )

        response = self.client.get(reverse("pagos:portal"))
        self.assertContains(response, BANNER_TEXT)
        self.assertContains(response, "checkout.wompi.co/widget.js")

    def test_widget_de_pago_sin_banner_entre_dia_1_y_4(self):
        vencida = timezone.localdate() - timedelta(days=1)
        Suscripcion.objects.create(
            plan=self.plan,
            estado="ACTIVA",
            fecha_proximo_pago=vencida,
            datos_facturacion=self.datos,
        )

        response = self.client.get(reverse("pagos:portal"))
        self.assertNotContains(response, BANNER_TEXT)
        self.assertContains(response, "checkout.wompi.co/widget.js")
