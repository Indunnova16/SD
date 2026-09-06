"""verify_webhook_signature() resolvia las `properties` de la firma (rutas
tipo "transaction.id", relativas a `data`) contra `data.transaction` ya
desanidado -- duplicaba el prefijo "transaction" y explotaba con
"'str' object has no attribute 'get'" en el 2do segmento ante CUALQUIER
webhook real de WOMPI (bug portfolio-wide, confirmado tambien en SD,
ya parchado en pagos-template#12 y en FormasFuturo Refs #68, portado aca
antes de que se materialice como pago perdido).
"""

import hashlib

from django.test import TestCase, override_settings

from pagos import wompi


@override_settings(
    WOMPI_EVENTS_KEY="events-secret-real", WOMPI_INTEGRITY_KEY="integrity-secret-checkout"
)
class VerifyWebhookSignatureTest(TestCase):
    def _payload(self, checksum):
        return {
            "timestamp": 1700000000,
            "signature": {
                "properties": [
                    "transaction.id",
                    "transaction.status",
                    "transaction.amount_in_cents",
                ],
                "checksum": checksum,
            },
            "data": {
                "transaction": {
                    "id": "tx-firma-1",
                    "status": "APPROVED",
                    "amount_in_cents": 7500000,
                }
            },
        }

    def _checksum_con(self, key):
        concat = "tx-firma-1" + "APPROVED" + "7500000" + "1700000000" + key
        return hashlib.sha256(concat.encode()).hexdigest()

    def test_no_crashea_y_firma_real_es_valida(self):
        """Regresion del bug: antes esto lanzaba AttributeError. Ahora debe
        resolver bien las properties y validar la firma real (events key)."""
        checksum_real = self._checksum_con("events-secret-real")
        payload = self._payload(checksum_real)

        self.assertTrue(wompi.verify_webhook_signature(payload, checksum_real))

    def test_firma_con_integrity_key_es_invalida(self):
        checksum_con_integrity = self._checksum_con("integrity-secret-checkout")
        payload = self._payload(checksum_con_integrity)

        self.assertFalse(wompi.verify_webhook_signature(payload, checksum_con_integrity))

    def test_checksum_incorrecto_es_invalido(self):
        payload = self._payload("checksum-cualquiera-invalido")

        self.assertFalse(wompi.verify_webhook_signature(payload, "checksum-cualquiera-invalido"))
