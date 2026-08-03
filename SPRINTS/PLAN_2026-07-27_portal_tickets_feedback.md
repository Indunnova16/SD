# PLAN — Portal de Tickets / Feedback público (issue #71)

**Fecha:** 2026-07-27
**Issue:** [Indunnova16/SD#71](https://github.com/Indunnova16/SD/issues/71)
**Estado:** Planning completado, listo para ejecución (F3 sprint_exec)
**Ruta:** sprint_path (F1 aprobado por Miguel — greenfield, `complexity_class: complex`)

## Contexto

Portal público (anónimo, sin login) "portal de SD - Cursos" para que cualquier
usuario reporte un problema/sugerencia y quede registrado automáticamente como
GitHub Issue en `Indunnova16/SD` (label `portal-web` + assignee `Indunnova`).
Réplica **simplificada** del patrón `Arcopack/feedback/` — v1.0 completa:

- Crear ticket (nombre, asunto, descripción, 0-N imágenes).
- Listar todos los tickets (tablero público).
- Ver el detalle de un ticket propio, incluidas las imágenes que subió
  (requisito literal del cliente: *"que el usuario pueda ver las imágenes
  cargadas en GH desde su portal"*).

**Explícitamente DIFERIDO de v1.0** (decisión HITL de Miguel 2026-07-27, no
reabrir): transcripción Gemini de audio/video, sync bidireccional GitHub→portal
vía webhook (sin esto el portal no refleja en vivo si Indunnova comentó/cerró
el issue — aceptable porque el cliente no pidió seguimiento de estado), y
sistema de comentarios/editar/cerrar/reabrir ticket desde el portal. Por lo
tanto **NO hay modelo `FeedbackComment`, NO hay `estado`/KPIs de resueltos, NO
hay `gcs_client.py` manual ni `gemini_client.py`** — a diferencia de Arcopack.

Simplificaciones que reducen el scope respecto al research inicial:

1. SD **ya tiene** `django-storages[google]` + `google-cloud-storage` en
   `requirements/production.txt` y el bucket `sd-lms-media` funcionando
   (`GS_DEFAULT_ACL=publicRead`, `GS_QUERYSTRING_AUTH=False`, UBLA
   desactivado, confirmado en vivo por F1). Un `ImageField` Django normal
   basta — cero código de storage manual.
2. El PAT `arcopack-feedback-github-token` **ya existe** en Secret Manager
   con permiso `push:true` sobre `Indunnova16/SD` (confirmado por F1) —
   solo hay que enchufarlo al servicio `sd-lms` en `deploy.yml`.
3. Solo imágenes (no audio/video/PDF) → el modelo `FeedbackAttachment` no
   necesita `tipo`/`mime_type`/`transcripcion` como Arcopack.

## Contrato técnico exacto (fuente de verdad para TODOS los sub-items)

Para evitar drift entre sub-items ejecutados por agentes/worktrees distintos,
estos nombres son **literales, no sugerencias**:

- **App**: `apps/feedback/`, `AppConfig.name = "apps.feedback"` (mismo patrón
  que `apps.core`/`apps.accounts`). Django deriva `app_label = "feedback"`
  del último componente del `name` — sin colisión, no existe hoy.
- **Tablas**: `feedback_feedbackticket`, `feedback_feedbackattachment`.
- **Modelo `FeedbackTicket`**: `nombre_reportante` (CharField 120),
  `asunto` (CharField 200), `descripcion` (TextField), `github_issue_number`
  (IntegerField null/blank/unique), `github_url` (URLField blank),
  `sincronizado_github` (BooleanField default False), `error_sincronizacion`
  (TextField blank), `created_at`/`updated_at` (auto). `Meta.ordering =
  ['-created_at']`.
- **Modelo `FeedbackAttachment`**: `ticket` (FK a FeedbackTicket,
  `related_name='adjuntos'`, `on_delete=CASCADE`), `imagen` (ImageField,
  `upload_to='feedback/adjuntos/%Y/%m/'`), `nombre_original` (CharField 255
  blank), `created_at` (auto). `Meta.ordering = ['created_at']`.
- **Form `NuevoTicketForm`** (`forms.Form`, NO ModelForm): campos
  `nombre_reportante` (requerido, min 2 chars), `asunto` (requerido, max
  200), `descripcion` (requerido, min 10 chars) — **a diferencia de Arcopack,
  TODOS son obligatorios siempre** (SD no tiene Gemini para autocompletar si
  el usuario solo sube imágenes). Honeypot `website` (oculto vía CSS
  `position:absolute;left:-9999px`, `required=False`, si viene con valor →
  `ValidationError`, mismo patrón que Arcopack).
- **Input de archivos**: `<input type="file" name="imagenes" multiple
  accept="image/*">` en el template — el view lee
  `request.FILES.getlist('imagenes')`.
- **URLs app** (`apps/feedback/urls.py`, `app_name = 'feedback'`):
  `''` → `feedback:lista`, `'nuevo/'` → `feedback:nuevo`,
  `'<int:ticket_id>/'` → `feedback:detalle`.
- **URL raíz**: `path("feedback/", include("apps.feedback.urls"))` en
  `config/urls.py`, sección "Web views (HTMX)".
- **`github_client.py`**: clase `GitHubFeedbackClient(token=None, repo=None)`
  leyendo `settings.GITHUB_FEEDBACK_TOKEN`/`GITHUB_FEEDBACK_REPO`; métodos
  `crear_issue(ticket_id, asunto, descripcion, nombre_reportante,
  adjuntos=None) -> dict` (retorna `{number, html_url, id}`) y
  `asegurar_label_portal_web() -> None` (label `portal-web`, color
  `fbca04`, idempotente 201/422). **Sin `ip` param** — SD no trackea IP en
  v1.0 (no estaba en el scope de F1).
- **`services.py`**: `sincronizar_ticket(ticket_id) -> bool` (idempotente,
  llama `asegurar_label_portal_web()` + `crear_issue()`, on error deja
  `sincronizado_github=False` + `error_sincronizacion` poblado **sin borrar
  el ticket**), `encolar_sincronizacion_ticket(ticket_id)` (via
  `transaction.on_commit`), `procesar_archivos_subidos(ticket, archivos) ->
  list` (ver validación de imagen abajo).
- **Settings** (`config/settings/base.py`): `GITHUB_FEEDBACK_TOKEN = config(
  "GITHUB_FEEDBACK_TOKEN", default="")`, `GITHUB_FEEDBACK_REPO = config(
  "GITHUB_FEEDBACK_REPO", default="Indunnova16/SD")`,
  `FEEDBACK_MAX_ATTACHMENTS = config(..., default=10, cast=int)`,
  `FEEDBACK_MAX_ATTACHMENT_BYTES = config(..., default=10*1024*1024,
  cast=int)` (10 MB, menor que Arcopack porque solo son imágenes).
- **Branding**: título de página / header = "portal de SD - Cursos" (texto
  literal del issue).
- **Layout de templates**: `apps/feedback/templates/feedback/base.html` es
  standalone (Tailwind CDN + DaisyUI + Alpine dark-mode) — **espejo del
  patrón de `templates/accounts/base_auth.html`** (login público), **NO**
  extender el shell autenticado con sidebar/logout (esta superficie es
  pública/anónima, sin sesión SD).

## Sub-items (Sprint A — sprint único)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | App skeleton + modelos + migración + wiring settings | `apps/feedback/{__init__,apps,models}.py`, `apps/feedback/migrations/{__init__,0001_initial}.py`, `config/settings/base.py` (LOCAL_APPS + `GITHUB_FEEDBACK_*` + `FEEDBACK_MAX_*`) | `apps/feedback/tests.py::ModelsTestCase` (str, migración aplica) | - | low | ⏳ pendiente |
| A2 | Cliente GitHub REST minimal | `apps/feedback/github_client.py`, `requirements/base.txt` (+`requests>=2.31,<3`) | `GithubClientTestCase` (mock `requests`, payload de `crear_issue` correcto — title/body/labels/assignees, `asegurar_label` idempotente 201 y 422) | A1 | low | ⏳ pendiente |
| A3 | Form `NuevoTicketForm` con honeypot | `apps/feedback/forms.py` | incluido en A8 | A1 | trivial | ⏳ pendiente |
| A4 | `services.py` — subida de imágenes + sync síncrona a GitHub | `apps/feedback/services.py` | incluido en A8 | A1, A2 | medium | ⏳ pendiente |
| A5 | Vistas públicas + urls (app + raíz) + admin | `apps/feedback/views.py`, `apps/feedback/urls.py`, `apps/feedback/admin.py`, `config/urls.py` | incluido en A8 | A1, A3, A4 | medium | ⏳ pendiente |
| A6 | Templates con branding "portal de SD - Cursos" | `apps/feedback/templates/feedback/{base,lista,nuevo,detalle}.html` | - (validado por journey E2E) | A5 | medium | ⏳ pendiente |
| A7 | Deploy: secret + env var en `deploy.yml` | `.github/workflows/deploy.yml` | - | (ninguna — independiente) | trivial | ⏳ pendiente |
| A8 | Tests unitarios happy + edge cases | `apps/feedback/tests.py` | ver detalle abajo | A6 | low | ⏳ pendiente |

**Total: 8 sub-items, 1 sprint.** Ninguno es `epic` → no aplica el gate de
"Enumeración de sitios" (3.5 del prompt F2).

### Detalle A7 (deploy.yml) — líneas exactas

- `--set-env-vars` (línea 65 actual, step "Deploy"): agregar
  `,GITHUB_FEEDBACK_REPO=Indunnova16/SD` al final de la cadena existente.
- `--set-secrets` (línea 66 actual, step "Deploy"): agregar
  `,GITHUB_FEEDBACK_TOKEN=arcopack-feedback-github-token:latest` al final.
- **NO tocar** los jobs `sd-lms-migrate` / `sd-lms-ensure-admin` /
  `sd-lms-axes-reset` — no necesitan el secret (no crean issues).
- A7 es deployable en solitario de forma segura (agrega env var/secret sin
  código que los lea aún) — útil como checkpoint de deploy temprano si el
  orquestador quiere validar el pipeline de secretos antes de que A1-A6
  terminen.

### Detalle A4 (services.py) — validación de imagen (hallazgo propio de F2)

`FeedbackAttachment.objects.create(imagen=archivo)` (fuera de un
`ModelForm`) **NO ejecuta `full_clean()`** — los validadores de `ImageField`
(que verifican con Pillow que el contenido es una imagen real) **no corren
automáticamente**. En un formulario público anónimo con upload a un bucket
GCS `publicRead`, esto es una superficie de "sube cualquier archivo con
extensión de imagen falsa" sin las protecciones nativas de Django. `A4` debe
validar explícitamente antes de guardar:

1. `content_type` empieza con `image/`.
2. Tamaño ≤ `FEEDBACK_MAX_ATTACHMENT_BYTES`.
3. Abrir el archivo con `PIL.Image.open(...).verify()` (defensivo contra
   content-type spoofeado) — si falla, **no crear el `FeedbackAttachment`**,
   loggear y continuar con el resto de archivos (best-effort por archivo,
   mismo patrón que Arcopack: un archivo inválido no debe tumbar la
   creación del ticket ni de los demás adjuntos válidos).

### Detalle A5 — riesgo de secuencia (por qué `config/urls.py` va en A5, no en A1)

`config/urls.py` hace `include("apps.feedback.urls")`. Si ese wiring se
deployara **antes** de que `apps/feedback/urls.py` exista (ej. si A1
incluyera el include raíz), el import fallaría al arrancar gunicorn y
**tumbaría el LMS completo** (todos los cursos/usuarios existentes), no solo
el portal nuevo — el mayor riesgo operativo detectado en este plan. Por eso
el include raíz vive en el **mismo sub-item** que crea `apps/feedback/urls.py`
(A5), nunca antes.

## DAG dependencias

```
A1 (app+modelos+settings)
 ├─→ A2 (github_client) ──┐
 ├─→ A3 (forms)           ├─→ A4 (services, depende A1+A2) ─→ A5 (views+urls+admin, depende A1+A3+A4) ─→ A6 (templates) ─→ A8 (tests)
 └─(A3 y A2 en paralelo, worktrees separados — archivos disjuntos)

A7 (deploy.yml) — sin dependencias, paralelo desde el inicio
```

`dag_dependencias` (JSON): `{"A2":["A1"], "A3":["A1"], "A4":["A1","A2"],
"A5":["A1","A3","A4"], "A6":["A5"], "A7":[], "A8":["A6"]}`

A2 y A3 son ambos pequeños (github_client.py ~80 líneas, forms.py ~40
líneas) y tocan archivos disjuntos — el orquestador puede correrlos en
worktrees paralelos o combinarlos en un solo sub-item si prioriza
throughput sobre paralelismo; no hay riesgo de colisión cualquiera de las
dos formas.

## Riesgos y mitigaciones

- **Secuencia `config/urls.py`** (alto si se ignora): mitigado — ver Detalle
  A5 arriba. El include raíz va junto con `apps/feedback/urls.py`.
- **Upload público sin validación de contenido real** (medio): mitigado —
  ver Detalle A4 (validación Pillow explícita antes de `.create()`).
- **Superficie pública anónima = spam/abuso** (aceptado para v1.0, no
  bloqueante): el honeypot cubre bots simples; **no hay** rate-limiting ni
  CAPTCHA en v1.0 — no lo pidió el cliente y agregar `django-ratelimit`
  sería scope creep. Si el volumen de spam se vuelve un problema real
  post-lanzamiento, es un issue de seguimiento, no parte de esta v1.0.
- **Fallo de sincronización a GitHub no debe perder el ticket** (cubierto
  por diseño — `sincronizado_github=False` + `error_sincronizacion`
  poblado, ticket sigue visible/consultable en el portal; sin reintento
  automático en v1.0 porque no hay Celery worker en el flujo síncrono del
  portal — igual que Arcopack).
- **El journey E2E mutativo crea un GitHub Issue REAL en Indunnova16/SD en
  cada corrida** (operativo, no de código): la API de GitHub no tiene
  borrado de issues, y el runner de journeys no tiene una acción de
  escritura HTTP genérica contra APIs externas (solo `psql`). Mitigación:
  el asunto del ticket de prueba lleva el prefijo `[QA-E2E-TEST]`
  (filtrable). El ticket LOCAL (BD) y su adjunto SÍ se limpian vía
  `cleanup: delete_via_psql` — el issue de GitHub queda abierto y marcado.
  **Nota operativa para Miguel**: estos issues `[QA-E2E-TEST]` caen bajo la
  excepción "issues abiertos por mí mismo (internos, no del cliente)" del
  protocolo global de issues — se pueden resolver directamente vía la CLI
  de GitHub sin pasar por la compuerta de "asignar Indunnova, no
  finalizar". Si el volumen de corridas de este journey crece, considerar
  un management command de limpieza periódica (listar por label
  `portal-web` + título con el prefijo de prueba, y resolverlos en batch)
  — fuera de scope de v1.0, queda anotado para no perderlo.
- **Riesgo global: medio** (coincide con la estimación de F1) — ninguno de
  los riesgos de arriba es un bloqueo, todos tienen mitigación de diseño
  concreta en el plan.

## Decisión de scope explícita: link desde `login.html` — FUERA de v1.0

F1 marcó como sub-item de baja prioridad "link visible al portal desde
`templates/accounts/login.html`". F2 decide dejarlo **fuera de v1.0**,
documentado explícitamente (no es un olvido):

1. El portal es público/anónimo — se espera compartir por URL directa o QR,
   no descubrirlo desde la pantalla de login del LMS interno.
2. `login.html` es una plantilla compartida de alto tráfico (TODOS los
   usuarios del LMS pasan por ahí) — tocarla para una feature de baja
   prioridad introduce riesgo asimétrico (cualquier error visual/de markup
   ahí afecta el login de todo el LMS) para un beneficio marginal.
3. Si Miguel quiere el link después, es un issue de 1 línea de HTML — no
   amerita mantener el sub-item vivo en este plan ni retrasar el cierre de
   v1.0 por él.

## Checklist DoD (versión 1.0 completa)

- [x] Migration: A1 (`0001_initial.py`, dos modelos).
- [x] Backend endpoint + form + lógica de negocio: A1-A5 (modelos, form con
      validación, vistas, servicio de sync + validación de imagen).
- [x] UI con estados completos: A6 — `nuevo.html` debe mostrar errores de
      validación por campo (incl. honeypot silencioso — no revelar al
      "bot" que fue detectado, simplemente re-renderizar el form limpio o
      con error genérico), estado de éxito post-creación
      (`messages.success` + redirect a detalle, patrón Arcopack), y
      `detalle.html` debe mostrar claramente si `sincronizado_github=False`
      (mensaje discreto tipo "seguimos procesando tu reporte" — el usuario
      NO debe ver un error técnico, el ticket sigue siendo válido).
- [x] Tests happy + ≥2 edge cases: A8 —
      1. Happy path: crear ticket con imagen → `FeedbackTicket` +
         `FeedbackAttachment` creados, `github_client.crear_issue` mockeado
         y llamado con el payload correcto, `sincronizado_github=True`
         tras el mock exitoso.
      2. Honeypot: form con `website` poblado → `ValidationError`, CERO
         filas creadas, CERO llamada a GitHub.
      3. Resiliencia ante fallo de GitHub: mock `GitHubClientError` →
         ticket **sigue existiendo** en BD con `sincronizado_github=False`
         + `error_sincronizacion` poblado (no se pierde el reporte del
         usuario — requisito explícito del issue).
      4. Archivo no-imagen (ej. `.txt` renombrado `.jpg` o contenido
         corrupto) → NO crea `FeedbackAttachment` para ese archivo, el
         ticket y los demás adjuntos válidos SÍ se crean (best-effort).
      5. `lista_view`/`detalle_view` responden 200 con y sin tickets
         existentes (caso vacío del primer deploy).
- [x] Smoke E2E definido: journey `SD_71.yaml` (ver abajo) — 2 read-only +
      1 mutativo completo (crear ticket con imagen real, verificar sync a
      GitHub, verificar imagen visible en detalle, verificar aparición en
      lista pública).
- [x] Instrucciones de validación cliente: ver sección final.

## Validación esperada (cliente / smoke)

1. Abrir `https://sd-lms-rvfp6uj2va-uc.a.run.app/feedback/` (sin login) →
   debe verse el tablero "portal de SD - Cursos" con el botón para crear un
   ticket nuevo.
2. Click "Nuevo ticket" → llenar nombre, asunto, descripción, adjuntar 1
   foto → enviar.
3. Debe redirigir a la página de detalle del ticket recién creado, mostrando
   la foto adjunta.
4. Verificar en `https://github.com/Indunnova16/SD/issues` que se creó un
   issue nuevo con label `portal-web`, asignado a `Indunnova`, con la foto
   embebida en el cuerpo del issue.
5. Volver a `/feedback/` y confirmar que el ticket recién creado aparece en
   el tablero.

## Journey E2E

Ver `SPRINTS/RUN_2026-07-27_1723/journeys/SD_71.yaml` — 2 journeys read-only
(`i71_lista_publica`, `i71_nuevo_form_render`) + 1 mutativo
(`m1_crear_ticket_completo_con_imagen`, sube `firma_qa_e2e.png` de
`fixtures/SD/`, verifica sync real a GitHub vía `psql_select` sobre
`github_issue_number`/`sincronizado_github`, y limpia el ticket+adjunto
local en `cleanup`). Selectores de las 2 superficies de UI nueva
(`/feedback/nuevo/`, `/feedback/<id>/`) marcados `# RECONCILIAR_DOM` — F3
(sub-item A6) debe reconciliarlos contra el DOM real antes de F5, siguiendo
`ui_nueva_reconciliar[]` del JSON de este agente.
