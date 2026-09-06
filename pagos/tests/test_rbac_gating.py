"""Tests nuevos de gating RBAC para las 3 vistas autenticadas de pagos/
(issue #85, sub-item A10).

Edge case real de SD que la fuente (pagos-template) no cubre: el template
original solo tenia `LoginRequiredMixin` generico, sin distincion de rol.
SD#58 introdujo `apps.accounts.permissions.RolRequiredMixin` y el issue #85
(sub-item A3) lo aplica a `DatosFacturacionView`, `PagoPortalView` y
`HistorialPagosView` restringido a `Rol.ADMINISTRADOR`.

Cubre las 3 vistas gateadas de A3:
  - happy: ADMINISTRADOR accede (200) a las 3.
  - edge:  EJECUTOR queda bloqueado (redirect a reports:dashboard) en las 3.
  - edge:  COORDINADOR queda bloqueado (redirect a reports:dashboard) en las 3.
  - edge (bonus): usuario anonimo tambien queda bloqueado -- RolRequiredMixin
    NO hereda de LoginRequiredMixin, `user_has_rol` devuelve False para
    AnonymousUser.is_authenticated=False igual que para un rol incorrecto,
    asi que el redirect es el mismo target (reports:dashboard), no
    accounts:login.

WompiWebhookView (endpoint publico, auth via firma HMAC) queda
deliberadamente FUERA de este archivo -- no lleva RolRequiredMixin (ver
pagos/views.py y el comentario de sitios_checklist de A3).
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

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

# Las 3 vistas gateadas por RolRequiredMixin(allowed_roles=(Rol.ADMINISTRADOR,))
# en pagos/views.py (sub-item A3). WompiWebhookView queda deliberadamente
# fuera -- no tiene gate de rol.
GATED_URL_NAMES = ["pagos:portal", "pagos:facturacion", "pagos:historial"]


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "document_number": f"91{n:07d}",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A10",
        "document_type": "CC",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


@override_settings(**WOMPI_SETTINGS)
class RbacGatingHappyPathTests(TestCase):
    """happy: ADMINISTRADOR accede (200) a las 3 vistas gateadas."""

    def setUp(self):
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client = Client()
        self.client.force_login(self.admin)

        # Fixtures minimos para que las 3 vistas rendericen 200 en vez de
        # fallar por falta de datos (plan activo + suscripcion + datos de
        # facturacion, igual que ui_nueva_reconciliar del F2).
        self.plan = PlanServicio.objects.create(nombre="Plan Test", precio=100000, activo=True)
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
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan,
            estado="PENDIENTE",
            datos_facturacion=self.datos,
        )

    def test_administrador_accede_al_portal(self):
        response = self.client.get(reverse("pagos:portal"))
        self.assertContains(response, "Portal de Pagos")

    def test_administrador_accede_a_facturacion(self):
        response = self.client.get(reverse("pagos:facturacion"))
        # El <select name="tipo_identificacion"> se arma en el template desde
        # las choices reales del modelo (DatosFacturacion.TIPO_IDENTIFICACION_CHOICES)
        # -- assertContains sobre el HTML renderizado, no solo status 200.
        self.assertContains(response, 'name="tipo_identificacion"')
        self.assertContains(response, "facturacionForm")

    def test_administrador_accede_a_historial(self):
        response = self.client.get(reverse("pagos:historial"))
        self.assertContains(response, "Historial de Pagos")


class RbacGatingEjecutorBloqueadoTests(TestCase):
    """edge: EJECUTOR queda bloqueado (redirect) en las 3 vistas."""

    def setUp(self):
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        self.client = Client()
        self.client.force_login(self.ejecutor)

    def test_ejecutor_bloqueado_en_portal(self):
        resp = self.client.get(reverse("pagos:portal"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)

    def test_ejecutor_bloqueado_en_facturacion(self):
        resp = self.client.get(reverse("pagos:facturacion"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)

    def test_ejecutor_bloqueado_en_historial(self):
        resp = self.client.get(reverse("pagos:historial"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)


class RbacGatingCoordinadorBloqueadoTests(TestCase):
    """edge: COORDINADOR queda bloqueado (redirect) en las 3 vistas -- el
    portal de pagos es ADMINISTRADOR-only, ni siquiera COORDINADOR (que si
    tiene acceso a otras superficies admin-adjacentes del repo, ej. el bloque
    'Operaciones' del navbar) puede entrar."""

    def setUp(self):
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.client = Client()
        self.client.force_login(self.coordinador)

    def test_coordinador_bloqueado_en_portal(self):
        resp = self.client.get(reverse("pagos:portal"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)

    def test_coordinador_bloqueado_en_facturacion(self):
        resp = self.client.get(reverse("pagos:facturacion"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)

    def test_coordinador_bloqueado_en_historial(self):
        resp = self.client.get(reverse("pagos:historial"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)


class RbacGatingAnonimoBloqueadoTests(TestCase):
    """edge (bonus): un usuario anonimo tambien queda bloqueado.
    RolRequiredMixin NO extiende LoginRequiredMixin -- user_has_rol()
    devuelve False para AnonymousUser (is_authenticated=False) igual que
    para un rol incorrecto, asi que el redirect target es el mismo
    (reports:dashboard), NO accounts:login."""

    def test_anonimo_bloqueado_en_portal(self):
        client = Client()
        resp = client.get(reverse("pagos:portal"))
        self.assertRedirects(resp, reverse("reports:dashboard"), fetch_redirect_response=False)


class RbacGatingWebhookSinGateTests(TestCase):
    """Confirma que WompiWebhookView efectivamente NO tiene gate de rol/sesion
    -- un POST anonimo con firma invalida debe recibir 401 (rechazado por
    verify_webhook_signature), NUNCA un redirect por falta de autenticacion.
    Si alguien agregara RolRequiredMixin/LoginRequiredMixin a este endpoint
    por error, WOMPI (que llama sin cookie de sesion) dejaria de poder
    entregar webhooks -- este test existe para atrapar esa regresion."""

    def test_webhook_anonimo_con_firma_invalida_da_401_no_redirect(self):
        client = Client()
        resp = client.post(
            reverse("pagos:webhook"),
            data='{"event": "transaction.updated", "signature": {}, "data": {}}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
