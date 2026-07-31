"""
Tests para issue #2 (pagos-template): 5 gaps confirmados por F2 comparando
linea a linea contra ObrajeCRM/apps/pagos/ (ya corregido via commits
ba6b6ec/20d4b32/95ae100/a731af4):

1. views.py:163      -- referencia WOMPI con granularidad mensual (%Y%m) genera
                        colisiones si se reintenta un pago en el mismo mes.
2. models.py:58-82    -- Suscripcion sin fecha_proximo_pago / requiere_pago.
3. portal.html:38     -- gate estado=='ACTIVA' que nunca revierte (no oculta/
                        muestra el boton de pago segun venza la suscripcion).
4. models.py:104-107  -- Pago.Meta sin UniqueConstraint de respaldo en BD.
5. views.py:181-234   -- webhook sin gate de idempotencia (ya_estaba_aprobado).

Bonus (confirmado no-op por F2): alegra.py:85 ya usa pago.monto -- solo test
de regresion, no cambio de codigo.

Adaptado en issue #85 sub-item A9: el template original usaba
django.contrib.auth.models.User con username= (auth.User generico). SD usa
un custom User (apps.accounts.models.User, AUTH_USER_MODEL='accounts.User')
sin campo `username` -- USERNAME_FIELD='document_number',
REQUIRED_FIELDS=['first_name','last_name','job_position','hire_date']. Los
3 sitios que creaban usuarios via User.objects.create_user(username=...)
se adaptan a get_user_model() + los campos reales de accounts.User.
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from pagos import alegra
from pagos.models import DatosFacturacion, Pago, PlanServicio, Suscripcion, calcular_n_meses
from pagos.views import _avanzar_fecha_proximo_pago

User = get_user_model()

WOMPI_SETTINGS = dict(
    WOMPI_PUBLIC_KEY='pub_test',
    WOMPI_PRIVATE_KEY='priv_test',
    WOMPI_EVENTS_KEY='events_test',
    WOMPI_INTEGRITY_KEY='integrity_test',
    WOMPI_SANDBOX=True,
    WOMPI_REFERENCE_PREFIX='TEST',
)


def _crear_datos_facturacion(**overrides):
    data = dict(
        tipo_persona='NATURAL',
        razon_social='Cliente Test',
        tipo_identificacion='CC',
        numero_identificacion='123456',
        email='cliente@test.com',
        telefono='3000000000',
        direccion='Calle 1 # 2-3',
        ciudad='Bogota',
        departamento='Bogota',
    )
    data.update(overrides)
    return DatosFacturacion.objects.create(**data)


def _crear_administrador(document_number, **overrides):
    """Crea un usuario accounts.User con rol ADMINISTRADOR (issue #85 A3
    gatea las 3 vistas autenticadas a ADMINISTRADOR-only -- estos tests de
    A9 ejercitan las vistas via test Client, asi que el usuario de fixture
    necesita el rol correcto o quedaria redirigido por el gate de A3, no
    por lo que el test intenta probar)."""
    defaults = dict(
        password='x',
        first_name='QA',
        last_name='Pagos',
        job_position='Administrador',
        hire_date=date(2024, 1, 1),
        rol=User.Rol.ADMINISTRADOR,
    )
    defaults.update(overrides)
    return User.objects.create_user(document_number=document_number, **defaults)


# ---------------------------------------------------------------------------
# Gap #2 -- fecha_proximo_pago + property requiere_pago
# ---------------------------------------------------------------------------
class RequierePagoPropertyTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)

    def test_pendiente_requiere_pago(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.assertTrue(s.requiere_pago)

    def test_suspendida_requiere_pago(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='SUSPENDIDA')
        self.assertTrue(s.requiere_pago)

    def test_activa_sin_fecha_proximo_pago_no_requiere_pago(self):
        # Suscripcion activada antes de este fix: nunca tuvo fecha_proximo_pago.
        # No debe romperse ni exigir pago retroactivo por falta de dato.
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA')
        self.assertFalse(s.requiere_pago)

    def test_activa_con_fecha_vigente_no_requiere_pago(self):
        futuro = timezone.localdate() + timedelta(days=10)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=futuro)
        self.assertFalse(s.requiere_pago)

    def test_activa_con_fecha_vencida_requiere_pago(self):
        ayer = timezone.localdate() - timedelta(days=1)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=ayer)
        self.assertTrue(s.requiere_pago)

    def test_activa_que_vence_hoy_requiere_pago(self):
        hoy = timezone.localdate()
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=hoy)
        self.assertTrue(s.requiere_pago)


class AvanzarFechaProximoPagoHelperTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)

    def _pago(self, suscripcion, n_meses=1, monto=None):
        return Pago.objects.create(
            suscripcion=suscripcion,
            monto=monto if monto is not None else self.plan.precio * n_meses,
            n_meses=n_meses,
            estado='APROBADO',
        )

    def test_sin_fecha_previa_activa_y_avanza_desde_hoy(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        _avanzar_fecha_proximo_pago(self._pago(s))
        s.refresh_from_db()
        self.assertEqual(s.estado, 'ACTIVA')
        self.assertIsNotNone(s.fecha_proximo_pago)
        self.assertGreater(s.fecha_proximo_pago, timezone.localdate())

    def test_con_fecha_previa_vigente_avanza_desde_esa_fecha_no_desde_hoy(self):
        futuro = timezone.localdate() + timedelta(days=10)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=futuro)
        _avanzar_fecha_proximo_pago(self._pago(s))
        s.refresh_from_db()
        self.assertGreater(s.fecha_proximo_pago, futuro)

    def test_rollover_diciembre_a_enero(self):
        s = Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=date(2026, 12, 15)
        )
        _avanzar_fecha_proximo_pago(self._pago(s))
        s.refresh_from_db()
        self.assertEqual(s.fecha_proximo_pago, date(2027, 1, 15))

    def test_vencida_avanza_desde_la_fecha_vencida_no_desde_hoy(self):
        """Regresion del bug original: un pago de 1 mes mientras se deben 2
        NO debe "blanquear" el atraso reseteando a hoy -- debe avanzar desde
        la fecha vencida real, dejando 1 mes todavia pendiente."""
        vencida_hace_2_meses = timezone.localdate() - timedelta(days=65)
        s = Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=vencida_hace_2_meses
        )
        _avanzar_fecha_proximo_pago(self._pago(s, n_meses=1))
        s.refresh_from_db()
        self.assertEqual(s.fecha_proximo_pago, _sumar_un_mes(vencida_hace_2_meses))
        # todavia vencida (solo se pago 1 de los ~2 meses de atraso) -> sigue
        # pidiendo pago, no quedo "al dia" artificialmente
        self.assertTrue(s.requiere_pago)

    def test_pago_de_2_meses_avanza_2_periodos(self):
        s = Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=date(2026, 5, 20)
        )
        _avanzar_fecha_proximo_pago(self._pago(s, n_meses=2, monto=self.plan.precio * 2))
        s.refresh_from_db()
        self.assertEqual(s.fecha_proximo_pago, date(2026, 7, 20))


def _sumar_un_mes(fecha):
    from calendar import monthrange
    y, m, d = fecha.year, fecha.month, fecha.day
    m += 1
    if m > 12:
        m = 1
        y += 1
    return date(y, m, min(d, monthrange(y, m)[1]))


# ---------------------------------------------------------------------------
# Nuevo (issue #92): calcular_n_meses + Suscripcion.meses_atraso
# ---------------------------------------------------------------------------
class CalcularNMesesTests(TestCase):
    def test_un_mes_exacto(self):
        self.assertEqual(calcular_n_meses(100000, 100000), 1)

    def test_dos_meses_exactos(self):
        self.assertEqual(calcular_n_meses(200000, 100000), 2)

    def test_redondea_al_entero_mas_cercano(self):
        self.assertEqual(calcular_n_meses(195000, 100000), 2)

    def test_precio_cero_no_rompe_devuelve_1(self):
        self.assertEqual(calcular_n_meses(50000, 0), 1)

    def test_monto_menor_a_un_mes_nunca_devuelve_0(self):
        self.assertEqual(calcular_n_meses(30000, 100000), 1)


class MesesAtrasoPropertyTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)

    def test_sin_fecha_proximo_pago_cero(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.assertEqual(s.meses_atraso, 0)

    def test_fecha_futura_cero(self):
        futuro = timezone.localdate() + timedelta(days=10)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=futuro)
        self.assertEqual(s.meses_atraso, 0)

    def test_vencida_mismo_mes_un_mes_de_atraso(self):
        ayer = timezone.localdate() - timedelta(days=1)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=ayer)
        self.assertEqual(s.meses_atraso, 1)

    def test_vencida_hace_2_meses_calendario(self):
        hoy = timezone.localdate()
        y, m = hoy.year, hoy.month - 2
        while m <= 0:
            m += 12
            y -= 1
        vencida = date(y, m, hoy.day if hoy.day <= 28 else 28)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=vencida)
        self.assertEqual(s.meses_atraso, 3)


# ---------------------------------------------------------------------------
# Gap #4 -- UniqueConstraint parcial en Pago
# ---------------------------------------------------------------------------
class UniqueConstraintPagoTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')

    def test_wompi_reference_duplicado_no_vacio_falla(self):
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_reference='REF-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_reference='REF-1')

    def test_wompi_reference_vacio_puede_repetirse(self):
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_reference='')
        # No debe lanzar IntegrityError: la condicion excluye el string vacio.
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_reference='')

    def test_wompi_transaction_id_duplicado_no_vacio_falla(self):
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_transaction_id='TX-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_transaction_id='TX-1')

    def test_wompi_transaction_id_vacio_puede_repetirse(self):
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_transaction_id='')
        Pago.objects.create(suscripcion=self.suscripcion, monto=100000, wompi_transaction_id='')


# ---------------------------------------------------------------------------
# Gap #1 -- referencia WOMPI con microsegundos (no solo %Y%m)
# ---------------------------------------------------------------------------
@override_settings(**WOMPI_SETTINGS)
class ReferenciaUnicaPortalTests(TestCase):
    def setUp(self):
        self.user = _crear_administrador('90000001')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000, activo=True)
        self.datos = _crear_datos_facturacion()
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_dos_requests_seguidos_generan_referencias_distintas(self):
        r1 = self.client.get(reverse('pagos:portal'))
        r2 = self.client.get(reverse('pagos:portal'))
        ref1 = r1.context['wompi_reference']
        ref2 = r2.context['wompi_reference']
        self.assertNotEqual(
            ref1, ref2,
            'dos referencias generadas en el mismo mes (incluso en la misma sesion '
            'de pruebas) deben diferir gracias a la resolucion de microsegundos'
        )

    def test_referencia_incluye_resolucion_de_microsegundos(self):
        r = self.client.get(reverse('pagos:portal'))
        ref = r.context['wompi_reference']
        # formato esperado: {prefix}-{susc_id}-{plan_id}-YYYYMMDDHHMMSSffffff
        timestamp_part = ref.rsplit('-', 1)[-1]
        self.assertEqual(
            len(timestamp_part), 20,
            f'referencia {ref!r} no tiene el formato %Y%m%d%H%M%S%f (20 digitos)'
        )
        self.assertTrue(timestamp_part.isdigit())


# ---------------------------------------------------------------------------
# Gap #3 -- gate del portal debe revertir con requiere_pago, no con estado
# estatico
# ---------------------------------------------------------------------------
@override_settings(**WOMPI_SETTINGS)
class PortalGateTemplateTests(TestCase):
    def setUp(self):
        self.user = _crear_administrador('90000002')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000, activo=True)
        self.datos = _crear_datos_facturacion()
        self.client = Client()
        self.client.force_login(self.user)

    def test_activa_vigente_oculta_boton_de_pago(self):
        futuro = timezone.localdate() + timedelta(days=10)
        Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=futuro, datos_facturacion=self.datos,
        )
        response = self.client.get(reverse('pagos:portal'))
        self.assertContains(response, 'Suscripcion activa')
        self.assertNotContains(response, 'checkout.wompi.co/widget.js')

    def test_activa_vencida_muestra_boton_de_pago_de_nuevo(self):
        ayer = timezone.localdate() - timedelta(days=1)
        Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=ayer, datos_facturacion=self.datos,
        )
        response = self.client.get(reverse('pagos:portal'))
        self.assertNotContains(response, 'Suscripcion activa')
        self.assertContains(response, 'checkout.wompi.co/widget.js')

    def test_pendiente_muestra_boton_de_pago(self):
        Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos,
        )
        response = self.client.get(reverse('pagos:portal'))
        self.assertNotContains(response, 'Suscripcion activa')
        self.assertContains(response, 'checkout.wompi.co/widget.js')


# ---------------------------------------------------------------------------
# Gap #5 -- idempotencia del webhook (ya_estaba_aprobado)
# ---------------------------------------------------------------------------
@override_settings(**WOMPI_SETTINGS)
class WebhookIdempotenciaTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.client = Client()

    @staticmethod
    def _payload(tx_id='tx-webhook-1', status='APPROVED', amount_cents=10000000, reference='REF-WEBHOOK-1'):
        return {
            'event': 'transaction.updated',
            'timestamp': 1234567890,
            'signature': {
                'checksum': 'irrelevante-porque-mockeamos-verify',
                'properties': ['transaction.id', 'transaction.status'],
            },
            'data': {
                'transaction': {
                    'id': tx_id,
                    'status': status,
                    'amount_in_cents': amount_cents,
                    'reference': reference,
                }
            },
        }

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.verify_webhook_signature', return_value=True)
    def test_reintento_del_webhook_no_reavanza_fecha_proximo_pago(self, mock_verify, mock_alegra):
        payload = self._payload()

        r1 = self.client.post(
            reverse('pagos:webhook'), data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(r1.status_code, 200)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.estado, 'ACTIVA')
        primera_fecha = self.suscripcion.fecha_proximo_pago
        self.assertIsNotNone(primera_fecha)

        # WOMPI reintenta/duplica la entrega del MISMO webhook (mismo tx_id,
        # mismo status APPROVED) -- comportamiento real y documentado de WOMPI.
        r2 = self.client.post(
            reverse('pagos:webhook'), data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(r2.status_code, 200)
        self.suscripcion.refresh_from_db()
        segunda_fecha = self.suscripcion.fecha_proximo_pago

        self.assertEqual(
            primera_fecha, segunda_fecha,
            'el reintento del webhook para el mismo tx_id NO debe volver a avanzar fecha_proximo_pago'
        )
        self.assertEqual(
            mock_alegra.call_count, 1,
            'la factura Alegra no debe regenerarse en el reintento del webhook'
        )

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.verify_webhook_signature', return_value=True)
    def test_dos_transacciones_distintas_si_avanzan_dos_veces(self, mock_verify, mock_alegra):
        r1 = self.client.post(
            reverse('pagos:webhook'),
            data=json.dumps(self._payload(tx_id='tx-A', reference='REF-A')),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 200)
        self.suscripcion.refresh_from_db()
        primera_fecha = self.suscripcion.fecha_proximo_pago

        r2 = self.client.post(
            reverse('pagos:webhook'),
            data=json.dumps(self._payload(tx_id='tx-B', reference='REF-B')),
            content_type='application/json',
        )
        self.assertEqual(r2.status_code, 200)
        self.suscripcion.refresh_from_db()
        segunda_fecha = self.suscripcion.fecha_proximo_pago

        self.assertGreater(
            segunda_fecha, primera_fecha,
            'dos transacciones APROBADAS distintas si deben avanzar fecha_proximo_pago cada una'
        )
        self.assertEqual(mock_alegra.call_count, 2)


@override_settings(**WOMPI_SETTINGS)
class RedirectWompiTests(TestCase):
    """El redirect (_procesar_transaccion_wompi) es naturalmente idempotente
    porque solo crea el Pago si wompi_transaction_id no existia -- pero debe
    activar y avanzar fecha_proximo_pago igual que el webhook."""

    def setUp(self):
        self.user = _crear_administrador('90000003')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000, activo=True)
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.client = Client()
        self.client.force_login(self.user)

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.get_transaction')
    def test_redirect_aprobado_activa_y_avanza_fecha(self, mock_get_tx, mock_alegra):
        mock_get_tx.return_value = {
            'status': 'APPROVED',
            'amount_in_cents': 10000000,
            'reference': 'REF-REDIRECT-1',
        }
        resp = self.client.get(reverse('pagos:portal'), {'id': 'tx-redirect-1'})
        self.assertEqual(resp.status_code, 200)
        self.suscripcion.refresh_from_db()
        self.assertEqual(self.suscripcion.estado, 'ACTIVA')
        self.assertIsNotNone(self.suscripcion.fecha_proximo_pago)
        self.assertTrue(Pago.objects.filter(wompi_transaction_id='tx-redirect-1').exists())
        self.assertEqual(mock_alegra.call_count, 1)

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.get_transaction')
    def test_redirect_repetido_para_el_mismo_tx_no_duplica_pago(self, mock_get_tx, mock_alegra):
        mock_get_tx.return_value = {
            'status': 'APPROVED',
            'amount_in_cents': 10000000,
            'reference': 'REF-REDIRECT-2',
        }
        self.client.get(reverse('pagos:portal'), {'id': 'tx-redirect-2'})
        self.suscripcion.refresh_from_db()
        primera_fecha = self.suscripcion.fecha_proximo_pago

        # El navegador puede reenviar el mismo query param al refrescar la pagina.
        self.client.get(reverse('pagos:portal'), {'id': 'tx-redirect-2'})
        self.suscripcion.refresh_from_db()

        self.assertEqual(Pago.objects.filter(wompi_transaction_id='tx-redirect-2').count(), 1)
        self.assertEqual(self.suscripcion.fecha_proximo_pago, primera_fecha)
        self.assertEqual(mock_alegra.call_count, 1)


# ---------------------------------------------------------------------------
# Bonus -- regresion: alegra.py:85 ya usa pago.monto, no plan.precio (no-op
# confirmado por F2). Solo se agrega test, no cambio de codigo.
# ---------------------------------------------------------------------------
class AlegraMontoRegressionTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)
        self.datos = _crear_datos_facturacion(alegra_contacto_id='999')
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos
        )

    @patch('pagos.alegra.requests.post')
    def test_factura_usa_monto_del_pago_no_precio_del_plan(self, mock_post):
        # Monto del pago DISTINTO al precio del plan (pago parcial/prorrateado):
        # si el codigo usara plan.precio en vez de pago.monto, la factura
        # quedaria mal facturada.
        monto_pagado = 37500
        pago = Pago.objects.create(
            suscripcion=self.suscripcion,
            monto=monto_pagado,
            estado='APROBADO',
            wompi_transaction_id='tx-alegra-1',
        )
        mock_resp = mock_post.return_value
        mock_resp.status_code = 201
        mock_resp.json.return_value = {'id': 555}

        alegra.generar_factura_desde_pago(pago)

        self.assertTrue(mock_post.called)
        _, kwargs = mock_post.call_args
        payload = kwargs['json']
        item = payload['items'][0]
        pago_registrado = payload['payments'][0]

        self.assertEqual(pago_registrado['amount'], monto_pagado)
        self.assertAlmostEqual(item['price'] * item['quantity'], monto_pagado, places=2)
