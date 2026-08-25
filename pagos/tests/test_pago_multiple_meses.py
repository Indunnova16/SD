"""Tests para la mejora "pagar varios meses de una vez" (atraso de clientes),
issue #92:

- El checkout ofrece opciones de pago por N meses (opciones_pago), sugiriendo
  `meses_atraso` cuando el cliente esta atrasado.
- El webhook y el redirect de WOMPI calculan `Pago.n_meses` a partir del
  monto realmente cobrado (no siempre 1), y _avanzar_fecha_proximo_pago avanza
  esa cantidad de periodos.
- La grilla de meses (grid_meses) refleja pagado/pendiente usando
  fecha_proximo_pago como cursor.

Complementa test_issue_2.py (que ya cubre AvanzarFechaProximoPagoHelperTests,
CalcularNMesesTests, MesesAtrasoPropertyTests con el helper y las properties
en aislamiento) con el flujo end-to-end de vistas.

Adaptado de pagos-template@f05a303 (sub-item A10): el template original
importaba `_crear_usuario_test(username=...)` desde test_issue_2.py -- ese
helper NO existe en SD. SD tiene `_crear_administrador(document_number,
**overrides)`, que ademas asigna rol=ADMINISTRADOR, necesario porque
PagoPortalView esta gateada RBAC desde #85/A3 (RolRequiredMixin,
allowed_roles=(Rol.ADMINISTRADOR,)) -- un usuario sin ese rol quedaria
redirigido por el gate, no por lo que el test intenta probar. Los 3 sitios
que llamaban _crear_usuario_test(username=...) se reemplazan por
_crear_administrador(document_number=..., password=...) con
document_number distintos por sitio.
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from pagos.models import Pago, PlanServicio, Suscripcion
from pagos.tests.test_issue_2 import _crear_administrador, _crear_datos_facturacion, WOMPI_SETTINGS


@override_settings(**WOMPI_SETTINGS)
class CheckoutOpcionesPagoTests(TestCase):
    def setUp(self):
        self.user = _crear_administrador('90000010', password='x')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000, activo=True)
        self.datos = _crear_datos_facturacion()
        self.client = Client()
        self.client.force_login(self.user)

    def test_al_dia_ofrece_opciones_desde_1_sugiere_1(self):
        Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.context['meses_atraso'], 0)
        self.assertEqual(r.context['meses_sugeridos'], 1)
        opciones = r.context['opciones_pago']
        self.assertEqual(opciones[0]['n'], 1)
        self.assertEqual(opciones[0]['monto_centavos'], 10000000)
        # al menos 6 opciones aunque no haya atraso, para poder adelantar meses
        self.assertGreaterEqual(len(opciones), 6)

    def test_atrasado_3_meses_sugiere_3_y_monto_correcto(self):
        hoy = timezone.localdate()
        y, m = hoy.year, hoy.month - 2
        while m <= 0:
            m += 12
            y -= 1
        vencida_hace_3_meses = date(y, m, 1)
        Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=vencida_hace_3_meses,
            datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.context['meses_atraso'], 3)
        self.assertEqual(r.context['meses_sugeridos'], 3)
        opciones = {o['n']: o for o in r.context['opciones_pago']}
        self.assertIn(3, opciones)
        self.assertEqual(opciones[3]['monto_centavos'], 100000 * 100 * 3)

    def test_opcion_n1_mantiene_referencia_sin_sufijo_compat(self):
        Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        opciones = {o['n']: o for o in r.context['opciones_pago']}
        self.assertEqual(opciones[1]['reference'], r.context['wompi_reference'])
        self.assertEqual(opciones[1]['monto_centavos'], r.context['monto_centavos'])

    # -----------------------------------------------------------------
    # (#328) el <select>/banner se arman en el TEMPLATE desde el contexto
    # de la vista -- un test que solo mira r.context puede pasar con el
    # HTML mal armado (caso NOVAPCR). Estos assertean contra lo RENDERIZADO.
    # -----------------------------------------------------------------
    def test_al_dia_render_no_muestra_banner_de_atraso_pero_si_selector(self):
        Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        self.assertNotContains(r, 'meses de suscripcion')
        self.assertContains(r, 'Cuantos meses queres pagar?')
        self.assertContains(r, 'id="pago-meses-select"')
        self.assertContains(r, '1 mes -- $100.000')

    def test_atrasado_render_muestra_banner_y_opcion_de_3_meses(self):
        hoy = timezone.localdate()
        y, m = hoy.year, hoy.month - 2
        while m <= 0:
            m += 12
            y -= 1
        vencida_hace_3_meses = date(y, m, 1)
        Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA', fecha_proximo_pago=vencida_hace_3_meses,
            datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        self.assertContains(r, 'Debes 3 meses de suscripcion')
        self.assertContains(r, '3 meses -- $300.000')
        # opcion sugerida (N=3) debe venir seleccionada en el <select>
        self.assertContains(r, f'value="3" selected')

    def test_opciones_tienen_referencias_unicas_entre_si(self):
        Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos,
        )
        r = self.client.get(reverse('pagos:portal'))
        referencias = [o['reference'] for o in r.context['opciones_pago']]
        self.assertEqual(len(referencias), len(set(referencias)))


@override_settings(**WOMPI_SETTINGS)
class WebhookNMesesTests(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000)
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.client = Client()

    @staticmethod
    def _payload(tx_id, amount_cents, reference):
        return {
            'event': 'transaction.updated',
            'signature': {'checksum': 'irrelevante', 'properties': []},
            'data': {'transaction': {
                'id': tx_id, 'status': 'APPROVED',
                'amount_in_cents': amount_cents, 'reference': reference,
            }},
        }

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.verify_webhook_signature', return_value=True)
    def test_pago_de_3_meses_guarda_n_meses_3_y_avanza_3_periodos(self, mock_verify, mock_alegra):
        hoy_mes = timezone.localdate().replace(day=1)
        self.suscripcion.fecha_proximo_pago = hoy_mes
        self.suscripcion.estado = 'ACTIVA'
        self.suscripcion.save()

        payload = self._payload('tx-3m', amount_cents=100000 * 100 * 3, reference='REF-3M')
        r = self.client.post(reverse('pagos:webhook'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(r.status_code, 200)

        pago = Pago.objects.get(wompi_transaction_id='tx-3m')
        self.assertEqual(pago.n_meses, 3)

        self.suscripcion.refresh_from_db()
        esperado = date(hoy_mes.year, hoy_mes.month, 1)
        for _ in range(3):
            y, m = esperado.year, esperado.month + 1
            if m > 12:
                m, y = 1, y + 1
            esperado = date(y, m, 1)
        self.assertEqual(self.suscripcion.fecha_proximo_pago, esperado)

    @patch('pagos.views.alegra.generar_factura_desde_pago', return_value=None)
    @patch('pagos.views.wompi.get_transaction')
    def test_redirect_pago_de_2_meses_guarda_n_meses_2(self, mock_get_tx, mock_alegra):
        user = _crear_administrador('90000011', password='x')
        client = Client()
        client.force_login(user)
        mock_get_tx.return_value = {
            'status': 'APPROVED',
            'amount_in_cents': 100000 * 100 * 2,
            'reference': 'REF-REDIRECT-2M',
        }
        client.get(reverse('pagos:portal'), {'id': 'tx-redirect-2m'})
        pago = Pago.objects.get(wompi_transaction_id='tx-redirect-2m')
        self.assertEqual(pago.n_meses, 2)


class GridMesesTests(TestCase):
    def setUp(self):
        self.user = _crear_administrador('90000012', password='x')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=100000, activo=True)
        self.client = Client()
        self.client.force_login(self.user)

    def test_al_dia_todos_los_meses_de_la_ventana_pagados(self):
        futuro = timezone.localdate() + timedelta(days=200)
        Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=futuro)
        r = self.client.get(reverse('pagos:portal'))
        grid = r.context['grid_meses']
        self.assertEqual(len(grid), 6)
        self.assertTrue(all(m['pagado'] for m in grid))
        self.assertTrue(grid[-1]['es_actual'])

        # (#328) render real: la grilla completa debe verse en el HTML, no
        # solo en el contexto -- 6 badges verdes, ninguno rojo (nada
        # pendiente al dia). Sin Pago creados en este test, badge-error solo
        # puede venir de la grilla (la tabla de pagos recientes esta vacia).
        self.assertContains(r, 'Estado por mes')
        body = r.content.decode()
        self.assertEqual(body.count('badge-success'), 6)
        self.assertNotIn('badge-error', body)

    def test_atrasado_2_meses_los_ultimos_2_quedan_pendientes(self):
        # fecha_proximo_pago = hace 2 meses (calendario): el mes que era el
        # "proximo pago" en si NO cuenta como pagado (es el que se debia) --
        # con meses_atraso=3 (formula (hoy-fpp)+1), pendientes son los ultimos
        # 3 slots de la grilla (actual, -1, -2); el -3 (3 meses atras) si esta
        # pagado porque es estrictamente anterior al mes de fecha_proximo_pago.
        hoy = timezone.localdate()
        y, m = hoy.year, hoy.month - 2
        while m <= 0:
            m += 12
            y -= 1
        Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=date(y, m, 1))
        r = self.client.get(reverse('pagos:portal'))
        grid = r.context['grid_meses']
        self.assertFalse(grid[-1]['pagado'])
        self.assertFalse(grid[-2]['pagado'])
        self.assertFalse(grid[-3]['pagado'])
        self.assertTrue(grid[-4]['pagado'])

        # (#328) render real: mezcla de badges rojos (pendiente) y verdes
        # (pagado) visible en el HTML servido.
        body = r.content.decode()
        self.assertIn('badge-error', body)
        self.assertIn('badge-success', body)

    def test_sin_suscripcion_no_rompe(self):
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.status_code, 200)
        grid = r.context['grid_meses']
        self.assertEqual(len(grid), 6)
        self.assertTrue(all(not m['pagado'] for m in grid))
