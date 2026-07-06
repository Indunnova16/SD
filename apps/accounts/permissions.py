"""
Utilidad de gating RBAC por rol — issue #58 (sub-item A4).

Unica fuente de verdad: `User.rol` (choices EJECUTOR/COORDINADOR/ADMINISTRADOR,
ver `apps.accounts.models.User.Rol`, sub-item A1). Los checks de permisos de
NEGOCIO nunca deben leer `job_profile` (metadata puramente descriptiva de la
ocupacion del usuario, decision de Miguel #2 del PLAN) ni `is_staff` (sigue
existiendo en el modelo solo para dar acceso a `/admin/` de Django — decision
del PLAN, seccion "Riesgos" — pero deja de ser arbitro de negocio desde este
modulo en adelante).

Expone:
- `Rol` — re-export de `User.Rol` para que las vistas no tengan que importar
  el modelo completo solo por el enum.
- `user_has_rol(user, *roles)` — helper booleano puro. Usalo para checks
  combinados (ej. ownership OR rol) o dentro de condicionales que no bloquean
  toda la vista (ej. mostrar u ocultar un bloque de contexto admin).
- `require_rol(*roles, ...)` — decorator para vistas basadas en funcion (FBV).
  Reemplaza el patron repetido `if not request.user.is_staff: messages.error
  + redirect` que existia en ~25 sitios de `accounts/views.py` y
  `courses/views.py`, y sus variantes (`user_passes_test(is_staff)`,
  `@staff_member_required`) en `certifications`, `preop_talks`,
  `lessons_learned`, `attendance`, `reports` y `gamification`. Tres modos
  (ver docstring de la funcion): mensaje+redirect (default, el mas comun),
  `json_only` (endpoints HTMX que SIEMPRE respondian JSON 403, sin mensaje
  ni redirect) y `raise_exception` (deja que Django resuelva el 403/permiso).
  Los pocos sitios con un helper local `_staff_required` que combinaba
  "HX-Request -> JSON, si no -> mensaje+redirect" quedan como funcion (no
  decorator) pero llamando a `user_has_rol` — no se fuerza esa forma en el
  decorator para no cambiar el comportamiento de los sitios que NUNCA
  chequeaban HX-Request.
- `RolRequiredMixin` — mixin para Class-Based Views genericas de Django (NO
  DRF). Ninguna vista migrada en el issue #58 es CBV hoy (confirmado: 0
  `class ...View` en accounts/courses/certifications/preop_talks/
  lessons_learned/attendance/reports/gamification — todas son FBV). Se expone
  para el proximo CBV que necesite el mismo gate, en vez de reinventar el
  chequeo ad-hoc. Los ViewSets DRF (ej. `NotificationTemplateViewSet`,
  sub-item A10) NO usan este mixin — necesitan una `permission_classes` de
  DRF construida sobre `user_has_rol`, que es lo que consume A10.

IMPORTANTE para quien construya el siguiente gate (A5-A10): llamar SIEMPRE a
`user_has_rol` o `require_rol` de este modulo. No repetir
`request.user.rol == "ADMINISTRADOR"` inline — si el set de roles admitidos
cambia (ej. se agrega un 4to rol en el futuro) hay un solo lugar que tocar.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

User = get_user_model()
Rol = User.Rol


def user_has_rol(user, *roles):
    """
    True si `user` esta autenticado y su `rol` esta en `roles`.

    Lee EXCLUSIVAMENTE `user.rol` — nunca `job_profile` ni `is_staff` (issue
    #58, decision #2: `rol` es la unica fuente de verdad para gating de
    negocio). Usuarios anonimos o con `rol=None` (pendiente de asignacion
    tras el backfill de A1 — bucket sin sugerencia confiable de
    `job_profile`) devuelven False: sin rol asignado explicitamente, no hay
    permisos elevados.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    rol = getattr(user, "rol", None)
    return rol is not None and rol in roles


def require_rol(
    *roles,
    redirect_url=None,
    message=None,
    json_only=False,
    raise_exception=False,
):
    """
    Decorator para FBV: bloquea la vista si `request.user.rol` no esta en
    `roles`. Tres modos, elegidos EXPLICITAMENTE por call site para no
    cambiar el comportamiento pre-existente de cada vista migrada:

    - Default (`redirect_url=...`): `messages.error(message)` +
      `redirect(redirect_url)`. Es el patron mas comun en el repo (todas las
      vistas de `accounts/views.py` y la mayoria de `courses/views.py`).
    - `json_only=True`: SIEMPRE `JsonResponse({"error": "No autorizado"},
      status=403)`, sin mensaje ni redirect — para endpoints HTMX puros que
      ya respondian solo JSON (ej. `course_toggle_status`,
      `profile_type_toggle_active`).
    - `raise_exception=True`: `django.core.exceptions.PermissionDenied` (para
      vistas sin un target de redirect razonable, ej. algunas de A10).

    `redirect_url` es OBLIGATORIO en el modo default — no existe un target
    sano compartido entre apps (accounts usa "accounts:dashboard", courses
    usa "courses:list", gamification usa "gamification:dashboard", etc).
    Pasarlo explicito por call site evita adivinar mal el destino.

    NO detecta `HX-Request` automaticamente: los sitios migrados que SI
    distinguian HTMX (ej. el helper local `_staff_required` de
    `courses/views.py`) se dejaron como funcion propia que llama a
    `user_has_rol` en vez de forzarlos por este decorator, precisamente para
    no alterar el comportamiento de los sitios que nunca hicieron esa
    distincion.

    Se aplica DEBAJO de los decorators de metodo HTTP
    (`@require_GET`/`@require_POST`/`@require_http_methods`) para preservar
    el orden de chequeo original: primero metodo, despues rol, despues body.
    """
    if not json_only and not raise_exception and not redirect_url:
        raise ValueError(
            "require_rol necesita redirect_url (o json_only=True / raise_exception=True)"
        )

    default_message = message or "No tiene permisos para acceder a esta página."

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not user_has_rol(request.user, *roles):
                if json_only:
                    return JsonResponse({"error": "No autorizado"}, status=403)
                if raise_exception:
                    raise PermissionDenied(default_message)
                messages.error(request, default_message)
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


class RolRequiredMixin:
    """
    Mixin para Class-Based Views genericas de Django (NO DRF) que requieren
    un `rol` minimo. Ver docstring del modulo — no usado por ninguna vista
    migrada en el issue #58 (todas son FBV hoy), expuesto para consistencia
    futura: el proximo CBV debe heredar de esto en vez de reimplementar el
    chequeo.

    Uso:
        class AlgunaVistaAdmin(RolRequiredMixin, ListView):
            allowed_roles = (Rol.ADMINISTRADOR,)
            redirect_url = "accounts:dashboard"
    """

    allowed_roles = ()
    redirect_url = None
    permission_denied_message = "No tiene permisos para acceder a esta página."

    def dispatch(self, request, *args, **kwargs):
        if not user_has_rol(request.user, *self.allowed_roles):
            if self.redirect_url:
                messages.error(request, self.permission_denied_message)
                return redirect(self.redirect_url)
            raise PermissionDenied(self.permission_denied_message)
        return super().dispatch(request, *args, **kwargs)
