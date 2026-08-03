# PLAN — SD#63 (reproceso bounce=2): logo+color corporativo, columna "Fecha de firma" y PDF Individual

**Fecha:** 2026-07-27
**Issue:** [Indunnova16/SD#63](https://github.com/Indunnova16/SD/issues/63)
**RUN:** RUN_2026-07-27_1514 (F1 triage completo, `agents/SD_63_f1.json`)
**Estado:** Planning completado, listo para ejecución (F3, `sprint_path`)
**Branch:** UNA branch consolidada — el scope real de esta vuelta (branding de 2
templates + 1 columna + 1 feature nueva que reusa el template ya branded) es una
v1.0 coherente, no se justifica partir en sub-branches.

## Contexto — por qué esta es la 3ª vuelta del mismo issue

Bounce 1 (cerrado, post-mortem `FIX_INCOMPLETO/validado_1_registro`): se cerró
contra la descripción del issue sin el DOCX oficial. Bounce 2 (2026-07-22,
`PLAN_2026-07-20_asistencia_automatica_pdf_hseq60.md`): corrigió con rigor las 5
desviaciones de formato del oficial FT-HSEQ-60 (blanco y negro, casillas de tipo
de actividad, 5 columnas exactas sin "Estado", sin bandas azules, sin "Resumen de
Asistencia", Eficacia completa) — ese trabajo fue correcto, NO se toca ni se
repite. Esta 3ª vuelta atiende lo que una sesión de validación EN VIVO (2026-07-23,
con Andrea y Linda) reveló que ningún documento estático exponía: fecha de firma
visible en el PDF (no solo en pantalla), 2 modalidades de descarga (Grupal +
Individual), MÁS un pedido nuevo en paralelo de branding (logo real + rojo
corporativo `#e4020f`) que emergió porque SD#69 (branding portafolio-wide,
mergeado el mismo día) excluyó deliberadamente estos 2 templates de asistencia de
su scope, delegándolos a este issue.

**Punto 6 del comentario del cliente (UX de validación de campos) queda
explícitamente FUERA de este RUN** — indefinición genuina de producto ("sigue
pendiente definir"), no se codea a ciegas. Se declara `ℹ️ decisión de scope
pendiente` en el cierre, nunca `✅`.

## Grounding verificado en el código real (2026-07-27, no solo el análisis de F1)

- `_build_course_attendance_summary(course)` (`apps/courses/views.py:2271-2338`) y
  `_build_attendance_summary(course, lesson)` (`:2204-2268`) ya traen `signed_at`
  en cada fila de `rows` — confirmado leyendo el código, no solo el número de
  línea de F1 (F1 decía "línea 2320", el campo real vive en el diccionario armado
  entre 2312-2323, dentro del rango — sin discrepancia material).
- `templates/courses/course_attendance_pdf.html` (268 líneas) y
  `templates/courses/attendance_pdf.html` (261 líneas) hoy son 100% blanco y negro
  (`#1a1a1a`/`#d1d5db`/`#666`), CERO referencia a `#e4020f` ni a ningún `<img>` de
  logo — confirmado con `grep`, no hay nada parcialmente hecho que reutilizar en
  estos 2 archivos.
- `templates/courses/course_attendance_report_detail.html` (vista on-screen, no
  PDF) **YA TIENE** la columna "Fecha de firma" (`{{ row.signed_at|date:"d/m/Y H:i" }}`)
  desde el bounce anterior — confirma la lectura de F1: el dato y su render on-screen
  ya existen, el gap es específicamente en el PDF.
- El asset de logo de alta resolución
  `apps/certifications/migrations/assets/sd_sas_logo_v2_real.png` (1800×1200 PNG,
  MD5 `9148226dea74ef3fea2d7044e7d381a8`) **SÍ estará presente en el contenedor de
  Cloud Run en runtime** — confirmado leyendo `Dockerfile` (`COPY --chown=appuser:appuser . .`,
  sin exclusión de `apps/**/migrations/assets` en `.dockerignore`) y `git ls-files`
  (el archivo está trackeado en git). Esto **de-riesga la técnica de A1**: no
  depende de collectstatic, WhiteNoise, GCS ni ninguna resolución de URL — es una
  lectura de archivo local en disco en tiempo de request, con fallback silencioso
  si el archivo no está (nunca un 500).
- **`base64` ya está importado en `apps/courses/views.py:5`** (usado hoy para
  decodificar la firma dibujada a mano en canvas) y `settings.BASE_DIR` está
  disponible vía `from django.conf import settings` (`:8`, ya importado) — cero
  imports nuevos para A1.
- Precedente real en el repo de "agregar `#e4020f` a un PDF xhtml2pdf sin logo":
  `templates/accounts/user_profile_pdf.html` (SD#69) ya usa `#e4020f` en
  border-bottom/color/background-color — confirma que el motor sí renderiza ese
  color en PDF sin problema. Pero **ese archivo NO tiene ningún `<img>`** — no hay
  precedente de embeber una imagen real en un PDF xhtml2pdf de este repo; la
  técnica base64 data-URI de A1 es nueva, sin precedente 1:1 a copiar (certifications
  usa WeasyPrint con `.url` directo, no aplica al motor xhtml2pdf de courses).
- URLs confirmadas en `apps/courses/urls.py:71-84`: `attendance-reports/` (lista),
  `attendance-reports/<int:course_id>/export-pdf/` (Grupal),
  `attendance-reports/<int:course_id>/` (detalle) — el patrón para el Individual
  nuevo es `attendance-reports/<int:course_id>/export-pdf/<int:user_id>/`.

### ⚠️ HALLAZGO CRÍTICO de este F2 — conflicto real no detectado por F1

`apps/courses/tests/test_issue_63.py` (1185 líneas, del bounce 2) tiene **2 tests
que EXPLÍCITAMENTE bloquean el sub-item 3** (columna "Fecha de firma") si no se
actualizan en el mismo cambio:

- `CourseAttendancePdfOfficialFormatTests.test_happy_path_firmantes_5_columnas_exactas_sin_estado`
  (línea ~952): asserta que la tabla de firmantes tiene **exactamente 5 columnas**
  (No./Nombre completo/Cédula/Cargo/Firma).
- `LegacyAttendancePdfOfficialFormatTests.test_happy_path_firmantes_5_columnas_exactas`
  (línea ~1052): además tiene **`self.assertNotIn("Fecha y hora de firma", html)`
  literal** — una aserción NEGATIVA explícita contra tener esa columna.

Estos tests son la corrección CORRECTA de bounce 2 (el oficial FT-HSEQ-60 tiene 5
columnas, no 6) — no son un bug a ignorar. Pero el cliente ahora pide
explícitamente (comentario 2026-07-23T21:37:46Z, punto 4) una 6ª columna con la
fecha de firma, que el oracle DOCX físico no tiene. Es una extensión deliberada
más allá del formato oficial (dato de auditoría útil que el papel no captura), no
una regresión. **Ambos tests deben actualizarse en el MISMO commit que agrega la
columna** (de "5 columnas exactas" a "6 columnas exactas incluyendo Fecha de
firma", y quitar/invertir el `assertNotIn` del legacy) — si F3 agrega la columna
sin tocar estos tests, el test suite queda ROJO y expone contradicción consigo
mismo. Se documenta explícitamente para que F3 no lo pase por alto ni lo
interprete como "test viejo a ignorar".

También hay que actualizar el `colspan="5"` de la fila `{% empty %}` (sin
inscritos) a `colspan="6"` en AMBOS templates (`course_attendance_pdf.html:241`,
`attendance_pdf.html:217`).

## ⚠️ Decisión de arquitectura tomada en este F2

**PDF Individual reusa `course_attendance_pdf.html` parametrizado (rows=[1 fila] +
flag `is_individual`), NO se crea un template nuevo
`course_attendance_pdf_individual.html`.** F1 dejó esto como "decisión de F3"; se
resuelve ahora en la descomposición porque afecta directamente el DAG y el orden
de sub-items:

- Evidencia/razón: si se crea un 3er archivo HTML con el mismo layout, HAY QUE
  aplicarle el logo+color+columna una TERCERA vez — exactamente el patrón que
  causó bounce 1 ("arreglar una superficie y dejar otra vieja"), ahora replicado
  a un archivo que ni siquiera existe todavía. Reusar el template ya corregido en
  A2 hace que el Individual herede branding + columna GRATIS, con cero riesgo de
  divergencia futura entre Grupal e Individual (mismo archivo = imposible que
  diverjan).
- Mecanismo: la vista nueva arma el mismo `context` de `export_course_attendance_pdf`
  pero con `rows` filtrado a 1 enrollee (`404` si el `user_id` no está inscrito en
  ese curso) y agrega `"is_individual": True`. El template añade un único
  `{% if is_individual %}` en el `<h1>`/`<title>` para decir "Lista de Asistencia
  Individual" en vez de "por Curso" — cambio quirúrgico de 2-3 líneas, no una
  bifurcación de layout.
- Consecuencia en el DAG: **A4 (Individual) depende de A2 (Grupal ya branded +
  columna)**, no puede ir en paralelo con A2 sin arriesgar tener que retocar el
  mismo template dos veces.

Ninguna de estas decisiones toca datos de producción ni requiere migración (no
hay campos de modelo nuevos en esta vuelta — a diferencia del bounce de
2026-07-20, que sí agregó 3 campos a `Course`).

## Sub-items (Sprint A — deployable_solo: false, bundle único v1.0 coherente)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Helper compartido `_attendance_pdf_branding_context()` en `views.py` (cerca de `_resolve_attendance_responsable`): lee `settings.BASE_DIR / "apps/certifications/migrations/assets/sd_sas_logo_v2_real.png"`, lo codifica base64, arma `data:image/png;base64,...`. Envuelto en `try/except (FileNotFoundError, OSError)` → si falla, `logo_data_uri=""` (el PDF sigue generándose sin logo, nunca un 500). Devuelve `{"logo_data_uri": ..., "brand_accent": "#e4020f"}`. Se llama UNA vez desde cada una de las 3 vistas PDF (`export_attendance_pdf`, `export_course_attendance_pdf`, la nueva Individual) y se mergea al `context` existente. | `apps/courses/views.py` | unit: data URI empieza con `data:image/png;base64,` y decodifica a PNG válido (magic bytes `\x89PNG`); `brand_accent == "#e4020f"`; edge: archivo simulado ausente (mock/patch de `open`) → `logo_data_uri==""` sin excepción | — | low | ⏳ pendiente |
| A2 | Grupal (`course_attendance_pdf.html` + `export_course_attendance_pdf`): (a) `<img src="{{ logo_data_uri }}">` en `.header` solo si `logo_data_uri` es verdadero (si vacío, header queda igual que hoy, sin ícono roto); (b) acento `#e4020f` SOLO en `border-bottom` del `.header`/color del `<h1>` — NUNCA `background-color` de banda (eso violaría la corrección ya validada de bounce 2, test `assertNotIn("#2563eb", html)` sigue vigente con OTRO hex); (c) agregar `<th>Fecha de firma</th>` (6ª columna) al `signers-table` + celda `{{ row.signed_at|date:"d/m/Y H:i" }}` con fallback `—` si `None`; (d) `colspan="5"→"6"` en la fila `{% empty %}`; (e) wire: `export_course_attendance_pdf` mergea `context.update(_attendance_pdf_branding_context())`. **Actualizar** `_course_pdf_context()` (helper de test) para incluir `logo_data_uri`/`brand_accent` con defaults sanos, y **actualizar** `test_happy_path_firmantes_5_columnas_exactas_sin_estado` → 6 columnas incluyendo "Fecha de firma" (ver hallazgo crítico arriba). | `templates/courses/course_attendance_pdf.html`, `apps/courses/views.py`, `apps/courses/tests/test_issue_63.py` | happy: logo embebido (`assertIn("data:image/png;base64,", html)`), acento presente (`assertIn("#e4020f", html)`), columna Fecha de firma con valor real; edge: `row.signed_at is None` → "—" sin error; edge: `logo_data_uri=""` (asset ausente simulado) → HTML válido sin logo; regresión: `assertNotIn("#2563eb", html)` sigue pasando (bounce 2 intacto) | A1 | medium | ⏳ pendiente |
| A3 | Legado (`attendance_pdf.html` + `export_attendance_pdf`): mismo tratamiento (a)-(e) que A2, aplicado al template legacy per-lección — evita repetir el patrón exacto de bounce 1 (corregir solo el flujo nuevo y dejar el legacy sin logo/color/columna). **Actualizar** `_legacy_pdf_context()` + **actualizar** `test_happy_path_firmantes_5_columnas_exactas` (quitar/invertir `assertNotIn("Fecha y hora de firma", html)`, pasar a 6 columnas). Auditado `test_attendance_pdf.py` (archivo de tests MÁS viejo, pre-existente): sin conflictos de columnas/color/logo sobre este mismo template — confirmado con grep, no requiere cambios ahí. | `templates/courses/attendance_pdf.html`, `apps/courses/views.py`, `apps/courses/tests/test_issue_63.py` | mismos casos que A2 adaptados a `_legacy_pdf_context`/`row.user.job_position` (el dict de fila de `_build_attendance_summary` NO trae `job_position` como key directa, a diferencia del builder course-level — patrón existente, no se cambia) | A1 | medium | ⏳ pendiente |
| A4 | PDF Individual — vista nueva `export_course_attendance_pdf_individual(request, course_id, user_id)`: reusa `_attendance_export_required` (mismo gate ADMINISTRADOR+COORDINADOR) + `_build_course_attendance_summary(course)` filtrado a la fila cuyo `user.id == user_id` (`404` si no está entre los enrollees de ESE curso — no solo `User.DoesNotExist` global, filtrar sobre `rows` ya construido). Reusa `course_attendance_pdf.html` con `rows=[fila_única]` + `is_individual=True` (ver decisión de arquitectura arriba — NO template nuevo). URL `attendance-reports/<int:course_id>/export-pdf/<int:user_id>/`, name `export_course_attendance_pdf_individual`. Filename `asistencia_individual_curso_{course.id}_{user_id}_{fecha}.pdf`. Botón "Descargar individual" por fila en `course_attendance_report_detail.html` (roster table, junto a cada fila) → enlaza a la nueva URL. | `apps/courses/views.py`, `apps/courses/urls.py`, `templates/courses/course_attendance_pdf.html` (flag `is_individual`), `templates/courses/course_attendance_report_detail.html` | happy: `user_id` inscrito → 200, `content-type application/pdf`, HTML fuente con exactamente 1 fila de firmante; edge: `user_id` NO inscrito en ESE curso (pero existe en otro) → 404, no 500 ni PDF vacío; edge: RBAC — EJECUTOR bloqueado igual que el Grupal; regresión: el endpoint Grupal (A2) sigue devolviendo TODAS las filas, no se filtra por accidente | A2 | medium-high | ⏳ pendiente |
| A5 | Tests consolidados + smoke E2E: correr pytest completo de `test_issue_63.py` + `test_attendance_pdf.py` en verde (incluye las 2 actualizaciones del hallazgo crítico); journey E2E (`SD_63.yaml` de este RUN) contra curso(s) reales de prod con ≥2 inscritos (nunca 1 solo registro — causa raíz de bounce 1). | `apps/courses/tests/test_issue_63.py` | pytest verde, cobertura happy + ≥3 edge cases por sub-item | A2, A3, A4 | low-medium | ⏳ pendiente |

No hay Sprint B — el scope (branding 2 templates + 1 columna + 1 feature nueva
que reusa el template ya branded) es una sola v1.0 coherente; partirlo dejaría
Grupal branded y Legado sin tocar (o viceversa), que es literalmente el patrón de
bounce 1 que este mismo issue ya penalizó una vez.

## DAG dependencias

```
A1 (helper branding: logo base64 + #e4020f)
 ├─→ A2 (Grupal: logo+color+columna Fecha de firma, wire vista)
 │        A2 ─→ A4 (Individual: reusa el template YA branded de A2, evita 3er repeat)
 └─→ A3 (Legado: logo+color+columna Fecha de firma, wire vista) — paralelo a A2/A4
A2, A3, A4 ─→ A5 (tests consolidados + smoke E2E)
```

Orden sugerido F3 (`sprint_exec`):
1. **A1** primero (helper, bloquea A2/A3/A4).
2. A2 (Grupal) y A3 (Legado) — pueden ir en cualquier orden entre sí (archivos y
   vistas distintas), pero A2 debe completarse ANTES de A4.
3. A4 (Individual, reusa A2 ya branded).
4. A5 cierra: pytest completo + journey E2E.

## Gate "Enumeración de sitios" (paso 3.5 del prompt base F2)

No aplica: ningún sub-item quedó `epic` (todos low/medium/medium-high) y el
riesgo global se mantiene `medio` (mismo nivel que F1 estimó) — no hay elemento
que dispare `epic` ni `riesgo_global=alto` tras esta lectura de código real. No
se re-pregunta el gate de partir vs ir completos (Miguel ya aprobó `sprint_path`).

## Riesgos y mitigaciones

- **Conflicto con tests lock de bounce 2 (5 columnas exactas)** — ver hallazgo
  crítico arriba. Mitigación: actualización explícita de ambos tests en el MISMO
  commit que agrega la columna, documentado para que F3 no lo trate como "test
  legacy a ignorar" ni lo borre sin reemplazo (borrar el assert sin reemplazarlo
  por la versión de 6 columnas dejaría un agujero de regresión real).
- **Riesgo de reintroducir "bandas de color de fondo"** (lo que el cliente pidió
  quitar explícitamente en bounce 2) al mismo tiempo que se pide "logo y colores"
  (aparente contradicción, ver `ultimo_comentario_cliente.interpretacion` de F1).
  Mitigación: el acento `#e4020f` se aplica ÚNICAMENTE a `border-bottom`/`color`
  de texto de encabezado, nunca `background-color` de una tabla o sección — test
  de regresión explícito conserva `assertNotIn("#2563eb", html)` Y se agrega un
  assert equivalente de que NO aparece `background-color:\s*#e4020f` en las
  tablas de contenido (solo en el borde del header).
- **Asset del logo podría no existir en algún ambiente** (aunque confirmado
  presente en el Dockerfile/git). Mitigación: `try/except` en A1 con fallback a
  string vacío — el PDF nunca falla por esto, en el peor caso sale sin logo
  (degradación elegante, no 500).
- **`user_id` no inscrito en el PDF Individual** — filtrar mal (ej. buscar el
  `User` global en vez de filtrar sobre los `enrollments` de ESE curso
  específico) permitiría exportar un PDF "individual" de alguien que nunca tomó
  ese curso. Mitigación: el filtro se hace sobre `summary["rows"]` (ya acotado a
  `Enrollment.objects.filter(course=course)`), `404` explícito si no aparece ahí
  — cubierto con test edge dedicado (A4).
- **Layout del PDF Individual sin adjunto físico específico para 1-persona** — se
  reusa el mismo layout/columnas que el Grupal (issue lo pide explícitamente:
  "mismo layout/columnas... para mantener fidelidad FT-HSEQ-60"), por lo que no
  hay ambigüedad de diseño nueva a resolver — riesgo bajo.
- **Migraciones**: NINGUNA en esta vuelta (a diferencia del bounce de
  2026-07-20). Todos los campos usados (`signed_at`, `job_position`, `instructor`,
  `project_name`, `activity_type`, `objectives`) ya existen en el modelo desde el
  sprint anterior. Cero riesgo de migración.

## Checklist DoD

- [ ] Migration: **N/A** — no hay campos de modelo nuevos en esta vuelta.
- [ ] Backend: A1 (helper branding) + A4 (vista + URL Individual) + wiring de
  contexto en A2/A3.
- [ ] UI: A2 (template Grupal) + A3 (template Legado) + botón "Descargar
  individual" en `course_attendance_report_detail.html` (A4).
- [ ] Tests happy + edge cases: por sub-item, ver tabla arriba (A5 consolida).
- [ ] Test de regresión: bandas de color (`#2563eb`) siguen ausentes; 5→6
  columnas actualizado en ambos test files sin dejar el assert viejo huérfano.
- [ ] Smoke E2E: journey `SD_63.yaml` de este RUN (ver abajo), contra curso(s)
  reales con ≥2 inscritos.
- [ ] Instrucciones de validación cliente (para comentario F6, ver abajo).

## Validación esperada (smoke E2E + instrucciones cliente)

Journeys (ver `journeys/SD_63.yaml` de este RUN):
1. Grupal PDF (curso real, gate-completo, con ≥1 firma real) — reachable,
   `content-type application/pdf`, tamaño no-trivial. Verificación VISUAL de
   logo/color queda como limitación documentada del runner (igual que el
   journey anterior de este mismo issue documentó para el rediseño B/N, y como
   `user_profile_pdf.html`/SD#69 documentó para su propio caso) — el runner de
   `qa-prod` NO extrae texto/imágenes de binarios PDF vía Playwright/http_get,
   solo status/content-type/tamaño. F5/validación humana debe confirmar
   visualmente (pdftoppm o descarga directa) antes de declarar 🟢.
2. Legado PDF — mismo patrón sobre una lección `attendance` real ya existente.
3. PDF Individual (MUTATIVO — fixture propio, ya que es una feature sin
   precedente real en prod): fixture de curso + 2 enrollments (1 con
   `completion_signature`), happy path 200 para el user_id inscrito, 404 para un
   user_id no inscrito en ese curso, cleanup de la fixture al final.
4. RBAC — EJECUTOR bloqueado en los 3 endpoints PDF (Grupal/Legado/Individual),
   con foco en que el gate se extendió correctamente a la URL NUEVA de
   Individual (no cubierta por la regresión RBAC del bounce anterior, que solo
   conocía Grupal/lista/detalle).

## Instrucciones de validación cliente (para comentario F6)

1. Abrir "Asistencia por Curso" → un curso ya completo (con Proyecto/Tipo de
   actividad/Instructor/Objetivo) → "Descargar PDF" → confirmar que el PDF trae
   el logo de SD S.A.S. en el encabezado y un acento rojo corporativo (sin
   fondos de color, solo el logo y bordes/texto), y que la tabla de firmantes
   ahora incluye una columna "Fecha de firma" con la fecha y hora real de cada
   firma.
2. Repetir la misma verificación (logo, color, columna) en el PDF de una
   lección de asistencia "legacy" (si el curso todavía usa ese flujo antiguo).
3. Desde el detalle de asistencia de un curso, usar el nuevo botón "Descargar
   individual" junto a una persona específica del roster → confirmar que el PDF
   generado trae SOLO esa persona (mismo formato/logo/color que el Grupal).
4. El punto de "cómo se retroalimenta al usuario la validación de campos antes
   de generar el PDF" (punto 6 del comentario) queda pendiente de una
   conversación de producto aparte — no se implementó en esta vuelta.
