import hashlib
import json
import logging
from calendar import monthrange
from datetime import date
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, ListView
from apps.accounts.permissions import RolRequiredMixin, Rol
from .models import PlanServicio, Suscripcion, Pago, DatosFacturacion, calcular_n_meses
from . import wompi
from . import alegra

logger = logging.getLogger(__name__)


def _sumar_meses(fecha, n_meses):
    y, m, d = fecha.year, fecha.month, fecha.day
    m += n_meses
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    dia = min(d, monthrange(y, m)[1])
    return date(y, m, dia)


def _avanzar_fecha_proximo_pago(pago):
    """Avanza fecha_proximo_pago `pago.n_meses` periodos tras un pago
    aprobado, y marca la suscripcion como ACTIVA.

    Avanza SIEMPRE desde la fecha_proximo_pago anterior (vigente o vencida),
    nunca desde "hoy" -- si se reseteara a hoy cuando esta vencida, un cliente
    atrasado 2 meses que paga 1 mes quedaria "al dia" artificialmente: el mes
    que debia desaparece sin quedar registrado. Al avanzar desde la fecha
    vencida real, si el pago no alcanza a cubrir todo el atraso la suscripcion
    sigue en requiere_pago=True (correcto: todavia debe meses)."""
    suscripcion = pago.suscripcion
    hoy = timezone.localdate()
    base = suscripcion.fecha_proximo_pago or hoy
    suscripcion.estado = 'ACTIVA'
    suscripcion.fecha_proximo_pago = _sumar_meses(base, pago.n_meses)
    suscripcion.save(update_fields=['estado', 'fecha_proximo_pago', 'updated_at'])
    logger.info(
        f'Suscripcion {suscripcion.id}: proximo pago avanzado a '
        f'{suscripcion.fecha_proximo_pago} ({pago.n_meses} mes(es) cubiertos por pago {pago.id})'
    )


class DatosFacturacionView(RolRequiredMixin, TemplateView):
    allowed_roles = (Rol.ADMINISTRADOR,)
    redirect_url = 'reports:dashboard'
    template_name = 'pagos/datos_facturacion.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        suscripcion = Suscripcion.objects.first()
        datos = suscripcion.datos_facturacion if suscripcion else None
        if datos:
            context['d'] = {
                'tipo_persona': datos.tipo_persona,
                'razon_social': datos.razon_social,
                'tipo_identificacion': datos.tipo_identificacion,
                'numero_identificacion': datos.numero_identificacion,
                'dv': datos.dv or '',
                'email': datos.email,
                'telefono': datos.telefono,
                'direccion': datos.direccion,
                'ciudad': datos.ciudad,
                'departamento': datos.departamento,
                'regimen': datos.regimen,
            }
        else:
            context['d'] = {
                'tipo_persona': '',
                'razon_social': '',
                'tipo_identificacion': 'CC',
                'numero_identificacion': '',
                'dv': '',
                'email': '',
                'telefono': '',
                'direccion': '',
                'ciudad': '',
                'departamento': '',
                'regimen': 'COMMON_REGIME',
            }
        return context

    def post(self, request, *args, **kwargs):
        suscripcion = Suscripcion.objects.first()
        if not suscripcion:
            messages.error(request, 'No hay suscripcion activa.')
            return redirect('pagos:portal')

        fields = [
            'tipo_persona', 'razon_social', 'tipo_identificacion',
            'numero_identificacion', 'dv', 'email', 'telefono',
            'direccion', 'ciudad', 'departamento', 'regimen',
        ]
        data = {f: request.POST.get(f, '').strip() for f in fields}

        required = ['tipo_persona', 'razon_social', 'tipo_identificacion',
                     'numero_identificacion', 'email', 'telefono',
                     'direccion', 'ciudad', 'departamento']
        missing = [f for f in required if not data[f]]
        if missing:
            messages.error(request, 'Por favor complete todos los campos obligatorios.')
            return self.get(request, *args, **kwargs)

        if suscripcion.datos_facturacion:
            datos = suscripcion.datos_facturacion
            for key, val in data.items():
                setattr(datos, key, val)
            datos.save()
        else:
            datos = DatosFacturacion.objects.create(**data)
            suscripcion.datos_facturacion = datos
            suscripcion.save(update_fields=['datos_facturacion'])

        messages.success(request, 'Datos de facturacion guardados correctamente.')
        return redirect('pagos:portal')


class PagoPortalView(RolRequiredMixin, TemplateView):
    allowed_roles = (Rol.ADMINISTRADOR,)
    redirect_url = 'reports:dashboard'
    template_name = 'pagos/portal.html'

    def get(self, request, *args, **kwargs):
        tx_id = request.GET.get('id')
        if tx_id:
            self._procesar_transaccion_wompi(tx_id)
        return super().get(request, *args, **kwargs)

    def _procesar_transaccion_wompi(self, tx_id):
        if Pago.objects.filter(wompi_transaction_id=tx_id).exists():
            return

        try:
            tx = wompi.get_transaction(tx_id)
            status = tx.get('status')
            amount = tx.get('amount_in_cents', 0) / 100
            reference = tx.get('reference', '')

            suscripcion = Suscripcion.objects.first()
            if not suscripcion:
                return

            estado_map = {
                'APPROVED': 'APROBADO',
                'DECLINED': 'RECHAZADO',
                'ERROR': 'ERROR',
                'PENDING': 'PENDIENTE',
                'VOIDED': 'RECHAZADO',
            }

            n_meses = calcular_n_meses(amount, suscripcion.plan.precio) if suscripcion.plan else 1
            pago = Pago.objects.create(
                suscripcion=suscripcion,
                monto=amount,
                n_meses=n_meses,
                estado=estado_map.get(status, 'PENDIENTE'),
                wompi_transaction_id=tx_id,
                wompi_reference=reference,
                detalle_respuesta=tx,
            )

            if status == 'APPROVED':
                _avanzar_fecha_proximo_pago(pago)
                try:
                    alegra.generar_factura_desde_pago(pago)
                except Exception as e:
                    logger.error(f'Error generando factura Alegra: {e}')

            logger.info(f'Pago {pago.id} creado desde redirect WOMPI tx={tx_id} status={status}')
        except Exception as e:
            logger.error(f'Error procesando transaccion WOMPI {tx_id}: {e}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plan = PlanServicio.objects.filter(activo=True).first()
        suscripcion = Suscripcion.objects.select_related('plan', 'datos_facturacion').first()
        context['plan'] = plan
        context['suscripcion'] = suscripcion
        context['pagos_recientes'] = Pago.objects.all()[:5]
        context['wompi_public_key'] = settings.WOMPI_PUBLIC_KEY
        if plan:
            context['monto_centavos'] = int(plan.precio * 100)
        context['wompi_sandbox'] = getattr(settings, 'WOMPI_SANDBOX', True)
        context['datos_facturacion'] = (
            suscripcion.datos_facturacion if suscripcion and suscripcion.datos_facturacion_id else None
        )
        # Generate WOMPI integrity signature (unica por intento -- microsegundos,
        # no solo year+month, para que 2 intentos de pago en el mismo mes no
        # colisionen en la misma referencia y WOMPI rechace el segundo intento)
        prefix = getattr(settings, 'WOMPI_REFERENCE_PREFIX', 'APP')
        if plan and suscripcion:
            now = timezone.now()
            reference = f"{prefix}-{suscripcion.id}-{plan.id}-{now:%Y%m%d%H%M%S%f}"
            amount_cents = int(plan.precio * 100)
            currency = 'COP'
            integrity_key = settings.WOMPI_INTEGRITY_KEY
            concat = f"{reference}{amount_cents}{currency}{integrity_key}"
            context['wompi_signature'] = hashlib.sha256(concat.encode()).hexdigest()
            context['wompi_reference'] = reference
        return context


class HistorialPagosView(RolRequiredMixin, ListView):
    allowed_roles = (Rol.ADMINISTRADOR,)
    redirect_url = 'reports:dashboard'
    model = Pago
    template_name = 'pagos/historial.html'
    context_object_name = 'pagos'
    paginate_by = 20
    ordering = ['-created_at']


@method_decorator(csrf_exempt, name='dispatch')
class WompiWebhookView(View):
    """Endpoint publico -- SIN gate de rol/sesion. Autenticidad via firma
    HMAC WOMPI_EVENTS_KEY (verify_webhook_signature), no via login. WOMPI
    entrega este webhook servidor-a-servidor, sin cookie de sesion de
    ningun usuario del portal."""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
            event = body.get('event')
            signature_prop = body.get('signature', {}).get('checksum', '')

            if not wompi.verify_webhook_signature(body, signature_prop):
                logger.warning('WOMPI webhook: firma invalida')
                return JsonResponse({'status': 'invalid_signature'}, status=401)

            if event == 'transaction.updated':
                tx = body.get('data', {}).get('transaction', {})
                tx_id = tx.get('id')
                status = tx.get('status')
                amount = tx.get('amount_in_cents', 0) / 100
                reference = tx.get('reference', '')

                estado_map = {
                    'APPROVED': 'APROBADO',
                    'DECLINED': 'RECHAZADO',
                    'ERROR': 'ERROR',
                    'PENDING': 'PENDIENTE',
                    'VOIDED': 'RECHAZADO',
                }

                suscripcion_actual = Suscripcion.objects.select_related('plan').first()
                n_meses = (
                    calcular_n_meses(amount, suscripcion_actual.plan.precio)
                    if suscripcion_actual and suscripcion_actual.plan else 1
                )
                pago, created = Pago.objects.get_or_create(
                    wompi_transaction_id=tx_id,
                    defaults={
                        'suscripcion': suscripcion_actual,
                        'monto': amount,
                        'n_meses': n_meses,
                        'estado': 'PENDIENTE',
                        'wompi_reference': reference,
                    }
                )

                # Capturar el estado ANTES de sobreescribirlo: WOMPI puede
                # reintentar/duplicar la entrega del webhook para el MISMO
                # tx_id, y ademas puede solaparse con _procesar_transaccion_wompi
                # (redirect del navegador) -- si los efectos secundarios de
                # APPROVED corren 2 veces para el mismo pago, fecha_proximo_pago
                # avanzaria el doble de meses de lo realmente pagado.
                ya_estaba_aprobado = (not created) and (pago.estado == 'APROBADO')

                pago.estado = estado_map.get(status, 'PENDIENTE')
                pago.detalle_respuesta = tx
                pago.save()

                if status == 'APPROVED' and not ya_estaba_aprobado:
                    if pago.suscripcion:
                        _avanzar_fecha_proximo_pago(pago)
                    if not pago.alegra_invoice_id:
                        try:
                            alegra.generar_factura_desde_pago(pago)
                        except Exception as e:
                            logger.error(f'Error generando factura Alegra: {e}')

                logger.info(f'WOMPI webhook: tx={tx_id} status={status} created={created} ya_estaba_aprobado={ya_estaba_aprobado}')

            return JsonResponse({'status': 'ok'})
        except Exception as e:
            logger.error(f'WOMPI webhook error: {e}')
            return JsonResponse({'status': 'error'}, status=400)
