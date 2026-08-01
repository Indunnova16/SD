"""
Tests para SD#73 -- Programación de cursos (convocatoria a grupo de personas).

Cada bloque de tests mapea a una fila de la tabla de entregables de
`SPRINTS/PLAN_2026-07-28_73_programacion_cursos.md`, que es la lista contra la
que se cierra el issue.

Decisiones cubiertas explícitamente por tests, porque son las que el cliente
puede rebotar:
  - La fecha de finalización es SUGERIDA y NO bloquea: nunca se escribe en
    `Enrollment.due_date` (ese campo dispara el vencimiento duro de
    `tasks.check_enrollment_deadlines` -> `EXPIRED` -> "Habilitar de nuevo").
  - El reporte de asistencia se filtra POR programación: dos convocatorias del
    mismo curso no se mezclan.
  - Reasignar el responsable cambia la firma que sale en el PDF.
  - Convocar a alguien ya inscrito reusa su `Enrollment` sin resetear progreso.
  - Vive DENTRO de la sección de Asistencia, sin entradas nuevas en el navbar
    (comentario del cliente, que manda sobre el body).
"""

from datetime import date, datetime, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.forms import CourseScheduleForm
from apps.courses.models import (
    Category,
    Course,
    CourseSchedule,
    Enrollment,
    JobProfileType,
    Module,
    ScheduleAssignment,
)
from apps.courses.services import CourseScheduleService
from apps.notifications.models import Notification

# Mismo fixture PNG mínimo que usan test_issue_63.py / test_attendance_pdf.py.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)

_SEQ = [7300]


def _png_file(name="sig.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


def _make_user(rol=None, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue73_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "SD73",
        "document_number": f"8{n:08d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
        "is_active": True,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat SD73 {n}", slug=f"cat-sd73-{n}", description="c", color="#3B82F6"
    )
    defaults = {
        "code": f"ISSUE73-{n}",
        "title": f"Curso SD73 {n}",
        "description": "desc",
        "objectives": "obj",
        "course_type": Course.Type.MANDATORY,
        "status": Course.Status.PUBLISHED,
        "category": category,
        "created_by": creator,
        # Campos que el gate de SD#63 exige para poder exportar el PDF.
        "project_name": "Proyecto SD73",
        "activity_type": Course.ActivityType.CAPACITACION,
    }
    defaults.update(overrides)
    course = Course.objects.create(**defaults)
    Module.objects.create(course=course, title="M1", description="d", order=0)
    return course


def _make_schedule(course, creator, **overrides):
    _SEQ[0] += 1
    defaults = {
        "course": course,
        "name": f"Turno {_SEQ[0]}",
        "created_by": creator,
    }
    defaults.update(overrides)
    return CourseSchedule.objects.create(**defaults)


# =============================================================================
# Entregables 1, 2, 24 -- Modelo de la Programación (aditivo, curso intacto)
# =============================================================================


class CourseScheduleModelTests(TestCase):
    def setUp(self):
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.course = _make_course(self.admin)

    def test_schedule_se_crea_sobre_curso_existente_sin_modificarlo(self):
        """Entregable 1: la programación no toca el curso."""
        before = Course.objects.get(pk=self.course.pk)
        schedule = _make_schedule(self.course, self.admin, name="Turno X")

        after = Course.objects.get(pk=self.course.pk)
        self.assertEqual(schedule.course_id, self.course.id)
        self.assertEqual(after.title, before.title)
        self.assertEqual(after.updated_at, before.updated_at)

    def test_schedule_tiene_nombre_propio_de_convocatoria(self):
        """Entregable 2: 'Turno X' es el nombre de la convocatoria."""
        schedule = _make_schedule(self.course, self.admin, name="Turno X")
        self.assertEqual(schedule.name, "Turno X")
        self.assertIn("Turno X", str(schedule))

    def test_is_overdue_es_informativo(self):
        """Entregable 23: estado derivado, no una máquina de estados."""
        vencida = _make_schedule(
            self.course, self.admin, suggested_end_date=date.today() - timedelta(days=1)
        )
        futura = _make_schedule(
            self.course, self.admin, suggested_end_date=date.today() + timedelta(days=5)
        )
        sin_fecha = _make_schedule(self.course, self.admin)

        self.assertTrue(vencida.is_overdue)
        self.assertFalse(futura.is_overdue)
        self.assertFalse(sin_fecha.is_overdue)

    def test_responsable_signature_url_vacia_si_no_hay_firma(self):
        responsable = _make_user()
        schedule = _make_schedule(self.course, self.admin, responsable=responsable)
        self.assertEqual(schedule.responsable_signature_url, "")

    def test_misma_persona_en_dos_programaciones_del_mismo_curso(self):
        """Entregable 20: permitido; un solo Enrollment respalda ambas."""
        persona = _make_user()
        s1 = _make_schedule(self.course, self.admin)
        s2 = _make_schedule(self.course, self.admin)

        audience = {persona.id: ScheduleAssignment.Source.USER}
        CourseScheduleService.convocar(s1, audience)
        CourseScheduleService.convocar(s2, audience)

        self.assertEqual(ScheduleAssignment.objects.filter(user=persona).count(), 2)
        self.assertEqual(
            Enrollment.objects.filter(user=persona, course=self.course).count(), 1
        )


# =============================================================================
# Entregables 3, 4, 5 -- Resolución de audiencia (persona / perfil / cargo)
# =============================================================================


class ResolveAudienceTests(TestCase):
    def setUp(self):
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.course = _make_course(self.admin)
        self.perfil = JobProfileType.objects.create(
            code=f"SD73PERF{_SEQ[0]}", name="Liniero SD73", order=99
        )

    def test_convoca_persona_especifica(self):
        """Entregable 3."""
        persona = _make_user()
        otra = _make_user()
        audience = CourseScheduleService.resolve_audience(users=[persona])

        self.assertEqual(audience, {persona.id: ScheduleAssignment.Source.USER})
        self.assertNotIn(otra.id, audience)

    def test_convoca_por_perfil_ocupacional(self):
        """Entregable 4: todos los que tengan ese perfil."""
        a = _make_user(job_profile=self.perfil)
        b = _make_user(job_profile=self.perfil)
        fuera = _make_user()

        audience = CourseScheduleService.resolve_audience(job_profiles=[self.perfil])

        self.assertEqual(set(audience), {a.id, b.id})
        self.assertNotIn(fuera.id, audience)
        self.assertEqual(audience[a.id], ScheduleAssignment.Source.PROFILE)

    def test_convoca_por_cargo(self):
        """Entregable 5: todos los que tengan ese cargo (job_position)."""
        a = _make_user(job_position="Soldador SD73")
        b = _make_user(job_position="Soldador SD73")
        fuera = _make_user(job_position="Otro SD73")

        audience = CourseScheduleService.resolve_audience(job_positions=["Soldador SD73"])

        self.assertEqual(set(audience), {a.id, b.id})
        self.assertNotIn(fuera.id, audience)
        self.assertEqual(audience[a.id], ScheduleAssignment.Source.POSITION)

    def test_no_convoca_usuarios_inactivos(self):
        _make_user(job_position="Cargo Inactivo SD73", is_active=False)
        audience = CourseScheduleService.resolve_audience(
            job_positions=["Cargo Inactivo SD73"]
        )
        self.assertEqual(audience, {})

    def test_dedup_y_precedencia_persona_sobre_perfil_y_cargo(self):
        """Si entra por varias vías, se convoca UNA vez y gana la más específica."""
        persona = _make_user(job_profile=self.perfil, job_position="Cargo Dual SD73")

        audience = CourseScheduleService.resolve_audience(
            users=[persona],
            job_profiles=[self.perfil],
            job_positions=["Cargo Dual SD73"],
        )

        self.assertEqual(len(audience), 1)
        self.assertEqual(audience[persona.id], ScheduleAssignment.Source.USER)


# =============================================================================
# Entregables 8, 9, 18, 19 -- Convocatoria: fecha no bloqueante, aviso, reuso
# =============================================================================


class ConvocarTests(TestCase):
    def setUp(self):
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.course = _make_course(self.admin)

    def test_convocar_crea_assignment_y_enrollment(self):
        persona = _make_user()
        schedule = _make_schedule(self.course, self.admin)

        result = CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        self.assertEqual(len(result["convocados"]), 1)
        assignment = result["convocados"][0]
        self.assertEqual(assignment.user_id, persona.id)
        self.assertIsNotNone(assignment.enrollment)
        self.assertTrue(
            Enrollment.objects.filter(user=persona, course=self.course).exists()
        )

    def test_fecha_sugerida_no_se_escribe_en_enrollment_due_date(self):
        """Entregable 8 -- EL requisito que no se puede romper.

        `Enrollment.due_date` es un límite DURO: `check_enrollment_deadlines`
        marca `EXPIRED` todo enrollment vencido y el alumno queda obligado a
        "Habilitar de nuevo" con 5 días menos. El cliente pidió lo contrario.
        """
        persona = _make_user()
        schedule = _make_schedule(
            self.course, self.admin, suggested_end_date=date.today() + timedelta(days=10)
        )

        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        enrollment = Enrollment.objects.get(user=persona, course=self.course)
        self.assertIsNone(enrollment.due_date)

    def test_fecha_sugerida_vencida_no_expira_ni_bloquea(self):
        """Entregable 8: pasada la fecha, el convocado sigue pudiendo hacerlo."""
        from apps.courses.tasks import check_enrollment_deadlines

        persona = _make_user()
        schedule = _make_schedule(
            self.course, self.admin, suggested_end_date=date.today() - timedelta(days=30)
        )
        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        check_enrollment_deadlines()

        enrollment = Enrollment.objects.get(user=persona, course=self.course)
        self.assertNotEqual(enrollment.status, Enrollment.Status.EXPIRED)
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)
        self.assertTrue(schedule.is_overdue)  # informativo, no bloqueante

    def test_notifica_al_convocado_con_curso_y_fecha(self):
        """Entregable 9: 'se le asignó este curso y tiene hasta tal fecha'."""
        persona = _make_user()
        schedule = _make_schedule(
            self.course,
            self.admin,
            name="Turno X",
            suggested_end_date=date(2026, 12, 31),
        )

        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        notif = Notification.objects.filter(user=persona).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.course.title, notif.subject)
        self.assertIn("Turno X", notif.body)
        self.assertIn("31/12/2026", notif.body)
        # Debe leerse como sugerencia, no como bloqueo.
        self.assertIn("no se bloquea", notif.body)

    def test_notifica_al_convocado_incluye_action_url_y_text(self):
        """Punto 5 -- `notify_assignment` debe pasar `action_url`/`action_text`
        a `NotificationService.create_notification` (que ya los soporta pero
        no se estaban usando, wiring faltante confirmado por F2)."""
        persona = _make_user()
        schedule = _make_schedule(self.course, self.admin, name="Turno X")

        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        notif = Notification.objects.get(user=persona)
        self.assertEqual(
            notif.action_url, reverse("courses:detail", args=[self.course.id])
        )
        self.assertEqual(notif.action_text, "Ir al curso")

    def test_persona_ya_inscrita_reusa_enrollment_sin_resetear_progreso(self):
        """Entregable 18: no duplica, no borra avance, no re-expira."""
        persona = _make_user()
        enrollment = Enrollment.objects.create(
            user=persona,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            progress=55,
            started_at=timezone.now(),
        )
        schedule = _make_schedule(self.course, self.admin)

        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        enrollment.refresh_from_db()
        self.assertEqual(
            Enrollment.objects.filter(user=persona, course=self.course).count(), 1
        )
        self.assertEqual(enrollment.status, Enrollment.Status.IN_PROGRESS)
        self.assertEqual(int(enrollment.progress), 55)
        self.assertIsNotNone(enrollment.started_at)

    def test_enrollment_expirado_no_se_resetea_al_convocar(self):
        """No se usa `EnrollmentService.enroll_user`, que borraría el avance."""
        persona = _make_user()
        enrollment = Enrollment.objects.create(
            user=persona,
            course=self.course,
            status=Enrollment.Status.EXPIRED,
            progress=80,
        )
        schedule = _make_schedule(self.course, self.admin)

        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        enrollment.refresh_from_db()
        self.assertEqual(int(enrollment.progress), 80)

    def test_convocar_dos_veces_a_la_misma_programacion_no_duplica(self):
        """Entregable 19."""
        persona = _make_user()
        schedule = _make_schedule(self.course, self.admin)
        audience = {persona.id: ScheduleAssignment.Source.USER}

        CourseScheduleService.convocar(schedule, audience)
        result = CourseScheduleService.convocar(schedule, audience)

        self.assertEqual(len(result["convocados"]), 0)
        self.assertEqual([u.id for u in result["ya_convocados"]], [persona.id])
        self.assertEqual(ScheduleAssignment.objects.filter(schedule=schedule).count(), 1)
        # Y no se le vuelve a notificar.
        self.assertEqual(Notification.objects.filter(user=persona).count(), 1)


# =============================================================================
# Entregables 13, 14 -- Reporte filtrado por programación (no se mezclan)
# =============================================================================


class ScheduleAttendanceSummaryTests(TestCase):
    def setUp(self):
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.course = _make_course(self.admin)

    def test_roster_solo_trae_los_convocados_de_esa_programacion(self):
        """Entregable 14: dos convocatorias del mismo curso no se mezclan."""
        a = _make_user()
        b = _make_user()
        s1 = _make_schedule(self.course, self.admin, name="Turno A")
        s2 = _make_schedule(self.course, self.admin, name="Turno B")

        CourseScheduleService.convocar(s1, {a.id: ScheduleAssignment.Source.USER})
        CourseScheduleService.convocar(s2, {b.id: ScheduleAssignment.Source.USER})

        r1 = CourseScheduleService.build_schedule_attendance_summary(s1)
        r2 = CourseScheduleService.build_schedule_attendance_summary(s2)

        self.assertEqual([row["user"].id for row in r1["rows"]], [a.id])
        self.assertEqual([row["user"].id for row in r2["rows"]], [b.id])
        self.assertEqual(r1["total_inscritos"], 1)
        self.assertEqual(r2["total_inscritos"], 1)

    def test_roster_ignora_inscritos_del_curso_no_convocados(self):
        """Entregable 13: quien está en el curso pero no en la convocatoria, fuera."""
        convocado = _make_user()
        solo_inscrito = _make_user()
        Enrollment.objects.create(user=solo_inscrito, course=self.course)

        schedule = _make_schedule(self.course, self.admin)
        CourseScheduleService.convocar(
            schedule, {convocado.id: ScheduleAssignment.Source.USER}
        )

        summary = CourseScheduleService.build_schedule_attendance_summary(schedule)
        self.assertEqual([row["user"].id for row in summary["rows"]], [convocado.id])

    def test_presente_se_deriva_de_la_firma_de_finalizacion(self):
        """Mismo criterio que el reporte por curso de SD#63."""
        presente = _make_user()
        ausente = _make_user()
        schedule = _make_schedule(self.course, self.admin)
        CourseScheduleService.convocar(
            schedule,
            {
                presente.id: ScheduleAssignment.Source.USER,
                ausente.id: ScheduleAssignment.Source.USER,
            },
        )

        enrollment = Enrollment.objects.get(user=presente, course=self.course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()

        summary = CourseScheduleService.build_schedule_attendance_summary(schedule)
        by_user = {row["user"].id: row for row in summary["rows"]}

        self.assertTrue(by_user[presente.id]["presente"])
        self.assertEqual(by_user[presente.id]["estado"], "Presente")
        self.assertFalse(by_user[ausente.id]["presente"])
        self.assertEqual(by_user[ausente.id]["estado"], "Ausente")
        self.assertEqual(summary["total_presentes"], 1)
        self.assertEqual(summary["total_ausentes"], 1)
        self.assertEqual(summary["porcentaje_asistencia"], 50.0)

    def test_summary_vacio_no_divide_por_cero(self):
        schedule = _make_schedule(self.course, self.admin)
        summary = CourseScheduleService.build_schedule_attendance_summary(schedule)
        self.assertEqual(summary["total_inscritos"], 0)
        self.assertEqual(summary["porcentaje_asistencia"], 0.0)

    def test_presente_sobrevive_si_assignment_enrollment_queda_null(self):
        """Gap 3 del comentario de validación 2026-07-30 ("por qué la
        programación #5 muestra que nadie lo hizo") -- investigado por código,
        sin acceso a BD prod.

        Hipótesis a confirmar: ¿hay un problema real de sincronización entre
        `ScheduleAssignment.enrollment` y el `Enrollment` real de la persona?

        `ScheduleAssignment.enrollment` es `on_delete=SET_NULL`
        (`models.py:1367-1375`): si el `Enrollment` original se borra (p.ej.
        `management/commands/clear_courses.py`, el único borrador masivo del
        repo) el FK queda en NULL. Este test simula exactamente ese estado y
        confirma que `build_schedule_attendance_summary` NO se queda ciego:
        el fallback (`services.py:861-864`, `Enrollment.objects.filter(user=,
        course=).first()`) recupera igual el `Enrollment` real por
        user+course y refleja `completion_signature` correctamente.

        Conclusión de la investigación: no hay bug de sincronización en el
        código -- el fallback es robusto. El síntoma reportado
        ("programación #5 no refleja completaciones reales") se explica por
        el scoping documentado y ya cubierto por
        `test_roster_ignora_inscritos_del_curso_no_convocados`: el roster de
        una programación son SOLO sus convocados (`ScheduleAssignment`), así
        que alguien que completó el curso por una vía distinta a ESA
        convocatoria puntual no aparece ahí aunque sí haya completado el
        curso -- comportamiento por diseño (requisito 5 del issue: "dos
        convocatorias del mismo curso no se mezclan"), no un defecto.
        """
        persona = _make_user()
        schedule = _make_schedule(self.course, self.admin)
        CourseScheduleService.convocar(
            schedule, {persona.id: ScheduleAssignment.Source.USER}
        )

        enrollment = Enrollment.objects.get(user=persona, course=self.course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()

        # Simula el FK huérfano (SET_NULL tras borrar/recrear el Enrollment
        # por fuera del flujo de convocatoria).
        assignment = ScheduleAssignment.objects.get(schedule=schedule, user=persona)
        assignment.enrollment = None
        assignment.save()

        summary = CourseScheduleService.build_schedule_attendance_summary(schedule)
        row = summary["rows"][0]

        self.assertTrue(row["presente"])
        self.assertEqual(row["estado"], "Presente")
        self.assertEqual(summary["total_presentes"], 1)


# =============================================================================
# Entregables 21, 22 -- Permisos por rol
# =============================================================================


class SchedulePermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=User.Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        # `instructor` es obligatorio para que el export de PDF pase el gate de
        # completitud FT-HSEQ-60 de SD#63; sin él la vista redirige (302) por
        # datos faltantes y no por permisos, que es lo que mide esta clase.
        self.course = _make_course(self.admin, instructor=self.admin)
        self.schedule = _make_schedule(self.course, self.admin)

    def _urls(self):
        return [
            reverse("courses:schedule_list"),
            reverse("courses:schedule_create"),
            reverse("courses:schedule_search_people"),
            reverse("courses:schedule_detail", args=[self.schedule.id]),
            reverse("courses:schedule_edit", args=[self.schedule.id]),
            reverse("courses:export_schedule_attendance_pdf", args=[self.schedule.id]),
        ]

    def test_administrador_accede(self):
        """Entregables 21 y 22."""
        self.client.force_login(self.admin)
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_coordinador_accede(self):
        self.client.force_login(self.coordinador)
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_ejecutor_bloqueado(self):
        """Un alumno no puede ver ni crear programaciones."""
        self.client.force_login(self.ejecutor)
        for url in self._urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("courses:list"), response["Location"])

    def test_ejecutor_no_puede_crear_por_post(self):
        """El gate no es solo de lectura."""
        self.client.force_login(self.ejecutor)
        response = self.client.post(
            reverse("courses:schedule_create"),
            {"course": self.course.id, "name": "Hackeo", "users": [self.ejecutor.id]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CourseSchedule.objects.filter(name="Hackeo").exists())

    def test_anonimo_redirige_a_login(self):
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)


# =============================================================================
# Entregable 6 -- Buscador de personas
# =============================================================================


class SchedulePeopleSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.persona = _make_user(
            first_name="Rosalinda", last_name="Quintero", job_position="Soldadora SD73"
        )

    def _search(self, q):
        return self.client.get(reverse("courses:schedule_search_people"), {"q": q})

    def test_busca_por_nombre(self):
        response = self._search("Rosalinda")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rosalinda")

    def test_busca_por_cedula(self):
        response = self._search(self.persona.document_number)
        self.assertContains(response, self.persona.document_number)

    def test_busca_por_cargo(self):
        response = self._search("Soldadora SD73")
        self.assertContains(response, "Rosalinda")

    def test_query_corta_no_devuelve_la_nomina_completa(self):
        """'buscador, no una lista larga sin filtro'."""
        response = self._search("R")
        self.assertNotContains(response, "Rosalinda")
        self.assertContains(response, "al menos 2 caracteres")

    def test_no_devuelve_inactivos(self):
        # Se asserta contra la cédula y no contra el nombre: el partial hace eco
        # del término buscado en el mensaje "Sin resultados para ...".
        inactivo = _make_user(first_name="Fantasma", last_name="Inactivo", is_active=False)
        response = self._search("Fantasma")
        self.assertNotContains(response, inactivo.document_number)
        self.assertContains(response, "Sin resultados")


# =============================================================================
# Entregables 1, 7, 16, 17 -- Vistas: crear, listar, ver asistencia, sección
# =============================================================================


class ScheduleViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.course = _make_course(self.admin, instructor=self.admin)
        self.perfil = JobProfileType.objects.create(
            code=f"SD73VIEW{_SEQ[0]}", name="Perfil SD73 View", order=98
        )

    def test_crear_programacion_convoca_al_grupo(self):
        """Entregables 1, 3, 4, 5, 7 por HTTP."""
        persona = _make_user()
        del_perfil = _make_user(job_profile=self.perfil)
        del_cargo = _make_user(job_position="Cargo View SD73")

        response = self.client.post(
            reverse("courses:schedule_create"),
            {
                "course": self.course.id,
                "name": "Turno X",
                "suggested_end_date": "2026-12-31",
                "responsable": self.admin.id,
                "notes": "",
                "users": [persona.id],
                "job_profiles": [self.perfil.id],
                "job_positions": ["Cargo View SD73"],
            },
        )

        self.assertEqual(response.status_code, 302)
        schedule = CourseSchedule.objects.get(name="Turno X")
        self.assertEqual(schedule.course_id, self.course.id)
        self.assertEqual(schedule.suggested_end_date, date(2026, 12, 31))
        self.assertEqual(schedule.responsable_id, self.admin.id)
        self.assertEqual(schedule.created_by_id, self.admin.id)

        convocados = set(
            ScheduleAssignment.objects.filter(schedule=schedule).values_list(
                "user_id", flat=True
            )
        )
        self.assertEqual(convocados, {persona.id, del_perfil.id, del_cargo.id})

    def test_crear_sin_audiencia_falla(self):
        response = self.client.post(
            reverse("courses:schedule_create"),
            {"course": self.course.id, "name": "Sin nadie", "notes": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CourseSchedule.objects.filter(name="Sin nadie").exists())

    def test_listado_muestra_programaciones(self):
        _make_schedule(self.course, self.admin, name="Turno Listado")
        response = self.client.get(reverse("courses:schedule_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Turno Listado")

    def test_listado_filtra_por_busqueda(self):
        _make_schedule(self.course, self.admin, name="Turno Alfa")
        _make_schedule(self.course, self.admin, name="Turno Beta")
        response = self.client.get(reverse("courses:schedule_list"), {"search": "Alfa"})
        self.assertContains(response, "Turno Alfa")
        self.assertNotContains(response, "Turno Beta")

    def test_detalle_muestra_quien_asistio_y_quien_falta(self):
        """Entregables 13 y 17: 'yo programo y luego veo la asistencia'."""
        presente = _make_user(first_name="Presente", last_name="SD73")
        ausente = _make_user(first_name="Ausente", last_name="SD73")
        schedule = _make_schedule(self.course, self.admin)
        CourseScheduleService.convocar(
            schedule,
            {
                presente.id: ScheduleAssignment.Source.USER,
                ausente.id: ScheduleAssignment.Source.USER,
            },
        )
        enrollment = Enrollment.objects.get(user=presente, course=self.course)
        enrollment.completion_signature = _png_file()
        enrollment.completion_signed_at = timezone.now()
        enrollment.save()

        response = self.client.get(
            reverse("courses:schedule_detail", args=[schedule.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Presente SD73")
        self.assertContains(response, "Ausente SD73")
        self.assertEqual(response.context["total_presentes"], 1)
        self.assertEqual(response.context["total_ausentes"], 1)

    def test_seccion_asistencia_tiene_pestana_a_programaciones(self):
        """Entregable 16: vive DENTRO de la sección de Asistencia."""
        response = self.client.get(reverse("courses:attendance_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("courses:schedule_list"))
        self.assertEqual(response.context["active_tab"], "cursos")

    def test_programaciones_urls_cuelgan_de_attendance_reports(self):
        """Entregable 16: sin ruta nueva de primer nivel."""
        for url in [
            reverse("courses:schedule_list"),
            reverse("courses:schedule_create"),
            reverse("courses:schedule_detail", args=[1]),
        ]:
            with self.subTest(url=url):
                self.assertTrue(url.startswith("/courses/attendance-reports/"), url)

    def test_navbar_no_gana_entrada_nueva(self):
        """Entregable 16: el cliente pidió explícitamente que NO sea página nueva."""
        from pathlib import Path

        from django.conf import settings

        navbar = (Path(settings.BASE_DIR) / "templates" / "partials" / "navbar.html").read_text()
        self.assertNotIn("schedule_list", navbar)
        self.assertNotIn("schedule_create", navbar)


# =============================================================================
# Punto 6 -- Navbar cablea el badge de no-leídas (notifications:unread-count)
# =============================================================================


class NavbarNotificationBadgeTests(TestCase):
    """SD#73 punto 6 -- el link '🔔 Notificaciones' del navbar debía quedar
    texto plano sin ningún `hx-get`, pese a que el endpoint
    `notifications:unread-count` ya existía y ya devolvía el HTML del badge
    (wiring faltante confirmado por F1/F2)."""

    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    def test_navbar_cablea_hx_get_a_unread_count(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        unread_count_url = reverse("notifications:unread-count")
        self.assertContains(response, f'hx-get="{unread_count_url}"')

    def test_endpoint_unread_count_responde_html_del_badge(self):
        """Regresión de vida del endpoint que el navbar ahora consume."""
        response = self.client.get(reverse("notifications:unread-count"))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# Entregables 10, 11, 12, 15 -- Responsable, firma y PDF por programación
# =============================================================================


class ScheduleResponsableAndPdfTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.instructor = _make_user(first_name="Instructor", last_name="Curso")
        self.course = _make_course(self.admin, instructor=self.instructor)

        self.responsable_1 = _make_user(first_name="Primera", last_name="Responsable")
        self.responsable_1.signature = _png_file("firma1.png")
        self.responsable_1.save()

        self.responsable_2 = _make_user(first_name="Segunda", last_name="Responsable")
        self.responsable_2.signature = _png_file("firma2.png")
        self.responsable_2.save()

        self.schedule = _make_schedule(
            self.course, self.admin, responsable=self.responsable_1
        )
        self.convocado = _make_user()
        CourseScheduleService.convocar(
            self.schedule, {self.convocado.id: ScheduleAssignment.Source.USER}
        )

    def test_responsable_es_campo_propio_de_la_programacion(self):
        """Entregable 10: distinto del instructor del curso."""
        self.assertEqual(self.schedule.responsable_id, self.responsable_1.id)
        self.assertNotEqual(self.schedule.responsable_id, self.course.instructor_id)

    def test_firma_del_responsable_alimenta_el_pdf(self):
        """Entregable 11."""
        self.assertNotEqual(self.schedule.responsable_signature_url, "")
        self.assertIn("firma1", self.schedule.responsable_signature_url)

    def test_reasignar_responsable_cambia_la_firma(self):
        """Entregable 12: la firma sigue a quien esté a cargo."""
        firma_antes = self.schedule.responsable_signature_url

        response = self.client.post(
            reverse("courses:schedule_edit", args=[self.schedule.id]),
            {
                "course": self.course.id,
                "name": self.schedule.name,
                "suggested_end_date": "",
                "responsable": self.responsable_2.id,
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.responsable_id, self.responsable_2.id)
        self.assertIn("firma2", self.schedule.responsable_signature_url)
        self.assertNotEqual(self.schedule.responsable_signature_url, firma_antes)

    def test_editar_sin_audiencia_no_pierde_convocados(self):
        self.client.post(
            reverse("courses:schedule_edit", args=[self.schedule.id]),
            {
                "course": self.course.id,
                "name": self.schedule.name,
                "suggested_end_date": "",
                "responsable": self.responsable_2.id,
                "notes": "",
            },
        )
        self.assertEqual(
            ScheduleAssignment.objects.filter(schedule=self.schedule).count(), 1
        )

    def test_editar_agrega_convocados(self):
        nuevo = _make_user()
        self.client.post(
            reverse("courses:schedule_edit", args=[self.schedule.id]),
            {
                "course": self.course.id,
                "name": self.schedule.name,
                "suggested_end_date": "",
                "responsable": self.responsable_1.id,
                "notes": "",
                "users": [nuevo.id],
            },
        )
        convocados = set(
            ScheduleAssignment.objects.filter(schedule=self.schedule).values_list(
                "user_id", flat=True
            )
        )
        self.assertEqual(convocados, {self.convocado.id, nuevo.id})

    def test_export_pdf_devuelve_pdf(self):
        """Entregable 15."""
        response = self.client.get(
            reverse("courses:export_schedule_attendance_pdf", args=[self.schedule.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            f"asistencia_programacion_{self.schedule.id}",
            response["Content-Disposition"],
        )
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_export_pdf_bloqueado_si_falta_info_del_curso(self):
        """Reusa el gate de completitud FT-HSEQ-60 de SD#63."""
        self.course.project_name = ""
        self.course.save()

        response = self.client.get(
            reverse("courses:export_schedule_attendance_pdf", args=[self.schedule.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("courses:schedule_detail", args=[self.schedule.id]),
            response["Location"],
        )

    def test_export_pdf_individual_por_programacion_devuelve_pdf(self):
        """Gap real 1 del comentario de validación 2026-07-30: faltaba la
        4ta combinación (individual + filtrado por programación) -- el
        cliente confirmó que `course_schedule_detail.html` solo tenía el
        botón grupal, sin link 'Descargar individual' por fila."""
        response = self.client.get(
            reverse(
                "courses:export_schedule_attendance_pdf_individual",
                args=[self.schedule.id, self.convocado.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            f"asistencia_individual_programacion_{self.schedule.id}_{self.convocado.id}",
            response["Content-Disposition"],
        )
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_export_pdf_individual_por_programacion_404_si_no_convocado(self):
        """`user_id` se resuelve contra el roster de ESTA programación, no un
        lookup global de usuarios -- mismo criterio que el individual de
        SD#63 (`export_course_attendance_pdf_individual`)."""
        ajeno = _make_user()
        response = self.client.get(
            reverse(
                "courses:export_schedule_attendance_pdf_individual",
                args=[self.schedule.id, ajeno.id],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_export_pdf_individual_por_programacion_bloqueado_si_falta_info(self):
        self.course.project_name = ""
        self.course.save()

        response = self.client.get(
            reverse(
                "courses:export_schedule_attendance_pdf_individual",
                args=[self.schedule.id, self.convocado.id],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("courses:schedule_detail", args=[self.schedule.id]),
            response["Location"],
        )

    def test_schedule_detail_ofrece_descargar_individual_por_fila(self):
        """El template debe traer el link por fila (no solo el grupal)."""
        response = self.client.get(
            reverse("courses:schedule_detail", args=[self.schedule.id])
        )
        self.assertContains(
            response,
            reverse(
                "courses:export_schedule_attendance_pdf_individual",
                args=[self.schedule.id, self.convocado.id],
            ),
        )

    def _render_schedule_pdf(self, **context_overrides):
        """Arma el MISMO context que `views.export_schedule_attendance_pdf` y
        renderiza el template real -- helper compartido por los tests de
        contenido literal del PDF (gap de cobertura del bounce, ver
        docstring del módulo)."""
        from django.template.loader import render_to_string

        from apps.courses.views import _attendance_pdf_branding_context

        summary = CourseScheduleService.build_schedule_attendance_summary(self.schedule)
        context = {
            "course": self.course,
            "schedule": self.schedule,
            "rows": summary["rows"],
            "total_inscritos": summary["total_inscritos"],
            "total_presentes": summary["total_presentes"],
            "total_ausentes": summary["total_ausentes"],
            "porcentaje_asistencia": summary["porcentaje_asistencia"],
            "calificacion_promedio": summary["calificacion_promedio"],
            "schedule_date": self.schedule.suggested_end_date or self.schedule.created_at.date(),
            "generated_at": timezone.now(),
            "request_user": self.admin,
            "pdf_instructor": self.schedule.responsable,
            "instructor_signature_url": self.schedule.responsable_signature_url,
        }
        context.update(_attendance_pdf_branding_context())
        context.update(context_overrides)

        return render_to_string("courses/course_attendance_pdf.html", context)

    def test_pdf_render_usa_responsable_y_datos_de_la_programacion(self):
        """Entregables 11 y 12 a nivel de HTML renderizado.

        Incluye, además, el gate de cobertura real detrás del bounce
        (reproceso bounce=1): el HTML renderizado NO debe contener el texto
        LITERAL de los comentarios Django `{# #}` multilínea que el motor
        imprimía sin procesar (SD#73 punto 1, CRÍTICO). Ese `assertNotIn`
        es lo que faltaba la vez anterior -- el test ya renderizaba este
        HTML pero nunca lo comprobó.
        """
        html = self._render_schedule_pdf()

        self.assertIn("Primera Responsable", html)
        self.assertIn(self.schedule.name, html)
        self.assertIn("firma1", html)
        # El instructor del curso NO firma cuando hay responsable de programación.
        self.assertNotIn("Instructor Curso", html)

        # --- Gap de cobertura del bounce (punto 1, CRÍTICO) ---
        # Los 2 bloques de comentario `{# ... #}` multilínea que el motor
        # imprimía literal antes del fix. Deben estar 100% ausentes del HTML.
        self.assertNotIn("SD#73: bloque ADITIVO", html)
        self.assertNotIn("SD#73: cuando el PDF sale de una programación", html)
        # Y, ya que estamos, ningún delimitador de comentario Django crudo
        # debe sobrevivir al render (regresión genérica del mismo bug).
        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)

    def test_pdf_fecha_estable_no_cambia_entre_descargas(self):
        """Punto 2 del rebote -- 'Fecha' NO debe reflejar `generated_at`.

        Renderiza el MISMO schedule dos veces con `generated_at` distinto
        (simulando 2 descargas separadas) y confirma que el campo 'Fecha'
        (vía `schedule_date`) es estable mientras 'Generado el' sí cambia.
        """
        html_1 = self._render_schedule_pdf(
            generated_at=timezone.make_aware(datetime(2026, 1, 1))
        )
        html_2 = self._render_schedule_pdf(
            generated_at=timezone.make_aware(datetime(2026, 6, 15))
        )

        schedule_date = self.schedule.suggested_end_date or self.schedule.created_at.date()
        fecha_esperada = schedule_date.strftime("%d/%m/%Y")

        self.assertIn(f'<div class="value">{fecha_esperada}</div>', html_1)
        self.assertIn(f'<div class="value">{fecha_esperada}</div>', html_2)
        # El encabezado "Generado el" SÍ cambia -- es la fecha de descarga.
        self.assertIn("01/01/2026", html_1)
        self.assertIn("15/06/2026", html_2)
        self.assertNotIn("01/01/2026", html_2)

    def test_pdf_muestra_calificacion_total_calculada(self):
        """Punto 3 -- 'Calificación total' = promedio de evaluaciones GRADED
        de los convocados de ESTA programación (patrón Avg+GRADED de
        apps/assessments/services.py:513)."""
        from apps.assessments.models import Assessment, AssessmentAttempt

        assessment = Assessment.objects.create(
            course=self.course,
            title="Evaluación SD73",
            passing_score=60,
            created_by=self.admin,
        )
        AssessmentAttempt.objects.create(
            user=self.convocado,
            assessment=assessment,
            status=AssessmentAttempt.Status.GRADED,
            score=80,
        )

        html = self._render_schedule_pdf()

        self.assertIn("Calificación total", html)
        # Formateo localizado es-CO (LANGUAGE_CODE): coma decimal, no punto.
        self.assertIn("80,0%", html)

    def test_pdf_calificacion_total_sin_evaluaciones(self):
        """Punto 3, caso borde: nadie ha presentado evaluación -> sin dividir
        por cero, mensaje explícito en vez de 0%."""
        html = self._render_schedule_pdf()

        self.assertIn("Calificación total", html)
        self.assertIn("Sin evaluaciones", html)
        self.assertNotIn("0.0%", html)

    def test_pdf_muestra_tipo_de_actividad_de_la_programacion(self):
        """Punto 4 -- cuando hay `schedule`, el PDF muestra
        `schedule.activity_type` (propio de la convocatoria), NO las
        casillas del curso."""
        self.schedule.activity_type = Course.ActivityType.SIMULACRO
        self.schedule.save()

        html = self._render_schedule_pdf()

        self.assertIn("Tipo de actividad", html)
        self.assertIn("Simulacro", html)
        # Las casillas de chequeo (comportamiento SD#63/individual) no deben
        # aparecer cuando el PDF sale de una programación (el selector CSS
        # de la clase sigue en el <style>, pero la tabla en sí no se renderiza).
        self.assertNotIn('<table class="activity-type-table">', html)

    def test_pdf_tipo_de_actividad_no_definido_si_vacio(self):
        """Punto 4, caso borde: `activity_type` en blanco (default) no
        fuerza ninguna elección -- muestra 'No definido'."""
        html = self._render_schedule_pdf()

        self.assertIn("Tipo de actividad", html)
        self.assertIn("No definido", html)

    def test_pdf_por_curso_de_sd63_no_cambia(self):
        """El issue dice explícitamente que NO modifica el PDF de asistencia."""
        from django.template.loader import render_to_string

        from apps.courses.views import (
            _attendance_pdf_branding_context,
            _build_course_attendance_summary,
        )

        summary = _build_course_attendance_summary(self.course)
        context = {
            "course": self.course,
            "rows": summary["rows"],
            "total_inscritos": summary["total_inscritos"],
            "total_presentes": summary["total_presentes"],
            "total_ausentes": summary["total_ausentes"],
            "porcentaje_asistencia": summary["porcentaje_asistencia"],
            "generated_at": timezone.now(),
            "request_user": self.admin,
            "instructor_signature_url": "",
        }
        context.update(_attendance_pdf_branding_context())

        html = render_to_string("courses/course_attendance_pdf.html", context)

        # Sin `schedule` ni `pdf_instructor`, se comporta como antes de SD#73.
        self.assertIn("Instructor Curso", html)
        self.assertIn("Firma del instructor", html)
        self.assertNotIn("Programación</div>", html)


# =============================================================================
# Entregable 9 (parte UI) -- Aviso no bloqueante en "Mis Cursos"
# =============================================================================


class MyCoursesConvocatoriaBadgeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.course = _make_course(self.admin)
        self.persona = _make_user(rol=User.Rol.EJECUTOR)

    def test_muestra_la_convocatoria_y_su_fecha_sugerida(self):
        schedule = _make_schedule(
            self.course,
            self.admin,
            name="Turno Aviso",
            suggested_end_date=date(2026, 11, 30),
        )
        CourseScheduleService.convocar(
            schedule, {self.persona.id: ScheduleAssignment.Source.USER}
        )

        self.client.force_login(self.persona)
        response = self.client.get(reverse("courses:my_courses"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Turno Aviso")
        self.assertContains(response, "el acceso no se bloquea")

    def test_sin_convocatoria_no_muestra_nada(self):
        Enrollment.objects.create(user=self.persona, course=self.course)
        self.client.force_login(self.persona)
        response = self.client.get(reverse("courses:my_courses"))
        self.assertNotContains(response, "el acceso no se bloquea")


# =============================================================================
# Form -- validaciones
# =============================================================================


class CourseScheduleFormTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.course = _make_course(self.admin)
        self.draft = _make_course(self.admin, status=Course.Status.DRAFT)

    def test_requiere_audiencia_al_crear(self):
        form = CourseScheduleForm(
            data={"course": self.course.id, "name": "Turno", "notes": ""}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("al menos una persona", str(form.errors))

    def test_valido_con_solo_una_persona(self):
        persona = _make_user()
        form = CourseScheduleForm(
            data={
                "course": self.course.id,
                "name": "Turno",
                "notes": "",
                "users": [persona.id],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_solo_ofrece_cursos_publicados(self):
        form = CourseScheduleForm()
        course_ids = set(form.fields["course"].queryset.values_list("id", flat=True))
        self.assertIn(self.course.id, course_ids)
        self.assertNotIn(self.draft.id, course_ids)

    def test_edicion_no_exige_audiencia(self):
        schedule = _make_schedule(self.course, self.admin)
        form = CourseScheduleForm(
            data={"course": self.course.id, "name": "Renombrada", "notes": ""},
            instance=schedule,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_cargos_se_derivan_de_la_bd(self):
        _make_user(job_position="Cargo Derivado SD73")
        form = CourseScheduleForm()
        choices = dict(form.fields["job_positions"].choices)
        self.assertIn("Cargo Derivado SD73", choices)

    def test_activity_type_es_parte_del_form(self):
        """`activity_type` ya estaba en `Meta.fields` (forms.py:711) pero el
        template nunca lo renderizaba -- gap real 2 del comentario de
        validación 2026-07-30 ('el campo existe en el backend pero es
        invisible para quien crea la programación')."""
        form = CourseScheduleForm()
        self.assertIn("activity_type", form.fields)

    def test_crear_programacion_guarda_activity_type_elegido(self):
        """Punto 3 del comentario 2026-07-29: se pregunta en la
        programación como selección única (reusa `Course.ActivityType`)."""
        persona = _make_user()
        response = self.client.post(
            reverse("courses:schedule_create"),
            {
                "course": self.course.id,
                "name": "Turno con actividad",
                "notes": "",
                "activity_type": Course.ActivityType.SIMULACRO,
                "users": [persona.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        schedule = CourseSchedule.objects.get(name="Turno con actividad")
        self.assertEqual(schedule.activity_type, Course.ActivityType.SIMULACRO)


class CourseScheduleFormTemplateTests(TestCase):
    """Gap real 2: el `<select>` de `activity_type` debe estar en el HTML
    servido, no solo en `Meta.fields` del form."""

    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.course = _make_course(self.admin)

    def test_form_nueva_programacion_renderiza_activity_type(self):
        response = self.client.get(reverse("courses:schedule_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="activity_type"')
        self.assertContains(response, "Tipo de actividad")

    def test_form_editar_programacion_renderiza_activity_type(self):
        schedule = _make_schedule(self.course, self.admin)
        response = self.client.get(
            reverse("courses:schedule_edit", args=[schedule.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="activity_type"')
