"""Conciliación contra la API de WOMPI (origen: incidente Obraje jul-2026,
pago cobrado por WOMPI sin registro local por webhook roto + redirect no
completado). Cubre: detección por prefijo, exclusión de pagos ya
registrados, exclusión de otras apps del merchant compartido, y el endpoint
cron de solo-detección.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from pagos.conciliacion import detectar_faltantes
from pagos.models import Pago, PlanServicio, Suscripcion


def _tx(tx_id, ref, status="APPROVED", cents=7500000):
    return {
        "id": tx_id,
        "reference": ref,
        "status": status,
        "amount_in_cents": cents,
        "created_at": "2026-08-01T12:00:00.000Z",
        "finalized_at": "2026-08-01T12:01:00.000Z",
    }


@override_settings(WOMPI_REFERENCE_PREFIX="MIAPP")
class DetectarFaltantesTest(TestCase):
    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre="Plan", precio=75000)
        self.suscripcion = Suscripcion.objects.create(plan=self.plan)

    @patch("pagos.conciliacion.wompi.listar_transacciones")
    def test_detecta_aprobada_sin_registro_local(self, mock_list):
        mock_list.return_value = [_tx("tx-perdida", "MIAPP-1-1-202608-1M")]

        faltantes = detectar_faltantes(dias=7)

        self.assertEqual([t["id"] for t in faltantes], ["tx-perdida"])

    @patch("pagos.conciliacion.wompi.listar_transacciones")
    def test_ignora_pago_ya_registrado(self, mock_list):
        Pago.objects.create(
            suscripcion=self.suscripcion,
            monto=75000,
            estado="APROBADO",
            wompi_transaction_id="tx-registrada",
        )
        mock_list.return_value = [_tx("tx-registrada", "MIAPP-1-1-202608-1M")]

        self.assertEqual(detectar_faltantes(dias=7), [])

    @patch("pagos.conciliacion.wompi.listar_transacciones")
    def test_ignora_otras_apps_del_merchant_compartido(self, mock_list):
        # El merchant WOMPI es compartido: la API devuelve transacciones de
        # TODO el portafolio (OBRAJE-, NOVAPCR-, DI-...). Solo las del
        # prefijo propio cuentan.
        mock_list.return_value = [
            _tx("tx-obraje", "OBRAJE-x-y-202608-1M"),
            _tx("tx-di", "DI-1-1-202608-1M"),
        ]

        self.assertEqual(detectar_faltantes(dias=7), [])

    @patch("pagos.conciliacion.wompi.listar_transacciones")
    def test_ignora_no_aprobadas(self, mock_list):
        mock_list.return_value = [
            _tx("tx-declinada", "MIAPP-1-1-202608-1M", status="DECLINED"),
            _tx("tx-pendiente", "MIAPP-1-1-202608-1M", status="PENDING"),
        ]

        self.assertEqual(detectar_faltantes(dias=7), [])


@override_settings(WOMPI_REFERENCE_PREFIX="MIAPP")
class CronConciliarWompiTest(TestCase):
    @patch("pagos.conciliacion.wompi.listar_transacciones")
    def test_post_reporta_faltantes_sin_registrar(self, mock_list):
        mock_list.return_value = [_tx("tx-perdida", "MIAPP-1-1-202608-1M")]

        resp = self.client.post(reverse("pagos:cron_conciliar_wompi"))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["faltantes"], 1)
        self.assertEqual(body["tx_ids"], ["tx-perdida"])
        # Solo-detección: NUNCA crea el Pago (eso es decisión humana --crear).
        self.assertFalse(Pago.objects.filter(wompi_transaction_id="tx-perdida").exists())

    def test_get_no_permitido(self):
        resp = self.client.get(reverse("pagos:cron_conciliar_wompi"))
        self.assertEqual(resp.status_code, 405)

    @patch("pagos.conciliacion.wompi.listar_transacciones", side_effect=Exception("API caida"))
    def test_error_de_api_responde_500_y_loguea(self, mock_list):
        resp = self.client.post(reverse("pagos:cron_conciliar_wompi"))
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.json()["success"])
