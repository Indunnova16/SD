# PLAN — RBAC de 3 roles de acceso x 5 módulos (issue #58)

**Fecha:** 2026-07-06
**Issue:** [Indunnova16/SD#58](https://github.com/Indunnova16/SD/issues/58)
**Estado:** Planning completado (F2), listo para ejecución (F3) — v1.0 COMPLETA, sin partir en sprints (autorización explícita de Miguel 2026-07-06, ver `../../SPRINTS/RUN_2026-07-06_1104/DECISIONES_MIGUEL.md`)

## Contexto

Hoy NO existe ningún RBAC de 3 niveles en SD (LMS). El único control de acceso real es
`request.user.is_staff` (auto-set solo para `job_profile.code == "ADMINISTRADOR"` en
`User.save()`), repetido como `if` ad-hoc en ~25 sitios de `accounts/views.py` y
`courses/views.py`, más variantes (`staff_member_required`, `user_passes_test(is_staff)`,
comparaciones `X != request.user and not request.user.is_staff`) dispersas en
`certifications`, `preop_talks`, `lessons_learned`, `attendance`, `reports` y `gamification`.
El navbar solo esconde 3 de los 5 ítems de "Sistema" tras ese mismo flag; "Reportes y
Analytics" y "Notificaciones" están HOY visibles a cualquier autenticado pese a estar
listados dentro del dropdown "Sistema".

Se implementa v1.0 completa: (1) campo `rol` de acceso (Ejecutor/Aprendiz, Coordinador,
Administrador) persistido en `User`, independiente de `job_profile`, con selector
prellenado-pero-editable en Crear/Editar Usuario y soporte en import/export masivo;
(2) capa de gating reusable por rol que reemplaza TODOS los checks ad-hoc de `is_staff`
(no solo los ~25 de accounts/courses — ver nota de alcance abajo); (3) navbar
desktop+mobile que oculta módulos según rol; (4) filtrado de datos por rol dentro de
Aprendizaje/Certificados/Operaciones/Gamificación/Sistema, incluyendo corregir los gaps
de seguridad reales encontrados (reports admin dashboard sin gate, `NotificationTemplateViewSet`
API sin gate real).

## Decisiones de Miguel incorporadas (HITL 2026-07-06)

1. `rol` es un **campo real e independiente** de `job_profile` en el modelo `User`
   (no derivado en runtime). Prellenado sugerido según mapeo, campo editable.
2. `COORDINADOR_VIZ` (job_profile) y el nuevo rol `Coordinador` quedan **separados**.
   `job_profile` nunca se usa en un chequeo de permisos nuevo — `rol` es la única fuente
   de verdad.
3. **No existe modelo de equipo/cuadrilla** en ningún nombre (ver evidencia abajo) →
   se agrega FK simple auto-referencial `User.supervisor` (NO modelo `Team` separado).
4. La restricción "Sistema = Administrador-only" aplica **solo** a pantallas de
   administración/config (gestión usuarios, parametrización, reportes cruzados de TODOS
   los usuarios, plantillas de notificación) — **nunca** a la bandeja personal de
   notificaciones ni a vistas de "mis propios datos".

## Evidencia de verificación (F2, antes de codear)

- **Búsqueda de "equipo" exhaustiva** (case-insensitive, TODAS las apps, no solo
  accounts/courses): `grep -rIn -i -E 'cuadrilla|crew|equipo|team' apps/*/models.py` →
  0 modelo de pertenencia real. El único hit de "TEAM" es
  `apps/gamification/models.py:303,394` — un `TextChoices` de **scope de leaderboard**
  (`Leaderboard.Scope.TEAM`), sin ninguna FK que agrupe usuarios; no es reusable como
  relación Coordinador↔Ejecutores. `UserContract` (accounts/models.py:358) es asignación
  usuario↔contrato de cliente (ej. ISA), M:N sin jerarquía de supervisión. **Confirmado
  camino B**: FK `supervisor` nueva en `User`.
- **`job_profile` es FK dinámica, no enum estático.** El campo real
  (`apps/accounts/models.py:114 job_profile = models.ForeignKey(...)`) apunta a
  `courses.JobProfileType` (tabla `job_profile_types`), NO al
  `class JobProfile(models.TextChoices)` definido en el mismo archivo (líneas 62-74) —
  ese enum es **código muerto** (0 referencias fuera de su propia definición, confirmado
  por grep; la migración `0012_remove_old_job_profile.py` documenta el reemplazo
  histórico). **No confundir ni reutilizar ese enum** al construir el mapeo de
  sugerencia — hay que leer los `code` reales de `job_profile_types`.
- **🔴 Hallazgo nuevo — códigos de `job_profile` no cubiertos por el mapeo de Miguel.**
  Consulta a `job_profile_types` (BD, proxy `127.0.0.1:5434/sd_lms`) devuelve **12 códigos
  activos**, 4 más de los que el mapeo de Miguel contempla:
  `LINIERO, TECNICO, OPERADOR, JEFE_CUADRILLA, INGENIERO_RESIDENTE, COORDINADOR_HSEQ,
  ADMINISTRADOR, CAPATAZ, "TODOS LOS CARGOS", CONTRATISTA, CONDUCTOR, COORDINADOR_VIZ`.
  El mapeo de Miguel (decisión #1) solo cubre 7 de estos. `CAPATAZ` en particular es
  ambiguo (rol de mando de cuadrilla, similar a `JEFE_CUADRILLA`) — **no se adivina**:
  se trata igual que `COORDINADOR_VIZ` (sin sugerencia automática, requiere elección
  explícita del admin), extendiendo el mismo precedente que Miguel ya fijó para el caso
  análogo. Igual tratamiento para 1 usuario con `job_profile` NULL detectado en BD.
  **Miguel: si tenés una opinión distinta sobre dónde cae `CAPATAZ`/`CONTRATISTA`/
  `CONDUCTOR`/`TODOS LOS CARGOS`, es un ajuste de una línea en el dict de mapeo — no
  bloquea la ejecución.**
- **Conteo real BD (script/dev, `sd_lms`, 10 usuarios):** LINIERO=5, "TODOS LOS
  CARGOS"=2, ADMINISTRADOR=1, COORDINADOR_HSEQ=1, NULL=1. Confirma que el backfill debe
  manejar el caso NULL y el caso "código fuera del mapeo conocido" como primera clase,
  no como excepción rara.
- **Notificaciones — separación confirmada por código, no por suposición.**
  `apps/notifications/views.py` (6 vistas: `notification_list`, `notification_items`,
  `mark_read`, `mark_all_read`, `unread_count`, `preferences`) están **100% filtradas
  por `request.user`** — es la bandeja personal, ninguna requiere cambio. El único
  surface "Sistema" real de Notificaciones es
  `apps/notifications/api/views.py::NotificationTemplateViewSet` (DRF, gestiona
  `NotificationTemplate` — el CRUD de plantillas que sí es config admin), hoy con
  `permission_classes = [permissions.IsAuthenticated]` — **gap real**: cualquier
  autenticado puede crear/editar/borrar plantillas de notificación vía API. No tiene UI
  que la enlace hoy, pero es API alcanzable.
- **Reportes — separación confirmada por código.** De las 18 vistas en
  `apps/reports/views.py`, 10 son "Reportes y Analytics" cross-usuario sin gate
  (`admin_dashboard`, `dashboard_stats`, `compliance_chart`, `training_trend`,
  `expiring_certs`, `overdue_assignments`, `recent_activity`, `course_progress`,
  `course_type_distribution`, `assessment_performance` — **gap real, confirma lo que
  F1 ya había marcado**); 3 (`scheduled_list/create/toggle`) ya tienen
  `@user_passes_test(is_staff)` (se migran al nuevo helper por consistencia); 5
  (`report_list`, `generate_report`, `my_reports`, `report_status`, `delete_report`)
  son **personales** (`generated_by=request.user` / `filter(..., generated_by=request.user)`)
  — sin cambio, según decisión #4.
- **Navbar — confirmación de líneas exactas** (`templates/partials/navbar.html`):
  desktop dropdown "Sistema" (líneas 143-165): `{% if user.is_staff %}` en 146 cubre
  "Gestión de Usuarios" (148) y "Parametrización" (151); el bloque se cierra ANTES de
  "📊 Reportes y Analytics" (155) y "🔔 Notificaciones" (158) — ambos quedan sin gate;
  se reabre `{% if user.is_staff %}` en 161 para "Manual de Administrador" (163). Mismo
  patrón duplicado en el menú mobile (líneas 297-325).

## Nota de alcance — extensión necesaria de Capa 0.5 (decisión del planner)

F1 acotó la Capa 0.5 (gating reusable) a "reemplaza ~25 ifs en `accounts/views.py` y
`courses/views.py`". Verificado en código: hay chequeos `is_staff`-equivalentes
**adicionales** en `certifications/views.py` (bypass de ownership), `preop_talks/views.py`
(bypass de ownership), `lessons_learned/views.py` (bypass de ownership),
`attendance/views.py` (`_staff_required` propio), `reports/views.py`
(`user_passes_test(is_staff)`) y `gamification/views.py`
(`@staff_member_required` — decorator built-in de Django admin, no el custom). **Se
extiende el alcance de A4 a los 8 archivos**, no solo 2 — razón: dejar `is_staff` como
árbitro en unos sitios y `rol` en otros crea una inconsistencia real (decisión #1 hace
`rol` independiente de `job_profile`; un usuario con `rol=Administrador` pero
`job_profile≠ADMINISTRADOR` no tendría `is_staff=True` y quedaría bloqueado de los
bypass de ownership que aún miren `is_staff`). Migrar todo a `rol` es la única forma de
cumplir la decisión #2 ("`rol` es la ÚNICA fuente de verdad") de punta a punta.

## Sub-items — v1.0 completa (un solo sprint, sin partir)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Modelo: campo `rol` (choices EJECUTOR/COORDINADOR/ADMINISTRADOR) + FK auto-referencial `supervisor` en `User` + migración schema + migración de datos backfill (mapeo `job_profile.code`→`rol` sugerido; códigos fuera del mapeo conocido y NULL → sin asignar, requiere revisión admin) | `apps/accounts/models.py`, `apps/accounts/migrations/0015_user_rol_supervisor.py` (schema), `apps/accounts/migrations/0016_backfill_user_rol.py` (data, con `RunPython` + reporte de conteo por bucket al final) | Unit: choices válidas, `clean()` rechaza `supervisor == self`, backfill mapea cada uno de los 12 códigos reales de `job_profile_types` (incluido NULL) al bucket correcto | - | high | ⏳ pendiente |
| A2 | Selector de `rol` + `supervisor` en Crear/Editar Usuario, con prellenado JS/server-side según mapeo (misma tabla que A1); `COORDINADOR_VIZ`/`CAPATAZ`/`TODOS LOS CARGOS`/`CONTRATISTA`/`CONDUCTOR`/sin perfil → sin prellenado, obliga elección explícita (validación en `clean()`) | `apps/accounts/forms.py` (`UserCreateForm`, `UserEditForm`), `templates/accounts/user_create.html`, `templates/accounts/user_edit.html`, `templates/accounts/partials/user_form.html` | Form: prellenado por cada job_profile mapeado, error si bucket "sin sugerencia" se envía vacío, `supervisor` queryset limitado a `rol in (COORDINADOR, ADMINISTRADOR)` | A1 | medium | ⏳ pendiente |
| A3 | Import/export masivo con `rol` (columna opcional `rol_acceso`) y `supervisor` (columna opcional `supervisor_documento`); mismo fallback de sugerencia que A2; export incluye ambas columnas | `apps/accounts/services.py` (`BulkUploadService.OPTIONAL_COLUMNS`, `ROL_MAP`, `ExportService` headers) | Bulk: fila con `rol_acceso` explícito, fila sin columna cae al mapeo sugerido, fila con job_profile "sin sugerencia" y sin `rol_acceso` → error de validación listado en el reporte de importación; export trae las 2 columnas nuevas | A1, A2 | medium | ⏳ pendiente |
| A4 | Utilidad de gating reusable `apps/accounts/permissions.py`: `require_rol(*roles)` (decorator function-view), `RolRequiredMixin` (CBV), `user_has_rol(user, *roles)` — lee **solo** `user.rol`, nunca `job_profile` ni `is_staff`. Migra TODOS los checks admin-equivalentes de los 8 archivos (ver Nota de alcance) | `apps/accounts/permissions.py` (nuevo), `apps/accounts/views.py`, `apps/courses/views.py`, `apps/certifications/views.py`, `apps/preop_talks/views.py`, `apps/lessons_learned/views.py`, `apps/attendance/views.py`, `apps/reports/views.py`, `apps/gamification/views.py` | Unit: decorator/mixin allow/deny por rol (3 roles x acción); regresión: usuarios backfillados a `rol=ADMINISTRADOR` (ex-`is_staff`) siguen pasando todos los checks migrados | A1 | high | ⏳ pendiente |
| A5 | Navbar desktop+mobile: `{% if user.is_staff %}` → `{% if user.rol == 'ADMINISTRADOR' %}` en los 3 sitios ya gateados (Gestión Usuarios, Parametrización, Manual Admin) + envolver "📊 Reportes y Analytics" (gap real, hoy sin gate); "🔔 Notificaciones" **NO se gatea** (decisión #4, queda visible a todo rol autenticado) | `templates/partials/navbar.html` (líneas 107,143-165,196,297,309-325) | Template: render con 3 fixtures de rol (Ejecutor/Coordinador/Administrador), assert presencia/ausencia por texto de cada ítem; assert explícito de que "Notificaciones" aparece para los 3 roles | A4 | medium | ⏳ pendiente |
| A6 | Filtrado Aprendizaje: Ejecutor ve solo cursos/rutas/evaluaciones de su `job_profile` (via `target_profiles`); Coordinador/Admin ven todo | `apps/courses/views.py` (`course_list`), `apps/learning_paths/views.py`, `apps/assessments/views.py` | Ejecutor ve subconjunto, Coordinador ve superset (incluye cursos de otros perfiles), Admin ve todo | A4 | medium | ⏳ pendiente |
| A7 | Filtrado Certificados: propio (Ejecutor) / equipo vía `supervisor` FK (Coordinador) / todos (Admin). `certificate_detail` migra bypass `is_staff`→`rol` | `apps/certifications/views.py` (`my_certificates`, nueva vista/parámetro `equipo`, `certificate_detail`) | Coordinador ve certificados de usuarios con `supervisor=coordinador`, NO ve los de otro Coordinador; Ejecutor solo los propios | A1 (FK), A4 | medium | ⏳ pendiente |
| A8 | Filtrado Operaciones: listado/gestión oculto para Ejecutor (Coordinador/Admin completo) en `preop_talks`/`lessons_learned`/`attendance` — **cuidado**: NO ocultar las vistas donde el Ejecutor participa de su propia charla/asistencia (`talk_conduct`, `sign_attendance`, `complete_talk`, check-in facial), solo el listado administrativo (`talk_list`, `lesson_list`, `face_event_list`) | `apps/preop_talks/views.py` (`talk_list`), `apps/lessons_learned/views.py` (`lesson_list`), `apps/attendance/views.py` (`face_event_list`) | Ejecutor: 403 en listado admin, 200 en su propia firma/charla; Coordinador/Admin: 200 en ambos | A4 | medium | ⏳ pendiente |
| A9 | Filtrado Gamificación: propio (dashboard personal, sin cambio) / equipo vía `supervisor` FK (Coordinador, vista nueva) / todo (`admin_dashboard`/`admin_analytics`/`admin_top_earners`, migran `@staff_member_required`→`require_rol(ADMINISTRADOR)`) | `apps/gamification/views.py` | Coordinador ve ranking/puntos de su equipo; Admin ve `admin_analytics` completo; Ejecutor bloqueado de vistas admin | A1 (FK), A4 | medium | ⏳ pendiente |
| A10 | Sistema — lockdown Administrador + corrección de 2 gaps reales: (a) 10 vistas cross-usuario de `reports/views.py` (`admin_dashboard` + 9 más) → `require_rol(ADMINISTRADOR)`; 3 `scheduled_*` migran de `is_staff` al mismo helper; 5 vistas personales (`my_reports` etc.) **sin cambio**. (b) `NotificationTemplateViewSet.permission_classes` → permission class DRF custom que exige `request.user.rol == ADMINISTRADOR`; `notifications/views.py` (bandeja personal) **sin cambio** | `apps/reports/views.py`, `apps/notifications/api/views.py` (+ `apps/notifications/api/permissions.py` nuevo si se prefiere aislar la permission class) | Reports admin: 403 Ejecutor/Coordinador, 200 Admin; API templates: 403 no-Admin, 200 Admin; regresión: `my_reports`/`report_status` siguen 200 para cualquier rol autenticado | A4 | high | ⏳ pendiente |
| A11 | Regresión contra datos legacy + smoke E2E autenticado (3 roles) + instrucciones de validación cliente | Suite `pytest` completa; journey `$RUN_DIR/journeys/SD_58.yaml` | `pytest` verde completo incl. ≥1 registro legacy por bucket de rol backfillado; E2E Playwright con 3 usuarios de prueba (uno por rol) recorriendo navbar + 1 vista filtrada por módulo | A1–A10 | medium | ⏳ pendiente |

## DAG dependencias

```
A1 → A2 → A3
A1 → A4
A4 → A5
A4 → A6
A1,A4 → A7
A4 → A8
A1,A4 → A9
A4 → A10
A1..A10 → A11
```

Orden de ejecución sugerido para F3: `A1, A4` (paralelizable entre sí NO — A4 no depende
de A2/A3 pero conviene después de A1 para tener el campo disponible en tests) →
`A2, A3, A5, A6, A8, A10` (paralelizables entre sí) → `A7, A9` (requieren FK `supervisor`
poblado en fixtures) → `A11` (cierre).

## Riesgos y mitigaciones

- **Backfill con códigos fuera de mapeo (CAPATAZ/TODOS LOS CARGOS/CONTRATISTA/CONDUCTOR/NULL, 3 de 10 usuarios reales en BD dev).** Mitigación: estos usuarios quedan con `rol` sin asignar tras el backfill (no se adivina) + el propio `RunPython` imprime al final un reporte "N usuarios requieren asignación manual de rol" para que Administrador los revise post-deploy vía la UI de A2. No bloquea el deploy (campo nullable temporalmente hasta asignación, o default más restrictivo EJECUTOR con flag `rol_requiere_revision` — a decidir en A1 con la opción más simple: dejar `rol` nullable y el gating (A4) trata `rol is None` como "sin permisos elevados", equivalente a Ejecutor por defecto de seguridad).
- **Inconsistencia `is_staff` vs `rol` en el período de transición.** Mitigado por la extensión de alcance de A4 (Nota de alcance arriba) — se migra TODO en la misma pasada, no queda una mitad en `is_staff` y otra en `rol`.
- **Enum muerto `User.JobProfile` (TextChoices, líneas 62-74) puede confundirse con el nuevo `User.Rol`.** Mitigación: nombrar la nueva clase explícitamente `class Rol(models.TextChoices)` (no reusar el nombre `JobProfile`) y no tocar/eliminar el enum muerto en este issue (fuera de scope, otro issue de limpieza).
- **`CAPATAZ` es semánticamente ambiguo (podría razonablemente ir a Coordinador, no Ejecutor).** Mitigación: tratado como "sin sugerencia automática" (no se asume), Miguel puede ajustarlo en una línea del dict antes de F3 si tiene una opinión — no bloquea.
- **Ownership-bypass checks migrados (A4) podrían cambiar comportamiento sutil si algún flujo dependía de `is_staff` para algo NO relacionado con "es Administrador" (ej. Django admin site access).** Mitigación: `is_staff` en sí NO se toca ni se remueve del modelo — sigue existiendo y sigue auto-asignándose por `job_profile==ADMINISTRADOR` (para acceso a `/admin/` de Django); solo se deja de usar como fuente de verdad en los checks de negocio migrados.

## Validación esperada (smoke prod / qa_claude)

- Login como 3 usuarios QA (uno por `rol`: Ejecutor, Coordinador, Administrador) contra
  `$LOGIN_PATH`.
- Navbar: Ejecutor NO ve "Sistema" ni "Gestión de Usuarios"/"Parametrización"/"Reportes y
  Analytics"/"Manual de Administrador"; SÍ ve "🔔 Notificaciones" (los 3 roles).
- Crear/editar usuario: selector `rol` prellenado según `job_profile` elegido, editable.
- Import masivo: plantilla exportada trae columna `rol_acceso`; import con y sin esa
  columna se comporta según A3.
- Certificados/Gamificación: Coordinador de prueba con ≥1 Ejecutor asignado vía
  `supervisor` ve esos certificados/puntos en la vista "equipo".
- Reportes/Notificaciones Sistema: Ejecutor/Coordinador reciben 403 en
  `reports:dashboard` y en la API `notifications` templates; Administrador 200 en ambos.
- Contra ≥1 registro/usuario legacy ya en BD (no solo fixtures QA nuevas).
