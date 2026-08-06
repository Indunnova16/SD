# PLAN — SD#71 "Portal Tickets" — Ronda 4 (reproceso #3)

## Contexto / reproceso

`reproceso_rate.py` marca SD#71 como **REPROCESO — 3 rebotes**. Post-mortems ya
registrados: `FIX_INCOMPLETO/intent_mal_leido` (ronda 1→2), `FIX_INCOMPLETO/otro`
(ronda 2→3). El cierre de ronda 3 (🟢, 2026-08-01) fue seguido por un comentario
de Indunnova que audita `apps/feedback/` a fondo contra la especificación
funcional completa del portal (basada en Arcopack) y deja una **lista
consolidada de 5 pendientes** — ninguno es que "el fix no funcionó", son
requisitos de la spec original que nunca se habían mapeado explícitamente.

### 🔁 Post-mortem de esta ronda (a incluir en el comentario de cierre)

- **Categoría:** `FIX_INCOMPLETO`
- **Causa raíz:** `otro` — específicamente: nunca se hizo un mapeo explícito
  contra la especificación funcional completa "estructura basada en la
  operación de Arcopack" que el issue original citaba. Cada ronda cerró contra
  el reclamo puntual del momento (video/audio, comentarios, resolver,
  transcripción) sin volver a leer la spec completa para ver qué otros
  sub-requisitos del mismo documento seguían sin construir. El propio revisor
  tuvo que hacer ese mapeo manualmente (comentario 2026-08-01) porque nosotros
  no lo hicimos antes de cada cierre 🟢.
- **Corrección de esta ronda:** tabla de entregables completa (abajo) contra
  el mapeo literal que ya hizo el revisor, para que el cierre de esta vuelta
  no vuelva a dejar un sub-ítem tácito afuera.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | Estado |
|---|---|---|---|
| 1 | Búsqueda pública por número de ticket | Formulario/caja de búsqueda en `/feedback/` que redirige al detalle del ticket buscado; 404 amigable si no existe | ⏳ |
| 2 | Detección de posibles duplicados por palabras clave al crear un ticket | Al enviar un ticket con asunto similar a uno abierto existente, el form re-muestra una advertencia con los tickets candidatos y pide confirmar antes de crear | ⏳ |
| 3 | Decisión: ¿"resolver" debe exigir identificación o queda público? | **Decisión de negocio real, ya preguntada 2 veces sin respuesta** — NO se implementa ninguna dirección sin autorización explícita de Indunnova. Se re-flagea en el comentario de cierre | ⏸ escalado (no bloquea el resto) |
| 4 | Confirmar/asegurar captura automática de IP + fecha del reportero | `created_at` (fecha) ya se capturaba automáticamente desde v1.0 (`auto_now_add`). IP NO se capturaba — se agrega `FeedbackTicket.ip_reportante` + migración, poblado en `nuevo_view` | ⏳ |
| 5 | Comentar desde el portal, independiente de resolver | Formulario de comentario en el detalle (separado del botón "Resolver") que postea un comentario al issue de GitHub sin cambiar el estado del ticket | ⏳ |

Fuera de esta tabla, NO se reabren los 6 puntos que la propia auditoría de
Indunnova (2026-08-01) ya marcó como ✅ implementado (formulario, adjuntos a
GCS, transcripción IA, creación de issue+label+assignee, comentarios visibles
en el portal, "Validado por + fecha" al resolver).

## Causa raíz por entregable

- **#1 y #5** son features que nunca se construyeron — no hay bug, es
  scope faltante identificado ahora por primera vez de forma explícita.
- **#2** ídem — nunca hubo lógica de duplicados.
- **#4** el modelo nunca tuvo el campo; `get_client_ip`-equivalente ya existe
  como patrón en `apps/courses/utils.py` (no se importa cross-app, se
  replica localmente en `apps/feedback/services.py` para no acoplar apps).
- **#3** no es un bug ni scope faltante: es una pregunta de negocio (seguridad
  vs. fricción en un portal público) que el equipo de Indunnova no ha resuelto
  en 2 rondas previas. Autonomía ampliada permite decisiones de scope menor,
  pero cambiar el modelo de autenticación de una acción pública en producción
  no lo es — se mantiene como pendiente de decisión, visible y explícito.

## Plan de implementación (orden)

1. **Modelo + migración**: `FeedbackTicket.ip_reportante` (GenericIPAddressField,
   null/blank). Migración `0004_feedbackticket_ip_reportante.py`.
2. **services.py**: `obtener_ip_cliente(request)` (mismo patrón que
   `apps.courses.utils.get_client_ip`, replicado local). `buscar_posibles_duplicados(asunto, excluir_id=None)`
   — normaliza palabras (≥4 letras, sin stopwords básicas) del asunto nuevo vs.
   asuntos de tickets `estado=abierto`, match si comparten ≥2 palabras.
   `comentar_issue_ticket(ticket, nombre, cuerpo)` — usa
   `GitHubFeedbackClient.comentar_issue` (nuevo método, extraído del bloque de
   comentario que ya usa `cerrar_issue`).
3. **github_client.py**: extraer `_postear_comentario(issue_number, cuerpo)` de
   `cerrar_issue` y exponer `comentar_issue(issue_number, cuerpo)` público, para
   reuso sin cerrar el issue.
4. **forms.py**: `BuscarTicketForm` (numero_ticket), `ComentarioTicketForm`
   (nombre + comentario + honeypot), agregar `confirmar_duplicado`
   (BooleanField oculto) a `NuevoTicketForm`.
5. **views.py**:
   - `nuevo_view`: si hay duplicados y no viene `confirmar_duplicado=1`, NO
     crea el ticket — re-renderiza con la lista de duplicados. Captura
     `ip_reportante` al crear.
   - `buscar_view` nueva: GET `numero` → redirige a detalle si existe
     (busca por `id` y por `github_issue_number`), si no existe vuelve a la
     lista con mensaje de error.
   - `comentar_view` nueva: POST-only, publica el comentario en GitHub (si el
     ticket aún no sincronizó, mensaje de "todavía se está sincronizando").
6. **urls.py**: `buscar/`, `<id>/comentar/`.
7. **Templates**: caja de búsqueda en `lista.html`; bloque de "posibles
   duplicados" + botón de confirmar en `nuevo.html`; form de comentario
   independiente en `detalle.html`.
8. **Tests**: nuevos casos en `test_portal_v1.py` (o archivo nuevo
   `test_busqueda_duplicados_comentarios.py`) cubriendo los 4 entregables
   implementables + regresión de lo existente.
9. Deploy vía `deploy-cloudrun.yml` a `main`, verificar 100% tráfico.
10. Smoke prod: lista+búsqueda+nuevo+duplicado+detalle+comentar+resolver.
11. Cierre con comentario estructurado, tabla de entregables tickeada,
    marcador `REPROCESO_DATA` con `bounce: 3`.

## Bloqueos / decisiones que Miguel/Indunnova deben tomar

- **#3** — el "resolver" público sigue sin decisión. No se toca en esta
  ronda. Ya se preguntó explícitamente 2 veces en el issue.
