"""Tests for issue #58 sub-item A8 — Filtrado de datos: Operaciones.

Gatea el LISTADO administrativo de `preop_talks` (`talk_list`/`talks_table`),
`lessons_learned` (`lesson_list`/`lesson_grid`) y `attendance`
(`face_event_list`) para Ejecutor (403 explícito, `require_rol(...,
raise_exception=True)`), dejando el listado completo visible para
Coordinador/Administrador — ocultamiento BINARIO (PLAN A8: "oculto para
Ejecutor, completo para Coordinador/Admin", a diferencia de A6/A7 que son
propio/equipo/todos).

`talks_table`/`lesson_grid` reciben el MISMO gate que `talk_list`/`lesson_list`
aunque el PLAN solo nombra estos últimos explícitamente: son la MISMA data
servida por una URL propia (usada internamente vía HX-Request) — dejarlas sin
gate sería un hueco visible (un Ejecutor podría pegarle directo a esa URL y
ver igual el listado completo). Scope ampliado dentro de A8, ver
`notas_para_orquestador` del sub-item.

Cubre además la regresión anti-romper-flujo-diario del propio PLAN: el
Ejecutor debe seguir con 200/302-hacia-éxito en las vistas donde participa de
SU PROPIA charla/asistencia (`talk_conduct`, `start_talk`, `complete_talk`,
`sign_attendance`) — esas NO llevan el gate nuevo, A8 no las toca.
"""

import itertools
from datetime import date, datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol
from apps.lessons_learned.models import Category as LessonCategory
from apps.lessons_learned.models import LessonLearned
from apps.preop_talks.models import PreopTalk, TalkAttendee

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a8_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A8",
        "document_type": "CC",
        "document_number": f"71{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class OperacionesListadoAdministrativoTests(TestCase):
    """`preop_talks:list`/`table`, `lessons_learned:list`/`grid`,
    `attendance:face_event_list` — 403 para Ejecutor, 200 para
    Coordinador/Administrador (PLAN A8)."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)

    # --- preop_talks:list / preop_talks:table ---------------------------

    def test_preop_talks_list_ejecutor_bloqueado_403(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 403)

    def test_preop_talks_list_htmx_ejecutor_bloqueado_403(self):
        """`talk_list` delega a `talks_table` internamente cuando la request
        es HX-Request — el gate debe cubrir también ese camino."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 403)

    def test_preop_talks_table_ejecutor_bloqueado_403(self):
        """`table/` tiene su propia URL además de ser invocada por `talk_list`
        — sin gate propio, un Ejecutor vería el listado completo igual
        pegándole directo a esta URL (hueco visible, scope ampliado en A8)."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("preop_talks:table"))
        self.assertEqual(response.status_code, 403)

    def test_preop_talks_list_coordinador_ok(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)

    def test_preop_talks_table_coordinador_ok(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("preop_talks:table"))
        self.assertEqual(response.status_code, 200)

    def test_preop_talks_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("preop_talks:list"))
        self.assertEqual(response.status_code, 200)

    # --- lessons_learned:list / lessons_learned:grid --------------------

    def test_lessons_learned_list_ejecutor_bloqueado_403(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("lessons_learned:list"))
        self.assertEqual(response.status_code, 403)

    def test_lessons_learned_list_htmx_ejecutor_bloqueado_403(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("lessons_learned:list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 403)

    def test_lessons_learned_grid_ejecutor_bloqueado_403(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("lessons_learned:grid"))
        self.assertEqual(response.status_code, 403)

    def test_lessons_learned_list_coordinador_ok(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("lessons_learned:list"))
        self.assertEqual(response.status_code, 200)

    def test_lessons_learned_grid_coordinador_ok(self):
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("lessons_learned:grid"))
        self.assertEqual(response.status_code, 200)

    def test_lessons_learned_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("lessons_learned:list"))
        self.assertEqual(response.status_code, 200)

    # --- attendance:face_event_list --------------------------------------

    def test_attendance_face_event_list_ejecutor_bloqueado_403(self):
        """Cambia de 302 (A4: `_staff_required`/`user_passes_test`) a 403
        (A8: `require_rol(..., raise_exception=True)`) — ver actualización
        del test homónimo en `test_issue_58_a4.py`."""
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("attendance:face_event_list"))
        self.assertEqual(response.status_code, 403)

    def test_attendance_face_event_list_coordinador_ok(self):
        """A8 amplía el acceso a COORDINADOR (antes ADMINISTRADOR-only vía
        `_staff_required`, straight-swap de A4) — es la corrección real de
        este sub-item para el módulo Operaciones."""
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("attendance:face_event_list"))
        self.assertEqual(response.status_code, 200)

    def test_attendance_face_event_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("attendance:face_event_list"))
        self.assertEqual(response.status_code, 200)

    def test_attendance_face_event_list_anonimo_redirige_login_no_403(self):
        """Anónimo: `login_required` sigue redirigiendo (302) — el 403 nuevo
        es SOLO para autenticado-con-rol-incorrecto, no para no-autenticado."""
        response = self.client.get(reverse("attendance:face_event_list"))
        self.assertEqual(response.status_code, 302)

    # --- attendance: mobile_face_qr / reindex_user_face SIN cambio -------

    def test_attendance_mobile_face_qr_coordinador_sigue_bloqueado(self):
        """Fuera del alcance de A8 (el PLAN solo pide ampliar el LISTADO,
        `face_event_list`) — sigue ADMINISTRADOR-only vía `_staff_required`,
        sin cambio. Regresión: A8 NO debe ampliar esto por accidente."""
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("attendance:mobile_face_qr"))
        self.assertEqual(response.status_code, 302)

    def test_attendance_mobile_face_qr_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("attendance:mobile_face_qr"))
        self.assertEqual(response.status_code, 200)


class OperacionesPropiaParticipacionRegresionTests(TestCase):
    """Regresión anti-romper-flujo-diario (PLAN A8): el Ejecutor sigue
    accediendo a las vistas donde participa de SU PROPIA charla/asistencia
    pese a que el listado administrativo (arriba) ahora le da 403. Ninguna
    de estas vistas fue tocada por A8."""

    def setUp(self):
        self.client = Client()
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.talk = PreopTalk.objects.create(
            title="Charla A8",
            content="contenido",
            project_name="Proyecto A8",
            location="Sitio A8",
            work_activity="Actividad A8",
            scheduled_at=datetime(2024, 1, 1, 8, 0, tzinfo=dt_timezone.utc),
            conducted_by=self.ejecutor,
        )

    def test_talk_conduct_ejecutor_dueno_ok(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse("preop_talks:conduct", kwargs={"talk_id": self.talk.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_start_talk_ejecutor_dueno_no_bloqueado(self):
        """POST de acción — éxito real = redirect a `conduct` (nunca 403)."""
        self.client.force_login(self.ejecutor)
        response = self.client.post(
            reverse("preop_talks:start", kwargs={"talk_id": self.talk.id}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.status_code, 403)

    def test_complete_talk_ejecutor_dueno_no_bloqueado(self):
        # complete_talk exige status IN_PROGRESS (PreopTalkService.complete_talk);
        # el default de fixture es SCHEDULED — avanzamos el estado primero para
        # aislar la regresión de PERMISOS (lo que prueba A8) de la máquina de
        # estados del dominio (no relacionada con RBAC).
        self.talk.status = PreopTalk.Status.IN_PROGRESS
        self.talk.save()
        self.client.force_login(self.ejecutor)
        response = self.client.post(
            reverse("preop_talks:complete", kwargs={"talk_id": self.talk.id}),
            {"notes": "sin novedad"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_attendees_list_ejecutor_ok(self):
        """`sign_attendance` (la vista de firma en sí) no se puede probar
        end-to-end hoy: descubrí al escribir este test que
        `TalkAttendeeService` no expone `sign_attendance`/`add_attendee`/
        `remove_attendee` (los nombres que llaman `preop_talks/views.py` en
        esas 3 funciones) — solo `capture_signature`/`register_attendee`/
        `verify_attendance`. Es un bug PRE-EXISTENTE de integración
        vista↔servicio, 100% ajeno a RBAC (rompe para CUALQUIER rol, no solo
        Ejecutor) y fuera de `archivos_a_tocar` de A8 (no toca
        `apps/preop_talks/services.py`) — lo reporto en
        `notas_para_orquestador`, no lo arreglo acá (root-cause distinto,
        no shotgun fix). En su lugar pruebo `attendees_list` (GET, sin ese
        problema) como regresión equivalente de "el Ejecutor sigue viendo la
        asistencia de SU propia charla"."""
        TalkAttendee.objects.create(talk=self.talk, user=self.ejecutor)
        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse("preop_talks:attendees", kwargs={"talk_id": self.talk.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_lesson_edit_propio_ejecutor_sigue_ok(self):
        """`lessons_learned` no tiene un análogo de 'propia charla', pero la
        regresión equivalente es que crear/editar la PROPIA lección (ya
        cubierto por A4, ownership bypass) sigue intacto — A8 no toca
        `lesson_edit`/`lesson_create`, solo `lesson_list`/`lesson_grid`."""
        category = LessonCategory.objects.create(name="Cat A8")
        lesson = LessonLearned.objects.create(
            title="Leccion A8",
            description="desc",
            category=category,
            situation="situacion",
            lesson="leccion",
            recommendations="recomendaciones",
            created_by=self.ejecutor,
        )
        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse("lessons_learned:edit", kwargs={"lesson_id": lesson.id})
        )
        self.assertEqual(response.status_code, 200)
