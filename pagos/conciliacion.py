"""Conciliación contra la API de WOMPI — la fuente de verdad del dinero.

Origen (incidente Obraje 2026-07/08): el webhook y el redirect del navegador
pueden fallar AMBOS (bug de firma, bug de parseo, ruta faltante en el
wompi-router, cliente que cierra la pestaña...). Cuando eso pasa, WOMPI
cobra pero el sistema no registra nada — y nadie se entera hasta que el
cliente reclama. Esta conciliación cierra esa clase entera de problema:
consulta las transacciones reales del merchant y detecta cualquier APPROVED
de ESTA app (por prefijo de referencia) que no tenga su Pago local.

Se invoca desde el comando `conciliar_pagos_wompi` (manual / --crear) y
desde el endpoint `cron/conciliar-wompi/` (Cloud Scheduler diario,
solo-detección). Cada faltante se loguea como ERROR con el marcador
`CONCILIACION_WOMPI` — la alerta de Cloud Logging se engancha a ese texto.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import wompi
from .models import Pago

logger = logging.getLogger(__name__)


def detectar_faltantes(dias=7):
    """Transacciones APPROVED de esta app en WOMPI sin Pago local.

    Retorna la lista de transacciones (dicts crudos de la API) faltantes.
    Loguea un ERROR con marcador CONCILIACION_WOMPI por cada una.
    """
    prefix = getattr(settings, 'WOMPI_REFERENCE_PREFIX', 'APP') + '-'
    hasta = timezone.now()
    desde = hasta - timedelta(days=dias)
    txs = wompi.listar_transacciones(
        desde.strftime('%Y-%m-%dT%H:%M:%S'),
        hasta.strftime('%Y-%m-%dT%H:%M:%S'),
    )

    faltantes = []
    for tx in txs:
        ref = tx.get('reference') or ''
        if not ref.startswith(prefix):
            continue  # transaccion de OTRA app del portafolio (merchant compartido)
        if tx.get('status') != 'APPROVED':
            continue
        if Pago.objects.filter(wompi_transaction_id=tx.get('id', '')).exists():
            continue
        faltantes.append(tx)
        logger.error(
            'CONCILIACION_WOMPI: transaccion APROBADA sin registro local '
            'tx=%s ref=%s monto_cents=%s finalizada=%s',
            tx.get('id'), ref, tx.get('amount_in_cents'),
            tx.get('finalized_at') or tx.get('created_at'),
        )
    return faltantes
