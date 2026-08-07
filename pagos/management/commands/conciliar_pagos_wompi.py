"""Concilia los pagos locales contra la API de WOMPI (fuente de verdad).

Detecta transacciones APPROVED del merchant que pertenecen a ESTA app
(prefijo WOMPI_REFERENCE_PREFIX) y no tienen Pago local — el escenario que
dejó un pago real de Obraje cobrado-pero-invisible en jul-2026 (webhook
roto + redirect no completado).

    python manage.py conciliar_pagos_wompi                # solo detecta y reporta
    python manage.py conciliar_pagos_wompi --dias 30      # ventana mas amplia
    python manage.py conciliar_pagos_wompi --crear        # ademas registra cada
                                                          # faltante (idempotente,
                                                          # misma logica del webhook:
                                                          # Pago + activar suscripcion
                                                          # + avanzar fecha + factura)

El default es SOLO-DETECCION a proposito: registrar un pago mueve dinero
(factura DIAN vía Alegra, avance de fecha) — la alerta avisa y un humano
decide correr --crear tras confirmar contra el dashboard de WOMPI.
"""
from django.core.management.base import BaseCommand

from pagos import alegra
from pagos.conciliacion import detectar_faltantes
from pagos.models import Pago, Suscripcion, calcular_n_meses
from pagos.views import _avanzar_fecha_proximo_pago

ESTADO_MAP = {
    'APPROVED': 'APROBADO',
    'DECLINED': 'RECHAZADO',
    'ERROR': 'ERROR',
    'PENDING': 'PENDIENTE',
    'VOIDED': 'RECHAZADO',
}


class Command(BaseCommand):
    help = 'Detecta (y opcionalmente registra) pagos WOMPI aprobados sin registro local.'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=7,
                            help='Ventana hacia atrás a conciliar (default 7)')
        parser.add_argument('--crear', action='store_true',
                            help='Registra cada faltante (Pago + suscripcion + factura)')

    def handle(self, *args, **options):
        faltantes = detectar_faltantes(dias=options['dias'])

        if not faltantes:
            self.stdout.write(self.style.SUCCESS(
                f'Conciliación OK: sin pagos faltantes en los últimos {options["dias"]} días.'
            ))
            return

        self.stdout.write(self.style.ERROR(
            f'{len(faltantes)} transacción(es) APROBADA(s) en WOMPI sin registro local:'
        ))
        for tx in faltantes:
            self.stdout.write(
                f'  tx={tx.get("id")} ref={tx.get("reference")} '
                f'monto=${tx.get("amount_in_cents", 0) / 100:,.0f} '
                f'finalizada={tx.get("finalized_at") or tx.get("created_at")}'
            )

        if not options['crear']:
            self.stdout.write(self.style.WARNING(
                'Solo detección (default). Para registrarlas: --crear '
                '(confirmá antes contra el dashboard de WOMPI).'
            ))
            return

        for tx in faltantes:
            self._registrar(tx)

    def _registrar(self, tx):
        """Misma lógica idempotente del webhook para un APPROVED recuperado."""
        tx_id = tx.get('id')
        monto = tx.get('amount_in_cents', 0) / 100
        suscripcion = Suscripcion.objects.select_related('plan').first()
        n_meses = (
            calcular_n_meses(monto, suscripcion.plan.precio)
            if suscripcion and suscripcion.plan else 1
        )
        pago, created = Pago.objects.get_or_create(
            wompi_transaction_id=tx_id,
            defaults={
                'suscripcion': suscripcion,
                'monto': monto,
                'n_meses': n_meses,
                'estado': 'PENDIENTE',
                'wompi_reference': tx.get('reference', ''),
            },
        )
        ya_estaba_aprobado = (not created) and (pago.estado == 'APROBADO')
        pago.estado = ESTADO_MAP.get(tx.get('status'), 'PENDIENTE')
        pago.detalle_respuesta = tx
        pago.save()
        self.stdout.write(self.style.SUCCESS(
            f'  Pago {"creado" if created else "actualizado"} id={pago.id} estado={pago.estado}'
        ))

        if ya_estaba_aprobado:
            return
        if pago.suscripcion:
            _avanzar_fecha_proximo_pago(pago)
            self.stdout.write(
                f'  Suscripción ACTIVA, próximo pago = {pago.suscripcion.fecha_proximo_pago}'
            )
        if not pago.alegra_invoice_id:
            try:
                factura = alegra.generar_factura_desde_pago(pago)
            except Exception as e:
                factura = None
                self.stdout.write(self.style.ERROR(f'  Error generando factura Alegra: {e}'))
            if factura:
                self.stdout.write(self.style.SUCCESS(
                    f'  Factura Alegra {pago.alegra_invoice_id} emitida.'
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    '  No se generó factura Alegra (revisar logs / datos de facturación).'
                ))
