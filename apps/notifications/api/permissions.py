"""
Permisos DRF custom para la API de notifications — issue #58 (sub-item A10).

`NotificationTemplateViewSet` gestiona `NotificationTemplate` (config de
plantillas de notificación) — es superficie "Sistema" (admin-only), NO la
bandeja personal (`apps/notifications/views.py`, 100% filtrada por
`request.user`, fuera de alcance de A10). Hoy usaba
`permission_classes = [permissions.IsAuthenticated]` — **gap real de
seguridad**: cualquier usuario autenticado podía crear/editar/borrar
plantillas de notificación vía API (sin UI que la enlace hoy, pero
alcanzable directamente). Este módulo cierra ese gap reusando la única
fuente de verdad de rol (`apps.accounts.permissions.user_has_rol`, sub-item
A4/A1) — nunca `is_staff` ni `job_profile`, igual que el resto del gating
RBAC del issue #58.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.permissions import Rol, user_has_rol


class IsAdministrador(BasePermission):
    """
    Permite el request solo si `request.user.rol == Rol.ADMINISTRADOR`.

    `has_permission` (permiso a nivel de vista, no de objeto) es suficiente
    acá: las plantillas de notificación no tienen dueño individual, así que
    TODAS las acciones del ViewSet (list/create/retrieve/update/partial_update
    /destroy) deben quedar detrás del mismo gate — no hay bypass de
    ownership que evaluar en `has_object_permission`.
    """

    message = "No tiene permisos para gestionar plantillas de notificación."

    def has_permission(self, request, view):
        return user_has_rol(request.user, Rol.ADMINISTRADOR)
