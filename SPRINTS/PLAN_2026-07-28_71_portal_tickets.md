# PLAN — Portal de Tickets #71, ronda 2 (rebote del cliente)

**Fecha:** 2026-07-28
**Issue:** [Indunnova16/SD#71](https://github.com/Indunnova16/SD/issues/71) · label `Urgente`
**Rama:** `fix/sd-71-2026-07-28` (worktree `~/SD-wt-71`)
**Plan previo:** `SPRINTS/PLAN_2026-07-27_portal_tickets_feedback.md` (v1.0, mergeada a `main`)
**Alcance de esta ronda:** SIN deploy, SIN push, SIN comentario en el issue.

## 0. Situación: esto es un REBOTE, no un issue nuevo

`reproceso_rate.py --repos SD --issue 71` → **"🔁 SD#71 ES UN REPROCESO — 1 rebote(s)"**.

- **Afirmamos** (2026-07-28, comentario de cierre v1.0): *"Feature 1.0 deployada …
  La feature está **completa para validación**, no en estado MVP"*, 🟡, revision
  `sd-lms-00151-tel`, 3/3 journeys verdes.
- **El revisor (`Indunnova`) devolvió** el mismo día:
  1. *"falta la opcion de grabar video y audio"* (captura del form: solo
     "Imágenes (opcional)" + `<input type=file accept="image/*">`).
  2. *"el usauro no puede ver los comentarios ni imagentes en el ticket"*
     (captura de `/feedback/2/`: solo asunto, reportante, fecha y descripción).
  3. *"ni puede resolver el caso"*.

### Post-mortem de la intervención previa (insumo del paso 6 del protocolo)

| Qué | Detalle |
|---|---|
| **Categoría** | `FIX_INCOMPLETO` |
| **Causa raíz** | `intent_mal_leido` — el requisito literal del body *"que el usuario pueda ver las **imágenes cargadas en GH** desde su portal"* se implementó como "ver las imágenes que **el usuario subió**" (se renderizan desde `FeedbackAttachment`, `detalle.html:29-42`). El cliente pedía la dirección contraria: ver, desde el portal, lo que pasa **en GitHub** (comentarios del equipo y sus imágenes). |
| **Qué falló** | El PLAN v1.0 **difirió explícitamente** por decisión HITL 2026-07-27 (`PLAN_2026-07-27…:21-27`): *"transcripción Gemini de audio/video, sync bidireccional GitHub→portal vía webhook … y sistema de comentarios/editar/cerrar/reabrir ticket desde el portal"*. Los 3 diferidos son **exactamente** los 3 reclamos del cliente. |
| **Por qué no se atrapó** | El diferimiento se justificó como *"el cliente no pidió seguimiento de estado"*, pero nunca se validó con el cliente. El E2E y el smoke (3/3 verdes) probaron **lo construido**, no **lo pedido** — no había gate que contrastara el body del issue contra la entrega. |
| **Corrección esta vez** | Tabla de entregables derivada del **body + los 2 comentarios**, y ningún ítem se declara ✅ sin evidencia concreta. |

**Nota sobre el watchdog:** acá el script SÍ detectó el rebote porque hubo comentario
de cierre nuestro. Aun sin ese comentario, entrega mergeada a `main` + cliente
reclamando = rebote funcional.

## 1. Tabla de entregables (gate anti-FIX_INCOMPLETO)

Derivada del body (4 bullets) + comentario #2 del revisor (3 reclamos).
`✅ ya hecho` = cubierto por los commits v1.0 en `main`; `❌ falta` = trabajo de esta ronda.

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | Estado al abrir |
|---|---|---|---|
| 1 | Portal público de tickets estilo Arcopack, sin login | `GET /feedback/` 200 anónimo | ✅ ya hecho (`views.py:29`) |
| 2 | Se llama "portal de SD - Cursos" | `<h1>` y `<title>` con el texto literal | ✅ ya hecho (`base.html:22,131`) |
| 3 | Crear ticket desde el portal | `POST /feedback/nuevo/` → redirect a detalle | ✅ ya hecho (`views.py:43`) |
| 4 | Ticket crea issue en GH con label `portal-web` + assignee `@Indunnova` | payload `labels`/`assignees` en `crear_issue` | ✅ ya hecho (`github_client.py:79-84`) |
| 5 | El usuario ve **sus** imágenes adjuntas en el portal | `<img>` por cada adjunto en el detalle | ✅ ya hecho (`detalle.html:29-42`) |
| 6 | **Grabar AUDIO desde el portal** | Botón "Grabar audio" → `MediaRecorder` → adjunto `tipo=audio` → `<audio controls>` en el detalle | ❌ falta |
| 7 | **Grabar VIDEO desde el portal** | Botón "Grabar video" → `MediaRecorder` (cámara+mic, preview en vivo) → adjunto `tipo=video` → `<video controls>` en el detalle | ❌ falta |
| 8 | Adjuntar audio/video como **archivo** (no solo grabado) | `accept="image/*,audio/*,video/*"`; backend acepta los 3 prefijos MIME | ❌ falta |
| 9 | **Ver los comentarios del equipo (GitHub) en el ticket** | Sección "Conversación" en el detalle con autor + fecha + cuerpo de cada comentario del issue | ❌ falta |
| 10 | **Ver las imágenes cargadas en GH desde el portal** (requisito literal del body) | Imagen embebida en un comentario de GH (`![](…)` o `<img src="https://github.com/user-attachments/assets/…">`) se ve como `<img>` en el detalle del portal | ❌ falta |
| 11 | **Resolver el caso desde el portal** | Botón "Resolver" → `POST /feedback/<id>/resolver/` → `estado=resuelto` + comentario y `state=closed` en el issue de GH | ❌ falta |
| 12 | El estado del ticket es visible | Badge 🔵 Abierto / 🟢 Resuelto en lista y detalle | ❌ falta |
| 13 | Fallo de GitHub nunca pierde/rompe el ticket | comentarios: degrada sin romper el detalle; resolver: estado local igual queda `resuelto` | ❌ falta (aplica a lo nuevo) |
| 14 | Los tests del portal corren en la suite de CI | `pytest` **colecta** los tests de `apps/feedback` | ❌ falta (ver §2) |

## 2. Hallazgo colateral: los 36 tests de v1.0 son invisibles para CI

`pyproject.toml:86` → `python_files = ["test_*.py", "*_test.py"]`.
Los tests viven en `apps/feedback/tests.py`, que **no matchea** ninguno de los dos patrones.

- `pytest --collect-only apps/feedback/` → `no tests collected`.
- `manage.py test apps.feedback` → `Ran 36 tests … OK`.

O sea: los 36 tests que el comentario de cierre citó como evidencia **nunca corrieron
en CI** (`.github/workflows/ci.yml:56` usa pytest). Es el gotcha
`feedback_tests_no_colectan_ocultan_bugs`. Se corrige moviendo a
`apps/feedback/tests/test_*.py` (convención del resto del repo, ej.
`apps/accounts/tests/test_api.py`).

## 3. Diseño de lo faltante (reusa lo existente)

### 3.1 Adjuntos audio/video (entregables 6, 7, 8)

`FeedbackAttachment.imagen` es un `ImageField` (`models.py:68`) y
`procesar_archivos_subidos` exige `content_type.startswith("image/")`
(`services.py:77`) + `PIL.Image.verify()` (`services.py:101`). No sirve para media.

- Modelo: `imagen` → `archivo` (`FileField`), + `tipo` (choices `imagen|audio|video`)
  + `mime_type`. Migración `0002` con `RenameField` + `AlterField` + `AddField` +
  data-migration que backfillea `tipo="imagen"` en las filas existentes de prod
  (v1.0 solo aceptaba imágenes, así que el backfill es exacto).
- Servicio: allowlist por prefijo MIME; `PIL.verify()` **solo** para imágenes
  (audio/video no se pueden verificar barato); normalizar `audio/webm;codecs=opus`
  → `audio/webm` (MediaRecorder manda el parámetro `codecs`).
- Límite: `FEEDBACK_MAX_ATTACHMENT_BYTES` 10 MB → 30 MB (video pesa; techo real
  es el límite de request de Cloud Run, 32 MiB).
- Front: patrón de Arcopack `feedback/templates/feedback/nuevo.html:286-413` —
  `MediaRecorder` + `DataTransfer` para inyectar el `Blob` grabado como `File`
  dentro del `<input type="file">` real, y postear multipart normal (sin fetch,
  sin base64).
- Body del issue de GH: `![]()` solo para imágenes; audio/video van como link
  (`github_client._build_body` hoy embebe todo como imagen → rompería).

### 3.2 Comentarios de GitHub en el portal (entregables 9, 10)

Arcopack lo resuelve con **webhook** (push, `GITHUB_FEEDBACK_WEBHOOK_SECRET` + HMAC
+ modelo `FeedbackComment`). Para SD elijo **pull** en la vista de detalle:

- No requiere infra nueva (ni secret de webhook, ni registrar el webhook en GH) —
  esta ronda no puede deployar ni tocar Secret Manager.
- No hay drift por eventos perdidos.
- Costo: 1 llamada a la API por vista de detalle → mitigado con `cache` (TTL 60 s)
  y degradación elegante (si GH falla, el detalle igual renderiza).

Piezas: `github_client.listar_comentarios()`, `services.obtener_comentarios_github()`,
filtro `markdownify` (markdown + bleach) y sección "Conversación" en `detalle.html`.

**Por qué esto cierra el entregable 10:** el cuerpo de un comentario de GH trae la
imagen como `![x](https://github.com/user-attachments/assets/…)` o como HTML crudo
`<img width="1236" src="…">` (es literalmente el formato del comentario #2 de este
issue). Al renderizar markdown y sanear con bleach dejando `img[src|alt|width|height]`,
la imagen queda visible en el portal.

Verificado: `Indunnova16/SD` es **público** (`gh repo view --json isPrivate` →
`false`) y las URLs `github.com/user-attachments/assets/…` de este issue se
descargan sin autenticación (`curl` anónimo → PNG válido). En un repo privado esto
NO funcionaría y habría que proxear.

Verificado también que **no hay CSP que las bloquee**: prod corre
`config.settings.cloudrun` (`deploy.yml:65`), que no define directivas; las
`CSP_*` de `production.py:20-30` son config muerta (no se usa ese módulo, y
django-csp 4.0 lee `CONTENT_SECURITY_POLICY`, no las `CSP_*` planas).

Guarda: los comentarios que empiezan con `[INTERNO]` no se publican en el portal
(mismo convenio que Arcopack) — el portal es anónimo y el issue es público.

### 3.3 Resolver el caso (entregables 11, 12)

- `FeedbackTicket.estado` (`abierto|resuelto`, default `abierto`).
- `github_client.cerrar_issue(issue_number, comentario)`: POST comentario + PATCH
  `state=closed`.
- `services.resolver_ticket()`: **primero** el estado local, **después** GitHub —
  un fallo de GH no impide que el usuario resuelva.
- `POST /feedback/<id>/resolver/` + `ResolverTicketForm` (nombre + honeypot).
  Sin auth (portal anónimo por diseño, igual que Arcopack); idempotente.

**Excepción explícita al hook `gh issue close`:** el hook de `settings.json` bloquea
`gh issue close` por Bash. Acá no se cierra ningún issue: se escribe *código* que
cierra el ticket **que el propio portal creó** (label `portal-web`), a pedido del
usuario final. Es el flujo "el cliente cierra al validar", no el agente cerrando
issues de cliente. **Esta rama no ejecuta ningún cierre.**

## 4. Fuera de alcance (decisiones de scope, ℹ️)

| Ítem | Razón |
|---|---|
| Transcripción de audio/video con Gemini | Arcopack la tiene; el cliente pidió **grabar**, no transcribir. Sin `GEMINI_API_KEY` en `sd-lms`. |
| Webhook GitHub→portal (push) | Reemplazado por pull; requiere secret + registrar webhook = infra, y esta ronda no deploya. |
| Reabrir un ticket resuelto | El cliente pidió "resolver". Se puede reabrir desde GitHub. |
| Comentar **desde** el portal | No pedido — el reclamo es *ver* los comentarios. |
| Arreglar la config CSP muerta de `production.py` | No afecta a prod (usa `cloudrun.py`); tocarlo es riesgo sin beneficio para este issue. |

## 5. Bloqueos / pendientes de esta ronda (⏸)

- ⏸ **Deploy y validación en prod**: fuera del alcance encargado. Nada de esto
  puede declararse 🟢 hasta deployar y smokear; el verdict al entregar es 🟡/🔵.
- ⏸ **`getUserMedia` exige contexto seguro**: funciona en `https://sd-lms-…run.app`
  (OK) y en `localhost`, no en HTTP plano. Verificar en el smoke post-deploy.
- ⏸ **Grabar video en iOS Safari**: `MediaRecorder` existe desde iOS 14.3 pero el
  MIME soportado es `video/mp4`, no `webm`. La negociación de MIME lo cubre, pero
  hay que probarlo en un iPhone real.
