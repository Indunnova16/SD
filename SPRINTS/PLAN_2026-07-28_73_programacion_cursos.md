# PLAN SD#73 — Programación de cursos (convocatoria a grupo de personas)

- **Issue:** https://github.com/Indunnova16/SD/issues/73 (label `Urgente`)
- **Fecha:** 2026-07-28
- **Worktree:** `/Users/miguelrodriguez/SD-wt-73` · rama `fix/sd-73-2026-07-28`
- **Reproceso (paso 1a):** `SD#73 — NO es reproceso (sin cierre nuestro previo). Cerrar normal.`
- **Baseline de la suite ANTES de tocar código:** `1454 passed, 1 skipped, 657 warnings, 115 subtests passed` (verde).

---

## 1. Qué pide el cliente

### Body del issue
Una **"programación"** es una convocatoria puntual de un curso **ya existente** a un
**grupo específico de personas**. No crea contenido nuevo: define **quién** debe tomarlo
y **hasta cuándo**. Ejemplo real: "Turno X".

1. Crear una programación sobre un curso ya existente.
2. Asignar a quién va dirigida: por **persona** (nombre/cédula) o por **cargo/perfil
   ocupacional**. Con **buscador**, no una lista larga sin filtro.
3. **Fecha de finalización sugerida, NO límite duro.** El sistema indica "se le asignó
   este curso y tiene hasta tal fecha", pero si no lo completa a tiempo **debe poder
   seguir haciéndolo** (no bloquear el acceso).
4. **Responsable de la programación = firma que aparece en la asistencia.** La firma de
   perfil del responsable sale automáticamente en el PDF de asistencia de esa
   programación. Si se **reasigna** el responsable, la firma pasa a ser la del nuevo.
5. **Reporte de asistencia filtrado por programación**, no solo por curso completo — sin
   mezclar con otras convocatorias del mismo curso.

### Comentario (manda sobre el body)
> "La Programación vive **dentro de la misma sección de Asistencia**, no en una página aparte."

Confirmado con Andrea: **NO** es una página nueva independiente en el navbar. Va integrada
en la sección/flujo de **Asistencia** (#63), como paso previo o pestaña, de forma que el
flujo quede junto: (1) se programa el curso → (2) desde ahí mismo se ve la asistencia de
esa programación (quién ya lo hizo, quién falta, descargar el reporte).
Ejemplo dado: *"yo programo y luego veo la asistencia, así sería"*.

### Fuera de alcance (explícito en el issue)
Solo la capa de "Programación". **No** modifica el PDF de asistencia en sí (#63) ni el
contenido de los cursos.

---

## 2. Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | ✅/❌ |
|---|------------|-----------------------------------------------|-------|
| 1 | **Crear una programación** sobre un curso YA existente, sin tocar el curso | `POST /courses/attendance-reports/programaciones/nueva/` crea `CourseSchedule(course=<existente>)`; el `Course` no se modifica | ✅ |
| 2 | La programación tiene **nombre propio** de convocatoria (ej. "Turno X") | Campo `CourseSchedule.name`, visible en listado y detalle | ✅ |
| 3 | **Convocar por persona específica** (nombre / cédula) | Form field `users` (múltiple) alimentado por buscador; `ScheduleAssignment.source="user"` | ✅ |
| 4 | **Convocar por perfil ocupacional** (todos los que tengan ese perfil) | Form field `job_profiles` (`JobProfileType`); expande a todos los `User` activos con ese `job_profile`; `source="profile"` | ✅ |
| 5 | **Convocar por cargo** (`User.job_position`, texto libre) | Form field `job_positions` (choices distinct de la BD); expande a todos los activos con ese cargo; `source="position"` | ✅ |
| 6 | **Buscador** de personas (no lista larga sin filtro) | `GET /courses/attendance-reports/programaciones/buscar-personas/?q=` → partial HTMX; busca por nombre, apellido, cédula y cargo; mín. 2 chars; tope 50 resultados | ✅ |
| 7 | **Fecha de finalización SUGERIDA** (se guarda y se muestra) | `CourseSchedule.suggested_end_date`; se muestra en listado, detalle, PDF y notificación | ✅ |
| 8 | La fecha **NO bloquea**: pasada la fecha el convocado sigue pudiendo hacer el curso | La fecha NO se escribe en `Enrollment.due_date` (ese campo sí bloquea vía `check_enrollment_deadlines` → `EXPIRED`). Test: convocatoria con fecha vencida deja `enrollment.due_date is None` y `status != EXPIRED` | ✅ |
| 9 | El sistema **indica a la persona** "se le asignó este curso y tiene hasta tal fecha" | `Notification` in-app por convocado (`subject`/`body` con curso + fecha sugerida + "no se bloquea el acceso") + badge informativo en "Mis Cursos" | ✅ |
| 10 | **Responsable** de la programación (campo propio, no el instructor del curso) | `CourseSchedule.responsable` (FK User) | ✅ |
| 11 | La **firma del responsable** sale automáticamente en el PDF de esa programación | `export_schedule_attendance_pdf` pasa `instructor_signature_url = schedule.responsable.signature.url` y `pdf_instructor = schedule.responsable` | ✅ |
| 12 | **Reasignar** el responsable → la firma que aparece pasa a ser la del nuevo | Editar la programación cambiando `responsable`; el PDF re-renderizado trae la firma del nuevo (se resuelve en tiempo de render, no se copia) | ✅ |
| 13 | **Reporte de asistencia filtrado por programación** (quién asistió / quién falta) | `GET /courses/attendance-reports/programaciones/<id>/` → roster SOLO de los convocados de esa programación, con Presente/Ausente | ✅ |
| 14 | **Sin mezclar** con otras convocatorias del mismo curso | Test: 2 programaciones del mismo curso con personas distintas → cada roster trae solo los suyos | ✅ |
| 15 | **PDF** de asistencia por programación descargable | `GET /courses/attendance-reports/programaciones/<id>/export-pdf/` → `application/pdf` | ✅ |
| 16 | **Vive dentro de la sección Asistencia** (comentario, manda sobre el body) | URLs bajo `attendance-reports/programaciones/…`; pestañas "Por Curso" / "Programaciones" en la misma sección; **cero entradas nuevas en el navbar** | ✅ |
| 17 | Flujo "programo → veo la asistencia" en un solo lugar | Desde el detalle de la programación se ve el roster y se descarga el PDF, sin saltar de módulo | ✅ |
| 18 | **Qué pasa si alguien ya está inscrito** en el curso | Se reusa el `Enrollment` existente (`get_or_create`): NO se duplica, NO se resetea progreso ni firma, NO se re-expira. Queda convocado igual | ✅ |
| 19 | Persona convocada **dos veces a la misma programación** | `UniqueConstraint(schedule, user)` → no duplica; el resultado reporta "ya convocados" aparte | ✅ |
| 20 | Persona en **dos programaciones del mismo curso** | Permitido; ambas la listan; el único `Enrollment` (unique `user`+`course`) respalda ambas | ✅ |
| 21 | **Permisos por rol** para ver/exportar | `ADMINISTRADOR` + `COORDINADOR` (mismo gate `_attendance_export_required` ya vigente en la sección). `EJECUTOR` → redirect con mensaje | ✅ |
| 22 | **Permisos por rol** para crear/editar la programación | `ADMINISTRADOR` + `COORDINADOR`. `EJECUTOR` bloqueado | ✅ |
| 23 | **Estados** | ℹ️ Decisión de scope: el issue NO define una máquina de estados para la programación. Estado por persona = **Presente/Ausente** derivado (igual que #63); la programación expone `is_overdue` (derivado de la fecha sugerida, informativo). No se inventa un ciclo Abierta/Cerrada que nadie pidió | ✅ (como decisión) |
| 24 | Migración **aditiva** (hay datos productivos) | `0023_courseschedule_scheduleassignment.py`: solo `CreateModel`, cero alteraciones a `Course`/`Enrollment`/`User` | ✅ |
| 25 | Suite completa verde, sin arreglar tests preexistentes ajenos | `pytest` con `DJANGO_SETTINGS_MODULE=config.settings.test` (de `pyproject.toml`) | ✅ |

---

## 3. Diseño — qué se REUSA del repo (nada inventado)

| Pieza existente | Ruta | Cómo se reusa |
|---|---|---|
| Sección Asistencia (listado) | `apps/courses/views.py:2667` `course_attendance_reports_list` | La Programación cuelga de esta MISMA sección (`attendance-reports/…`), con pestañas. No se toca el navbar |
| Gate de rol de la sección | `apps/courses/views.py:2406` `_attendance_export_required` (ADMIN+COORD) | Reusado tal cual en las 5 vistas nuevas |
| Helper RBAC | `apps/accounts/permissions.py` `user_has_rol` / `require_rol` | Único árbitro de rol, no se lee `is_staff` ni `job_profile` |
| Roster Presente/Ausente | `apps/courses/views.py:2271` `_build_course_attendance_summary` | Se extrae la construcción de fila a partir del `Enrollment` y se aplica al subconjunto convocado (mismo criterio: presente ⇔ `Enrollment.completion_signature`) |
| Branding PDF (logo + color) | `apps/courses/views.py:2375` `_attendance_pdf_branding_context` | Reusado sin cambios en el PDF de programación |
| Template PDF FT-HSEQ-60 | `templates/courses/course_attendance_pdf.html` | Reusado; se añade UN bloque aditivo guardado por `{% if schedule %}` + `pdf_instructor` con fallback a `course.instructor` (el PDF por curso e individual quedan byte-idénticos) |
| Gate de completitud del curso | `apps/courses/views.py:2489` `_course_attendance_missing_fields` | Reusado: no se exporta un PDF incompleto |
| Patrón de asignación masiva + `bulk_create` | `apps/learning_paths/services.py:20` `assign_path_to_user` | Patrón copiado (asignación → enrollments, `ignore_conflicts`), adaptado a una convocatoria puntual |
| Auto-enroll sin prerequisitos | `apps/courses/views.py:504-511` (`my_courses`) | Precedente para que la convocatoria administrativa cree el `Enrollment` sin exigir prerrequisitos |
| Notificaciones in-app | `apps/notifications/services/notification.py:24` `NotificationService.create_notification` | API correcta (`subject`/`body`) para el aviso al convocado |
| Búsqueda HTMX con partial | `apps/courses/views.py:790` `course_admin_list` + `templates/courses/partials/course_admin_table.html` | Mismo patrón (`HX-Request` → partial) para el buscador de personas |
| Perfil ocupacional | `apps/courses/models.py:59` `JobProfileType` ← `User.job_profile` (`apps/accounts/models.py:131`) | Fuente de "perfil ocupacional" |
| Cargo | `apps/accounts/models.py:130` `User.job_position` | Fuente de "cargo" (texto libre) |
| Fixtures de test | `apps/courses/tests/test_issue_63.py:57-80` (`_PNG_BYTES`, `_make_user`) | Mismo estilo de fixtures/PNG mínimo |

### Modelos nuevos (aditivos)

```
CourseSchedule           # la "Programación" / convocatoria
  course           FK Course            (curso YA existente, no se modifica)
  name             Char                 ("Turno X")
  suggested_end_date Date null          (SUGERIDA — nunca se copia a Enrollment.due_date)
  responsable      FK User  null        (su firma de perfil sale en el PDF)
  notes            Text blank
  created_by       FK User  null
  created_at / updated_at
  → property is_overdue, total_convocados, total_presentes, ...

ScheduleAssignment       # una persona convocada a esa programación
  schedule         FK CourseSchedule
  user             FK User
  enrollment       FK Enrollment null   (el enrollment reusado/creado)
  source           Char (user|profile|position)
  created_at
  UniqueConstraint(schedule, user)
```

### Decisión crítica — por qué la fecha NO va a `Enrollment.due_date`

`apps/courses/tasks.py:510` `check_enrollment_deadlines` marca como `EXPIRED` todo
`Enrollment` con `due_date < today`, y `templates/courses/my_courses.html:105` obliga
entonces a "Habilitar de nuevo" (con 5 días menos, `views.py:531 reenable_course`).
Es decir: **`Enrollment.due_date` es un límite duro que bloquea.** El requisito 3 pide
exactamente lo contrario. Por eso la fecha sugerida vive **solo** en
`CourseSchedule.suggested_end_date` y es puramente informativa.

---

## 4. Compuertas HITL

- **Ninguna escritura en BD de producción** requerida por este issue: los modelos son
  nuevos y la migración es aditiva (solo `CreateModel`). No hay backfill de datos.
- Sin deploy, sin push, sin comentario en el issue en esta corrida (alcance acordado).
