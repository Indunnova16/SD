"""Context processor global -- expone `alerta_pago_vencido` al layout base
para el banner de aviso de pago vencido (issue #90).

Gateado a rol ADMINISTRADOR: mismo publico que ya ve el link "Portal de
Pagos" en el navbar (issue #85 A3, `apps.accounts.permissions.Rol`) -- no
tiene sentido exponer el estado de facturacion a EJECUTOR/COORDINADOR, que
ni siquiera pueden entrar al portal de pagos.

Single-tenant: igual que `pagos/views.py` (`Suscripcion.objects.first()`),
este repo modela una unica suscripcion por instancia de la app.
"""

from apps.accounts.permissions import Rol, user_has_rol

from .models import Suscripcion


def alertas_pago(request):
    user = getattr(request, "user", None)
    if not user_has_rol(user, Rol.ADMINISTRADOR):
        return {"alerta_pago_vencido": False}

    suscripcion = Suscripcion.objects.first()
    if not suscripcion:
        return {"alerta_pago_vencido": False}

    return {"alerta_pago_vencido": suscripcion.alerta_pago_vencido}
