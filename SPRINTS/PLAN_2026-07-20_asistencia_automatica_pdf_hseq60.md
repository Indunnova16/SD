# PLAN — Asistencia automática por curso + PDF formato oficial FT-HSEQ-60 (issue #63)

**Fecha:** 2026-07-20
**Issue:** [Indunnova16/SD#63](https://github.com/Indunnova16/SD/issues/63)
**Estado:** Planning completado, listo para ejecución
**Branch:** UNA branch consolidada (modelo + forms + vista/template PDF nuevo + report course-level + navbar comparten `apps/courses/*`).

## Contexto

Rediseño del PDF de asistencia al formato oficial `FT-HSEQ-60 Lista de asistencia V04` +
gate de validación pre-descarga + conversión de la asistencia de "lección manual por
curso" a "capacidad automática de todo curso" (usando la firma de finalización que YA
existe) + link visible en el navbar (pedido de seguimiento del cliente, 2026-07-17).

### Hechos verificados en el repo y en BD prod (grounding)

- Última migración: `apps/courses/migrations/0021_backfill_attendance_progress_percent.py`
  → la nueva es **`0022`**.
- `Course` (models.py:160-289) hoy NO tiene `project_name` / `activity_type` / `instructor`.
  `Course.objectives` (TextField, blank=True) ya existe → mapea a "Objetivo". `Course.title`
  ya existe → mapea a "Tema" (ver decisión abajo). `Course.duration_hours` (property,
  models.py:288, ya usada en certificados SD#43) → mapea a "Tiempo".
- `User.job_position` (`apps/accounts/models.py:131`, `CharField`, REQUIRED_FIELD) ya existe
  y está poblado en prod (15/15 usuarios) → mapea a "Cargo" en la tabla del PDF.
- `User.signature` (`apps/accounts/models.py:123`, ImageField) ya existe y es el mismo campo
  que usa `_resolve_attendance_responsable` (views.py:2246) para precargar la firma del
  responsable del PDF actual → se reutiliza para la firma del Instructor.
- Mecanismo de firma **YA EXISTENTE y genérico** (no depende de ninguna lección):
  `Enrollment.completion_signature` / `completion_signed_at` (models.py:862-872) +
  `sign_course_completion` (views.py:1995) — el alumno firma al presionar "Finalizar
  Curso", **para TODO curso**, no solo los que tienen una lección de tipo Asistencia.
  Confirmado en BD prod: de 13 `enrollments`, **8 ya tienen `completion_signature`
  no vacío** — el dato para el reporte automático por curso YA EXISTE hoy, sin fabricar
  nada nuevo (gate de disponibilidad Kaizen #53: `count=8 >= 1` → mutativo viable, no
  render-only).
- Mecanismo **viejo** (per-lección manual), a mantener intacto por decisión de esta
  planificación (ver sección de decisión de arquitectura): `Lesson.Type.ATTENDANCE`,
  `AttendanceSignature`, `attendance_lesson_view`, `save_attendance_signature`,
  `_build_attendance_summary(course, lesson)` (views.py:2179),
  `_resolve_attendance_responsable(course, lesson)` (views.py:2246),
  `_attendance_export_required(request)` (views.py:2280, ya exige
  `Rol.ADMINISTRADOR`/`Rol.COORDINADOR` — ver punto 4 del issue, "ya implementado"),
  `export_attendance_pdf(request, course_id, lesson_id)` (views.py:2299) +
  `templates/courses/attendance_pdf.html`.
- **Confirmado en BD prod el problema que reporta el issue** (duplicados por creación
  manual): `lessons` con `lesson_type='attendance'` incluye 2 filas literalmente
  tituladas "Asistencia", más "asistencia 2 de prueba", "prieba asistencia" (typo),
  "prueba pdf", "qa_e2e_sd59_a4 asistencia" (residuo de QA) — 6 títulos distintos para
  el mismo concepto, exactamente el síntoma citado en el issue.
- RBAC: `Rol.EJECUTOR` / `Rol.COORDINADOR` / `Rol.ADMINISTRADOR`
  (`apps/accounts/models.py:77-92`, issue #58) + helper `user_has_rol` /
  `require_rol` (`apps/accounts/permissions.py:59,76`). Punto 4 del issue: **ya
  implementado** en `_attendance_export_required` y `is_attendance_admin_view`
  (views.py:307,2049) — solo requiere un test de regresión sobre la vista NUEVA.
- `templates/partials/navbar.html:107-114` (desktop, dentro de "Operaciones") y
  `:297-302` (móvil) — patrón exacto a replicar, gateado hoy solo
  `user.rol == 'ADMINISTRADOR'`; el cliente pide replicarlo pero con
  `user.rol == 'ADMINISTRADOR' or user.rol == 'COORDINADOR'` (texto literal del
  comentario de seguimiento, con snippet Django ya redactado por el cliente).
- URL prefix confirmado (`config/urls.py:64`): `path("courses/", include("apps.courses.urls"))`,
  `app_name = "courses"` → todas las nuevas rutas van `courses:<name>` con path
  absoluto `/courses/...`.
- Login prod: `login_field_user: username`, `login_path: /accounts/login/` (confirmado
  contra `~/.claude/skills/qa-prod/journeys/SD.yaml` existente). QA users con rol real
  ya sembrados en `secrets/SD.env`: `SD_QA_ADMIN_USER` (ADMINISTRADOR),
  `SD_QA_COORDINADOR_USER` (COORDINADOR), `SD_QA_EJECUTOR_USER` (EJECUTOR) — confirmados
  contra BD prod (`users.rol`).

## ⚠️ Decisión de arquitectura tomada autónomamente en este F2 (pendiente de confirmar con Miguel)

El F1 de este issue marcó `requiere_input_humano=true` sobre dos preguntas de diseño
genuinas. Corriendo en modo `--unattended`, y siendo el scope **single-módulo**
(todo dentro de `apps/courses`), esto NO bloquea la ejecución (protocolo: decisión
razonada y documentada ahora, confirmación de Miguel después — NO ambigüedad dejada
para que otro agente la resuelva a mitad de F3). Decisión tomada, con evidencia real
del código y de BD prod:

1. **Fuente de la firma de asistencia automática = reusar
   `Enrollment.completion_signature`/`completion_signed_at`, NO construir un mecanismo
   nuevo.** Evidencia: (a) el propio texto del issue #63 punto 3 dice literalmente
   *"el alumno solo firma al finalizar el curso"* — describe exactamente el flujo que
   `sign_course_completion` ya implementa hoy para TODO curso; (b) en BD prod 8 de 13
   `enrollments` YA tienen esa firma capturada — cero trabajo de captura nuevo; (c)
   construir un mecanismo dedicado nuevo (ej. otra firma "de asistencia" separada de
   la firma "de finalización") duplicaría UX (el alumno firmaría dos veces por el
   mismo hecho) y superficie de código sin beneficio. Riesgo aceptado: semánticamente
   "firmó al completar el curso" pasa a leerse también como "asistió" — es coherente
   con un LMS de inducciones/capacitaciones (completar = haber tomado la capacitación).

2. **La lección manual `Lesson.Type.ATTENDANCE` NO se retira ni se migra — COEXISTE
   intacta con datos ya en prod; solo se cierra la puerta a crear lecciones NUEVAS de
   ese tipo.** Evidencia y justificación: (a) el issue pide "ya no requerir" la
   creación manual, no pide borrar lo existente; (b) hay datos reales en prod
   (2 lecciones "Asistencia" + AttendanceSignature de alumnos que ya firmaron esas
   sesiones) — migrarlos o borrarlos es una decisión de negocio sobre datos de
   producción que ningún agente puede tomar sin autorización explícita (regla dura
   del protocolo: nunca `psql` INSERT/UPDATE/DELETE, ninguna migración de datos
   corrida directo contra prod); (c) el fix de la causa raíz real (gente creando
   duplicados sin querer) se resuelve ocultando la opción "Asistencia" del selector
   de tipo de lección **solo cuando se está creando una lección nueva** (sub-item A7)
   — deja de ser posible generar MÁS duplicados desde hoy, sin tocar ni un byte de lo
   que ya existe ni arriesgar que un `<select>` sin la opción correspondiente
   corrompa silenciosamente el tipo de una lección ya guardada al reabrir/guardar su
   edición (riesgo real de Alpine/HTML nativo con `<select>` sin `<option>` que
   matchee el valor persistido).
   - **Pendiente de confirmación con Miguel / cliente**: si en algún momento se
     decide limpiar/migrar las lecciones "Asistencia" duplicadas o consolidar sus
     firmas dentro del nuevo reporte automático, es un **backfill de datos de
     producción que requiere HITL explícito** — se deja registrado como
     `accion_post_deploy` (ver JSON) para que Miguel decida si lo autoriza en un
     sprint aparte. NO se ejecuta en este sprint.

3. **Tema del PDF = `Course.title` reusado, no se crea un campo nuevo.** `title` ya es
   obligatorio a nivel de modelo y semánticamente cumple el rol de "Tema" del formato
   oficial; agregar un campo paralelo (`topic`) crearía dos fuentes de verdad que
   pueden divergir sin beneficio real. Si Miguel prefiere un campo separado
   (ej. título de curso ≠ tema de la sesión puntual), es un ajuste de 1 sub-item en
   una siguiente vuelta, no bloquea esta v1.0.

4. **Plantilla nueva `course_attendance_pdf.html`, NO redecorar
   `attendance_pdf.html` en el sitio.** El issue dice literalmente "rediseñar
   `attendance_pdf.html`", pero ese template hoy es consumido por el flujo VIEJO
   (`export_attendance_pdf(course_id, lesson_id)`, que sigue vivo por la decisión #2).
   Redecorarlo in-place con el contexto nuevo (campos a nivel `Course`) rompería
   silenciosamente el PDF legado la próxima vez que alguien lo genere para una de las
   2 lecciones "Asistencia" reales que hoy existen en prod. Se crea un template nuevo
   dedicado al flujo automático por curso; el viejo queda 100% intacto.

**Ninguna de estas 4 decisiones toca ni migra un solo registro de producción.** Son
reversibles a nivel de código en la próxima vuelta si Miguel decide distinto.

## Sub-items por sprint

### Sprint A (deployable_solo: false — bundle único, la vista/template nuevos dependen del modelo nuevo)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | `Course`: 3 campos nuevos — `project_name` (CharField 200, blank=True, verbose "Proyecto"; sigue la convención ya usada en `preop_talks.project_name`/`lessons_learned` para "proyecto/línea/sitio"), `activity_type` (CharField choices `ActivityType`: CHARLA/CAPACITACION/SIMULACRO/SOCIALIZACION/OTRA, blank=True, verbose "Tipo de actividad"), `instructor` (FK `accounts.User`, `on_delete=SET_NULL`, null=True, blank=True, `related_name="courses_as_instructor"`, verbose "Instructor asignado"). Migración `0022_course_attendance_fields.py`. Todos `blank=True`/`null=True` para no romper los 8 cursos ya existentes — la obligatoriedad real la impone el gate A5, no la BD. | apps/courses/models.py, apps/courses/migrations/0022_course_attendance_fields.py | `makemigrations --check` limpio; `migrate` aplica sobre los 8 cursos reales sin error (todos quedan con los 3 campos vacíos, cero rotura) | - | low | ⏳ pendiente |
| A2 | Forms: agregar `project_name`, `activity_type`, `instructor` a `Meta.fields` + widgets de `CourseCreateForm`, `CourseEditParamsForm`, `CourseFullEditForm` (forms.py:70,125,170). `instructor` como `Select` filtrado a usuarios activos (`queryset = User.objects.filter(is_active=True).order_by("first_name")`, `empty_label="Sin asignar"`). UI: agregar los 3 campos en `course_create.html`, `course_edit_params.html`, `course_full_edit.html` (mismo patrón `input input-bordered`/`select select-bordered` que el resto del form). | apps/courses/forms.py, templates/courses/course_create.html, templates/courses/course_edit_params.html, templates/courses/course_full_edit.html | unit: form válido con los 3 campos completos; válido también con los 3 vacíos (blank=True); `instructor` acepta `None` | A1 | medium | ⏳ pendiente |
| A3 | Template NUEVO `course_attendance_pdf.html` (formato FT-HSEQ-60): encabezado con Fecha (= fecha de generación del reporte, `generated_at` — no existe ya un concepto de "fecha de sesión" a nivel curso con firma automática, ver decisión #3 de arriba), Instructor (`course.instructor.get_full_name`) + su firma (`course.instructor.signature.url` si existe, si no línea en blanco — mismo patrón que `responsable_signature_url` de hoy), Proyecto (`course.project_name`), Tema (`course.title`), Objetivo (`course.objectives`), Tipo de actividad (`course.get_activity_type_display`), Tiempo (`course.duration_hours` + " h"). Tabla: No. (`forloop.counter`), Nombre completo, Cédula (`document_number`), **Cargo** (`row.user.job_position`, columna NUEVA vs el PDF viejo), Firma (imagen de `Enrollment.completion_signature` si existe, si no "Sin firma"/"Firmado ✓" según estado). Se conserva el bloque "Resumen de Asistencia" (Inscritos/Presentes/Ausentes/%) que ya existe hoy (el issue dice que el PDF actual "sí incluye" eso, no pide quitarlo). Pie: sección estática **"Eficacia de la capacitación"** con la escala impresa literal (1–3.4 necesita refuerzo · 3.5–5 aprueba) — texto fijo, NO campo de captura. Se retira el bloque "Firma del Responsable" separado del PDF viejo (queda consolidado en el Instructor del encabezado, ver decisión #4). | templates/courses/course_attendance_pdf.html (NUEVO) | (cubierto por A5 unit + journey mutativo) | A1 | high | ⏳ pendiente |
| A4 | Helper `_build_course_attendance_summary(course)` en views.py (paralelo a `_build_attendance_summary(course, lesson)` ya existente, NO lo reemplaza): recorre `Enrollment.objects.filter(course=course).select_related("user")`, deriva `presente` = `completion_signature` no vacío, arma `rows` (full_name, document_number, job_position, presente, signed_at=`completion_signed_at`, signature_image_url=`completion_signature.url` si existe) + totales + `%` (misma fórmula/edge-case 0 inscritos que la función hermana). | apps/courses/views.py | unit: rows correctas con 2 inscritos (1 firmado, 1 no) sobre curso real de prod (id=63, "INDUCCIÓN PODA Y TALA", 2 enrollments con `completion_signature`); 0 inscritos → 0% sin ZeroDivisionError | A1 | medium | ⏳ pendiente |
| A5 | Vista + URL `export_course_attendance_pdf(request, course_id)` — reusa `_attendance_export_required` (mismo gate ADMINISTRADOR+COORDINADOR ya validado en el issue punto 4) + patrón xhtml2pdf existente (`pisa.CreatePDF` → `HttpResponse` `application/pdf`, filename `asistencia_curso_<id>_<YYYYMMDD>.pdf`). **Gate de validación (issue punto 2):** antes de renderizar, si falta `project_name`, `activity_type`, `objectives` o `instructor` → `messages.error` listando los campos faltantes + `redirect` a **`courses:course_full_edit`** — es el ÚNICO de los 3 forms que expone `objectives` junto con los 3 campos nuevos a la vez (`course_edit_params` NO tiene `objectives` en su `Meta.fields` hoy ni se le agrega en A2; redirigir ahí dejaría al Administrador sin forma de completar Objetivo desde ese mismo flujo) — NO genera PDF incompleto. `duration_hours` NO se gatea (se deriva de las lecciones del curso, forzarlo penalizaría cursos cortos legítimos; se documenta como decisión de scope, no bug). URL: `courses/attendance-reports/<int:course_id>/export-pdf/`, name `export_course_attendance_pdf`. | apps/courses/views.py, apps/courses/urls.py | unit: 200 + `content-type application/pdf` con curso completo; redirect a `course_full_edit` + mensaje de campos faltantes con curso incompleto (los 8 reales hoy, antes de que alguien los complete); 403/redirect para rol EJECUTOR | A1, A3, A4 | medium | ⏳ pendiente |
| A6 | Vistas + URLs course-level para Administrador+Coordinador: (a) `course_attendance_reports_list(request)` — lista de cursos con conteo inscritos/firmados + link a detalle, URL `courses/attendance-reports/`, name **`attendance_reports`** (nombre literal que ya usó el cliente en su comentario de seguimiento — mantiene el link del navbar sin ambigüedad); (b) `course_attendance_report_detail(request, course_id)` — roster on-screen del curso (reusa A4) + botón "Descargar PDF" (→ A5) + aviso visual si el gate de A5 bloquearía la descarga (campos faltantes). Ambas gateadas con `_attendance_export_required`. Templates nuevos `course_attendance_reports_list.html`, `course_attendance_report_detail.html` (mismo layout base que `course_admin_list.html`). | apps/courses/views.py, apps/courses/urls.py, templates/courses/course_attendance_reports_list.html (NUEVO), templates/courses/course_attendance_report_detail.html (NUEVO) | unit: lista 200 solo para ADMINISTRADOR/COORDINADOR, 403/redirect EJECUTOR; detalle muestra roster correcto | A4, A5 | medium | ⏳ pendiente |
| A7 | Builder: ocultar `<option value="attendance">Asistencia</option>` (`templates/courses/partials/builder/lesson_form.html`, línea del `<select name="lesson_type">`) **solo cuando `is_new` es true** (`{% if not is_new %}<option value="attendance">Asistencia</option>{% endif %}`) — cierra la puerta a NUEVOS duplicados sin arriesgar que el `<select>` reviente/corrompa el tipo de una lección "Asistencia" YA existente al reabrirla para editar (esas 2+ lecciones reales en prod siguen editables con su tipo intacto, porque para ellas `is_new=False` y la opción sigue presente). | templates/courses/partials/builder/lesson_form.html | (cubierto por journey read-only: builder de curso nuevo no muestra "Asistencia"; builder editando una lección Asistencia existente sí la muestra) | - | low | ⏳ pendiente |
| A8 | Navbar: link `📋 Asistencia por Curso` → `{% url 'courses:attendance_reports' %}`, gateado `{% if user.rol == 'ADMINISTRADOR' or user.rol == 'COORDINADOR' %}`, en el bloque desktop `templates/partials/navbar.html:107-114` (dentro de "Operaciones", junto a "Eventos de asistencia") y el bloque móvil `:297-302` — snippet literal ya redactado por el cliente en su comentario de seguimiento. | templates/partials/navbar.html | (cubierto por journey: EJECUTOR no ve el link, COORDINADOR sí) | A6 | trivial | ⏳ pendiente |
| A9 | Test de regresión RBAC (issue punto 4 — "ya implementado, no romperlo"): `Rol.EJECUTOR` recibe 403/redirect en `attendance_reports` (lista), `course_attendance_report_detail` y `export_course_attendance_pdf`; `Rol.COORDINADOR` y `Rol.ADMINISTRADOR` sí acceden a las 3. | apps/courses/tests/test_issue_63.py | 6 casos (3 vistas × {EJECUTOR bloqueado, COORDINADOR/ADMINISTRADOR permitido}) | A5, A6 | low | ⏳ pendiente |
| A10 | Tests unitarios consolidados (happy path + edge cases) + smoke E2E autenticado: helper A4 (%, 0 inscritos), gate de A5 (campos faltantes vs completos), PDF válido (content-type + tamaño mínimo), lista/detalle A6, builder A7 (opción oculta solo para lección nueva). Contra dato real de prod (curso id=63, ya con 2 enrollments firmados) además de fixtures propias. | apps/courses/tests/test_issue_63.py | pytest verde, cobertura happy + ≥3 edge cases | A2, A5, A6, A7, A9 | medium | ⏳ pendiente |

No hay Sprint B — el scope completo (backend + UI + gate + navbar + tests) es una sola
v1.0 coherente; partirlo en "mínimo + mejoras" dejaría el gate de validación o el
navbar sin cerrar, que es justo lo que el cliente pidió completo.

## DAG dependencias

```
A1 (migración 3 campos Course)
 ├─→ A2 (forms + UI edición)
 ├─→ A3 (template PDF nuevo)
 └─→ A4 (helper resumen course-level, fuente completion_signature)
              A1,A3,A4 ─→ A5 (vista export + gate validación)
                    A4,A5 ─→ A6 (lista + detalle course-level)
                          A6 ─→ A8 (navbar)
A7 (builder oculta opción) — independiente, sin dependencias
A5,A6 ─→ A9 (regresión RBAC)
A2,A5,A6,A7,A9 ─→ A10 (tests consolidados + smoke)
```

Orden sugerido F3 (`sprint_exec`):
1. **A1** primero (migración, bloquea casi todo).
2. En paralelo: A2 (forms/UI edición), A3 (template PDF), A7 (builder, sin dependencias).
3. A4 → A5 (necesita A1+A3+A4) → A6 (necesita A4+A5) → A8 (necesita A6).
4. A9 al final de A5/A6. A10 cierra el sprint.

## Riesgos y mitigaciones

- **Layout pixel-perfect del PDF sin el físico FT-HSEQ-60 real** (no hay adjunto ni
  foto en el issue/comentarios — confirmado, `adjuntos_revisados: []` en F1). Se
  construye A3 contra la DESCRIPCIÓN textual literal del issue (campos + orden +
  escala de eficacia), no contra un layout visual verificado. **Precedente**:
  `SPRINTS/PLAN_2026-07-09_certificados_asistencia.md` ítem D1 tuvo el mismo gap y
  obligó un descubrimiento posterior. Mitigación: marcar explícitamente en el cierre
  (F6) que el layout está 🟡 pendiente de validación visual contra el documento físico
  — NO se declara 🟢 "pixel-perfect" sin ese contraste.
- **Gate de A5 bloqueará HOY los 8 cursos reales de prod** (ninguno tiene
  `project_name`/`activity_type`/`instructor` porque son campos nuevos). Es el
  comportamiento CORRECTO que pide el issue punto 2 (no generar PDF incompleto), pero
  significa que nadie podrá descargar el PDF nuevo hasta completar esos campos por
  curso. Mitigación: el mensaje de redirect debe ser explícito sobre qué falta y
  llevar directo a `course_full_edit` (único form con los 4 campos gateados a la
  vez); se documenta en el comentario al cliente
  (F6) que deben completar Proyecto/Tipo de actividad/Instructor en sus cursos activos
  antes de poder exportar. NO se auto-rellenan esos campos con datos inventados.
- **`Enrollment.completion_signature` como fuente de asistencia asume que "completar
  el curso" = "asistir".** Válido para cursos de un solo bloque/sesión (la mayoría de
  inducciones HSEQ), pero si un curso real representa MÚLTIPLES sesiones físicas
  distintas en el tiempo (varias fechas), una sola firma de finalización no captura
  asistencia POR SESIÓN. El issue no pide ese nivel de granularidad ("todo curso debe
  tener automáticamente... la capacidad de registrar asistencia", singular, sin
  mencionar sesiones múltiples) — se documenta como límite conocido de v1.0, no como
  bug.
- **`<select>` de tipo de lección sin la opción "Asistencia" en el flujo de creación**
  (A7): riesgo mitigado con `{% if not is_new %}` — ver detalle en la decisión de
  arquitectura #2 arriba. Cubrir con journey read-only que abra el builder de un curso
  con una lección "Asistencia" YA existente y confirme que el `<select>` la sigue
  mostrando/seleccionando correctamente.
- **Migraciones nuevas SOLO se corren vía pipeline de deploy** (`deploy_gate.py`),
  nunca `manage.py migrate` manual contra el proxy prod — la migración 0022 se
  verifica en F3 contra `settings_test`/SQLite local, se aplica en prod recién en el
  job `migrate` del deploy.

## Validación esperada (qa_claude smoke + instrucciones cliente)

QA users con rol real ya sembrados (`secrets/SD.env`): `SD_QA_ADMIN_USER`
(ADMINISTRADOR), `SD_QA_COORDINADOR_USER` (COORDINADOR), `SD_QA_EJECUTOR_USER`
(EJECUTOR) — permite validar el RBAC (punto 4 del issue) con roles reales, no con
superuser. Login `/accounts/login/`, campo `username` (allauth, mismo patrón que
`journeys/SD.yaml`).

Smoke / journeys (ver `journeys/SD_63.yaml` del RUN):
- (a) `courses:attendance_reports` — visible y HTTP 200 para Coordinador/Administrador,
  403/redirect para Ejecutor; el link del navbar aparece/no aparece según rol.
- (b) Curso real de prod (id=63, "INDUCCIÓN PODA Y TALA", 2 enrollments con
  `completion_signature` ya cargado) → gate bloquea el PDF (campos nuevos vacíos) →
  completar Proyecto/Tipo de actividad/Instructor vía `course_edit_params` → reintentar
  → PDF 200, `content-type application/pdf`, tamaño razonable, roster con 2 filas.
- (c) Builder: crear lección nueva no ofrece "Asistencia" en el selector; editar una
  lección "Asistencia" ya existente sí la conserva.
- Crawl maestros post-deploy: lista cursos + detalle curso + admin-courses (parametrización)
  + nueva lista/detalle de asistencia (HTTP 200 en todo).

## Instrucciones de validación cliente (para comentario F6)

1. Entrar como Coordinador o Administrador → menú "Operaciones" (desktop) o menú
   móvil → "📋 Asistencia por Curso" → confirmar que aparece el link (y que un
   Ejecutor/alumno NO lo ve).
2. Abrir un curso real, ir a "Parametrización" → completar Proyecto, Tipo de
   actividad e Instructor asignado del curso (campos nuevos).
3. Desde "Asistencia por Curso" → abrir ese curso → "Descargar PDF" → confirmar que
   el PDF trae encabezado (Fecha/Instructor+firma/Proyecto/Tema/Objetivo/Tipo de
   actividad/Tiempo), tabla con columna Cargo, y el pie "Eficacia de la capacitación".
   **Pedimos explícitamente que comparen este PDF contra el formato físico
   FT-HSEQ-60 V04 real** — no tuvimos acceso a un adjunto/foto del documento
   original, así que el layout se construyó desde la descripción escrita del issue;
   cualquier ajuste de orden/espaciado visual lo hacemos en una vuelta corta.
4. Confirmar que un curso SIN esos campos completos NO permite descargar el PDF y en
   su lugar redirige con el mensaje de qué falta completar.
5. Abrir el constructor de un curso nuevo → confirmar que el tipo de lección
   "Asistencia" ya no aparece como opción (para no volver a crear duplicados) — y que
   una lección "Asistencia" que ya existía de antes se sigue viendo/editando normal.
