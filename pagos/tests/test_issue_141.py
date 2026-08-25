"""Regresion issue #141: el portal de pagos mostraba $15.000.000 en vez de
$150.000 porque templates/pagos/portal.html reutilizaba `monto_centavos`
(calculado solo para `amount_in_cents` de WOMPI, = plan.precio*100) para
mostrarle el monto al cliente. El cobro real via WOMPI era correcto -- el
bug era 100% de visualizacion. Fix: `monto_pesos` (plan.precio, sin *100)
separado de `monto_centavos`, usado solo para el display.
"""
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from pagos.models import PlanServicio, Suscripcion
from pagos.tests.test_issue_2 import _crear_administrador, _crear_datos_facturacion, WOMPI_SETTINGS


@override_settings(**WOMPI_SETTINGS)
class MontoPesosVsCentavosTests(TestCase):
    def setUp(self):
        self.user = _crear_administrador('90000141', password='x')
        self.plan = PlanServicio.objects.create(nombre='Plan Test', precio=150000, activo=True)
        self.datos = _crear_datos_facturacion()
        # estado='PENDIENTE' -> requiere_pago=True, condicion para que el
        # template renderice el selector de meses + widget WOMPI (sin esto
        # el portal solo muestra el alert "Suscripcion activa").
        Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', datos_facturacion=self.datos)
        self.client = Client()
        self.client.force_login(self.user)

    def test_monto_pesos_en_contexto_no_esta_multiplicado_por_100(self):
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.context['monto_pesos'], 150000)
        self.assertEqual(r.context['monto_centavos'], 15000000)

    def test_opciones_pago_monto_pesos_escala_linealmente_por_n_sin_x100(self):
        r = self.client.get(reverse('pagos:portal'))
        opciones = {o['n']: o for o in r.context['opciones_pago']}
        self.assertEqual(opciones[1]['monto_pesos'], 150000)
        self.assertEqual(opciones[1]['monto_centavos'], 15000000)
        if 2 in opciones:
            self.assertEqual(opciones[2]['monto_pesos'], 300000)
            self.assertEqual(opciones[2]['monto_centavos'], 30000000)

    def test_render_muestra_pesos_correctos_no_15_millones(self):
        """Reproduce el reporte EXACTO del cliente: el selector y el 'Total a
        pagar' deben mostrar $150.000, nunca $15.000.000 / $15000000."""
        r = self.client.get(reverse('pagos:portal'))
        body = r.content.decode()
        self.assertIn('mes -- $150.000', body)
        self.assertIn('>150.000</span> COP', body)
        self.assertNotIn('15.000.000', body)
        self.assertNotIn('15000000 COP', body)
        self.assertNotIn('COP (centavos)', body)

    def test_data_amount_in_cents_sigue_en_centavos_para_wompi(self):
        """No-regresion: el widget WOMPI (data-amount-in-cents) DEBE seguir
        recibiendo el monto en centavos -- si esto cambia, WOMPI cobra mal."""
        r = self.client.get(reverse('pagos:portal'))
        body = r.content.decode()
        self.assertIn('data-amount-in-cents="15000000"', body)
