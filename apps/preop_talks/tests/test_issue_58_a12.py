"""Tests for issue #58 sub-item A12-fix — talk_list ya NO gatea la página completa.

Hallazgo de INTEGRACIÓN de A11 (regresión E2E prep): A8 gateó `talk_list`
completo con `@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR,
raise_exception=True)` (403 para Ejecutor). El problema: `talk_list.html` es
la página que aloja el widget `today_talks` — la ÚNICA forma de la UI (vía
navbar → `preop_talks:list`, no hay link directo a `preop_talks:today`) para
que un Ejecutor llegue a firmar SU charla pre-operacional del día. Con el 403
de página completa, el Ejecutor perdía su flujo diario real.

Fix (A12-fix, revierte PARCIALMENTE A8 — ver `test_issue_58_a8.py` donde se
actualiza el test homónimo que quedó obsoleto): `talk_list` vuelve a ser
accesible a cualquier usuario autenticado. El gate se mueve a nivel de
CONTENIDO vía `can_manage` en el contexto (patrón propio/equipo/todos de
A6/A7/A9): el widget `today_talks` (propio) SIEMPRE visible; la
gestión/historial completo (todos) solo si `can_manage`. `talks_table` — el
endpoint HTMX de la tabla paginada completa, dato puramente administrativo —
SIGUE gateado tal cual, sin cambio.
"""

import itertools
from datetime import date, datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol
from apps.preop_talks.models import PreopTalk

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a12_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A12",
        "document_type": "CC",
        "document_number": f"72{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class TalkListAccesoEjecutorTests(TestCase):
    """`preop_talks:list` (A12-fix): 200 para CUALQUIER rol autenticado,
    contenido escalonado por `can_manage`."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        # Dato legacy: charla que ya existía en BD antes del fix, conducida
        # por el propio Ejecutor — su flujo diario real depende de que
        # `today_talks` siga sirviendo esto sin romperse tras el cambio.
        self.charla_legacy = PreopTalk.objects.create(
            title="Charla legacy A12",
            content="contenido legacy",
            project_name="Proyecto legacy",
            location="Sitio legacy",
            work_activity="Actividad legacy",
            scheduled_at=datetime(2024, 1, 1, 8, 0, tzinfo=dt_timezone.utc),
            conducted_by=self.ejecutor,
        )

    # --- Ejecutor: 200, ve today_talks, NO ve gestión --------------------

    def test_talk_list_ejecutor_ya_no_da_403(self):
        """Regresión del hallazgo A11: antes de A12-fix esto era 403 y le
        rompía el flujo diario de firma de charla al Ejecutor."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)

    def test_talk_list_ejecutor_ve_widget_today_talks(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Charlas de Hoy")
        self.assertContains(response, reverse("preop_talks:today"))

    def test_talk_list_ejecutor_no_ve_historial_gestion(self):
        """`can_manage=False` → el bloque de Historial/Filtros (dato
        administrativo) no debe estar en el HTML servido al Ejecutor."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Historial de Charlas")
        self.assertNotContains(response, "Nueva Charla")
        self.assertFalse(response.context["can_manage"])

    # --- Coordinador/Administrador: 200, ven todo ------------------------

    def test_talk_list_coordinador_ve_todo(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial de Charlas")
        self.assertContains(response, "Nueva Charla")
        self.assertTrue(response.context["can_manage"])

    def test_talk_list_administrador_ve_todo(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial de Charlas")
        self.assertContains(response, "Nueva Charla")
        self.assertTrue(response.context["can_manage"])

    def test_talk_list_anonimo_sigue_redirigiendo_login(self):
        """`login_required` sin cambio — el fix NO abre la vista a anónimos,
        solo a cualquier usuario AUTENTICADO."""
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 302)


class TalkListRegresionesTests(TestCase):
    """Regresiones explícitas exigidas por A12-fix: `talks_table` sigue
    gateado, `today_talks` (la vista) sigue sin gate."""

    def setUp(self):
        self.client = Client()
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)

    def test_talks_table_ejecutor_sigue_403(self):
        """`talks_table` (endpoint HTMX de la tabla paginada completa) NO
        se toca en A12-fix — sigue siendo dato puramente administrativo."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:table"))
        self.assertEqual(response.status_code, 403)

    def test_talk_list_htmx_ejecutor_sigue_403(self):
        """`talk_list` delega a `talks_table` internamente cuando la
        request es HX-Request — sigue heredando su gate, sin cambio."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 403)

    def test_talks_table_coordinador_ok(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("preop_talks:table"))
        self.assertEqual(response.status_code, 200)

    def test_today_talks_ejecutor_sigue_sin_gate(self):
        """`today_talks` (la vista en sí, no la página que la aloja) nunca
        tuvo `require_rol` — A12-fix no le agrega ninguno; sigue accesible a
        cualquier autenticado, es el corazón del flujo diario del Ejecutor."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:today"))
        self.assertEqual(response.status_code, 200)

    def test_today_talks_coordinador_sigue_sin_gate(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("preop_talks:today"))
        self.assertEqual(response.status_code, 200)
