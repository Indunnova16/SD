"""Tests de regresión para la bandeja personal de notificaciones (SD#58, A10).

`apps/notifications/views.py` (`notification_list` y las otras 5 vistas: `notification_items`,
`mark_read`, `mark_all_read`, `unread_count`, `preferences`) es la bandeja personal —
100% filtrada por `request.user` — y quedó explícitamente FUERA del alcance de A10
(decisión #4 del PLAN: el lockdown Administrador aplica solo a superficies
"Sistema"/config admin, nunca a la bandeja personal). No existía ningún test de
regresión para estas vistas antes de A10; se agrega acá para dejar constancia de
que `notifications:list` sigue siendo accesible a CUALQUIER rol autenticado
(incluido `rol=None`, el bucket "sin asignar" del backfill de A1) — nada en A10
lo tocó, pero es exactamente la superficie que el PLAN pide verificar como
regresión.
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a10_notif_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A10",
        "document_type": "CC",
        "document_number": f"72{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class NotificationsPersonalViewsRegressionTests(TestCase):
    """Regresión: la bandeja personal (fuera de alcance de A10) sigue 200
    para cualquier rol autenticado."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.sin_rol = _make_user(rol=None)

    def test_notifications_list_cualquier_rol_ok(self):
        for user in (self.administrador, self.coordinador, self.ejecutor, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse("notifications:list"))
                self.assertEqual(response.status_code, 200)

    def test_notifications_unread_count_cualquier_rol_ok(self):
        for user in (self.administrador, self.coordinador, self.ejecutor, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse("notifications:unread-count"))
                self.assertEqual(response.status_code, 200)

    def test_notifications_preferences_cualquier_rol_ok(self):
        for user in (self.administrador, self.coordinador, self.ejecutor, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse("notifications:preferences"))
                self.assertEqual(response.status_code, 200)

    def test_notifications_list_anonimo_redirige_a_login(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
