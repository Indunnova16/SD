"""Unit tests para `apps.notifications.api.permissions.IsAdministrador` (SD#58, A10).

Aislado de la integración vía ViewSet (cubierta en `test_api.py`,
`TestNotificationTemplate*`) — acá se prueba el permission class directo con
un `RequestFactory` sintético, igual que A4 hizo para `require_rol`/
`user_has_rol` en `apps/accounts/tests/test_issue_58_a4.py`.
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.permissions import Rol
from apps.notifications.api.permissions import IsAdministrador

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a10_notif_perm_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A10",
        "document_type": "CC",
        "document_number": f"73{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class IsAdministradorPermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.permission = IsAdministrador()

    def _request(self, user):
        request = self.factory.get("/api/notifications/templates/")
        request.user = user
        return request

    def test_administrador_tiene_permiso(self):
        user = _make_user(rol=Rol.ADMINISTRADOR)
        self.assertTrue(self.permission.has_permission(self._request(user), view=None))

    def test_ejecutor_no_tiene_permiso(self):
        user = _make_user(rol=Rol.EJECUTOR)
        self.assertFalse(self.permission.has_permission(self._request(user), view=None))

    def test_coordinador_no_tiene_permiso(self):
        """El CRUD de plantillas es Administrador-only — Coordinador NO alcanza."""
        user = _make_user(rol=Rol.COORDINADOR)
        self.assertFalse(self.permission.has_permission(self._request(user), view=None))

    def test_rol_none_no_tiene_permiso(self):
        """Bucket 'sin asignar' del backfill de A1 -> sin acceso, no default adivinado."""
        user = _make_user(rol=None)
        self.assertFalse(self.permission.has_permission(self._request(user), view=None))

    def test_is_staff_solo_sin_rol_no_alcanza(self):
        """Regresión central del issue #58: is_staff=True sin rol=ADMINISTRADOR
        NO otorga acceso (rol es la única fuente de verdad, decisión #2 del PLAN)."""
        user = _make_user(rol=None, is_staff=True, is_superuser=True)
        self.assertFalse(self.permission.has_permission(self._request(user), view=None))

    def test_usuario_anonimo_no_tiene_permiso(self):
        self.assertFalse(
            self.permission.has_permission(self._request(AnonymousUser()), view=None)
        )
