import base64
import logging
from datetime import date, timedelta

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def get_headers():
    credentials = f"{settings.ALEGRA_EMAIL}:{settings.ALEGRA_API_TOKEN}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/json',
    }


def buscar_contacto(identificacion):
    url = f"{settings.ALEGRA_API_URL}/contacts"
    params = {'identification': identificacion}
    resp = requests.get(url, headers=get_headers(), params=params, timeout=15)
    resp.raise_for_status()
    contactos = resp.json()
    if contactos:
        return contactos[0]
    return None


def crear_contacto(datos_facturacion):
    kind_map = {
        'JURIDICA': 'LEGAL_ENTITY',
        'NATURAL': 'PERSON_ENTITY',
    }

    payload = {
        'name': datos_facturacion.razon_social,
        'identificationObject': {
            'type': datos_facturacion.tipo_identificacion,
            'number': datos_facturacion.numero_identificacion,
        },
        'kindOfPerson': kind_map.get(datos_facturacion.tipo_persona, 'PERSON_ENTITY'),
        'regime': datos_facturacion.regimen,
        'email': datos_facturacion.email,
        'phonePrimary': datos_facturacion.telefono,
        'address': {
            'address': datos_facturacion.direccion,
            'city': datos_facturacion.ciudad,
            'department': datos_facturacion.departamento,
        },
        'type': ['client'],
    }

    if datos_facturacion.dv:
        payload['identificationObject']['dv'] = datos_facturacion.dv

    url = f"{settings.ALEGRA_API_URL}/contacts"
    resp = requests.post(url, headers=get_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def obtener_o_crear_contacto(datos_facturacion):
    if datos_facturacion.alegra_contacto_id:
        return datos_facturacion.alegra_contacto_id

    contacto = buscar_contacto(datos_facturacion.numero_identificacion)
    if contacto:
        contacto_id = str(contacto['id'])
        datos_facturacion.alegra_contacto_id = contacto_id
        datos_facturacion.save(update_fields=['alegra_contacto_id'])
        return contacto_id

    contacto = crear_contacto(datos_facturacion)
    contacto_id = str(contacto['id'])
    datos_facturacion.alegra_contacto_id = contacto_id
    datos_facturacion.save(update_fields=['alegra_contacto_id'])
    return contacto_id


def crear_factura(contacto_id, plan, pago):
    hoy = date.today()
    vencimiento = hoy + timedelta(days=30)
    monto_pago = float(pago.monto)
    precio_mes = float(plan.precio)
    if precio_mes > 0:
        meses = max(1, round(monto_pago / precio_mes))
        if abs(meses * precio_mes - monto_pago) < 0.01:
            quantity = meses
            price = precio_mes
        else:
            quantity = 1
            price = monto_pago
    else:
        quantity = 1
        price = monto_pago

    payload = {
        'date': hoy.isoformat(),
        'dueDate': vencimiento.isoformat(),
        'client': {'id': int(contacto_id)},
        'status': 'open',
        'stamp': {'generateStamp': True},
        'paymentForm': 'CASH',
        'paymentMethod': 'DEBIT_CARD',
        'numberTemplate': {'id': settings.ALEGRA_NUMBER_TEMPLATE_ID},
        'items': [
            {
                'id': settings.ALEGRA_ITEM_ID,
                'description': f"Plan {plan.nombre} - Plataforma SaaS + Hosting + Soporte ({hoy.strftime('%b %Y')})",
                'price': price,
                'quantity': quantity,
                'tax': [],
            }
        ],
        'payments': [
            {
                'date': hoy.isoformat(),
                'amount': monto_pago,
                'paymentMethod': 'transfer',
                'account': {'id': settings.ALEGRA_BANK_ACCOUNT_ID},
            }
        ],
        'observations': f"Pago procesado por WOMPI - TX: {pago.wompi_transaction_id}",
    }

    url = f"{settings.ALEGRA_API_URL}/invoices"
    resp = requests.post(url, headers=get_headers(), json=payload, timeout=30)
    data = resp.json()
    if resp.status_code in (200, 201):
        return data
    if 'invoice' in data:
        logger.warning(f'Factura creada como borrador: {data.get("error", {}).get("message", "")}')
        return data['invoice']
    resp.raise_for_status()
    return data


def generar_factura_desde_pago(pago):
    suscripcion = pago.suscripcion
    datos = suscripcion.datos_facturacion

    if not datos:
        logger.warning(f'Pago {pago.id}: sin datos de facturacion, no se genera factura Alegra')
        return None

    try:
        contacto_id = obtener_o_crear_contacto(datos)
        factura = crear_factura(contacto_id, suscripcion.plan, pago)
        invoice_id = str(factura.get('id', ''))
        pago.alegra_invoice_id = invoice_id
        pago.save(update_fields=['alegra_invoice_id'])
        logger.info(f'Factura Alegra {invoice_id} creada para pago {pago.id}')
        return factura
    except requests.RequestException as e:
        logger.error(f'Error creando factura Alegra para pago {pago.id}: {e}')
        return None
