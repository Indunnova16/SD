"""
Capa de servicio del portal público de feedback (apps.feedback).

Responsabilidades:

1. `procesar_archivos_subidos`: valida y guarda los adjuntos (imagen, audio
   o video) de un ticket ya creado. `FeedbackAttachment.objects.create(...)`
   fuera de un `ModelForm` NO ejecuta `full_clean()` — los validadores
   nativos del field no corren automáticamente. En un form público anónimo
   esto deja abierta la superficie de "sube cualquier archivo con extensión
   falsa". Por eso este módulo valida EXPLÍCITAMENTE antes de crear cada
   `FeedbackAttachment`, best-effort por archivo: uno inválido nunca tumba
   el ticket ni los demás adjuntos.

2. `sincronizar_ticket` / `encolar_sincronizacion_ticket`: sincroniza el
   ticket como un GitHub Issue de forma síncrona (sin Celery, mismo patrón
   que Arcopack), disparada vía `transaction.on_commit` para que solo
   corra si el ticket+adjuntos ya quedaron persistidos en BD. Un fallo de
   GitHub NUNCA borra ni invalida el ticket: queda registrado con
   `sincronizado_github=False` + `error_sincronizacion` poblado.

3. `obtener_comentarios_github`: trae los comentarios del issue para
   mostrarlos en el detalle del ticket (issue #71 ronda 2 — el cliente
   reclamó que "el usuario no puede ver los comentarios"). Modelo **pull**
   con caché corta, no webhook: no necesita secret ni registrar un webhook
   en GitHub, y no acumula drift por eventos perdidos.

4. `resolver_ticket`: marca el ticket como resuelto y cierra el issue en
   GitHub ("ni puede resolver el caso"). El estado local se escribe SIEMPRE
   primero: si GitHub está caído, el usuario igual resuelve su caso.
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.feedback.github_client import GitHubClientError, GitHubFeedbackClient
from apps.feedback.models import FeedbackAttachment, FeedbackTicket

logger = logging.getLogger(__name__)

# Prefijos MIME aceptados como adjunto del portal. `image/` ya estaba en
# v1.0; `audio/` y `video/` entran por el reclamo del cliente en #71.
PREFIJOS_MIME_PERMITIDOS = ("image/", "audio/", "video/")

# Caché de los comentarios traídos de GitHub. 60 s es suficiente para que
# un usuario que refresca no dispare una llamada por request, y bajo para
# que un comentario nuevo del equipo aparezca casi enseguida.
CACHE_TTL_COMENTARIOS = 60
CACHE_KEY_COMENTARIOS = "feedback:comentarios:{issue_number}"


def normalizar_mime(content_type):
    """Devuelve el MIME sin parámetros y en minúsculas.

    `MediaRecorder` reporta el content-type con el codec incluido
    (`audio/webm;codecs=opus`, `video/webm;codecs=vp9,opus`). Comparar ese
    string crudo contra un allowlist o guardarlo en `mime_type` para usarlo
    en `<source type="...">` da falsos negativos, así que se corta en el
    primer `;`.
    """
    return (content_type or "").split(";")[0].strip().lower()


def procesar_archivos_subidos(ticket, archivos):
    """Valida y guarda como `FeedbackAttachment` los archivos subidos.

    Recibe el `FeedbackTicket` ya guardado y una lista de `UploadedFile`
    (típicamente `request.FILES.getlist(...)`). Por cada archivo valida,
    en orden, EXPLÍCITAMENTE (porque `.create()` fuera de un `ModelForm`
    no dispara `full_clean()`):

        a. El MIME normalizado empieza con `image/`, `audio/` o `video/`.
        b. `size <= settings.FEEDBACK_MAX_ATTACHMENT_BYTES`.
        c. Solo para imágenes: el contenido real es una imagen válida
           (`PIL.Image.verify()`), defensivo contra content-type spoofeado.

    (c) es solo para imágenes a propósito: no existe un equivalente barato
    y confiable para audio/video (haría falta ffprobe, que no está en la
    imagen de Cloud Run). Para esos el gate es el prefijo MIME + el tamaño,
    y el riesgo residual es acotado porque el archivo se sirve desde GCS
    como adjunto, nunca se ejecuta.

    Un archivo que falla cualquiera de las validaciones NO se guarda, se
    loguea como warning, y se continúa con el resto — un archivo inválido
    no debe tumbar la creación del ticket ni de los demás adjuntos
    válidos. Respeta `settings.FEEDBACK_MAX_ATTACHMENTS`: si vienen más
    archivos que el límite, solo se procesan los primeros N (se loguea que
    se truncó, no se falla).

    Devuelve la lista de `FeedbackAttachment` creados exitosamente.
    """
    max_attachments = settings.FEEDBACK_MAX_ATTACHMENTS
    max_bytes = settings.FEEDBACK_MAX_ATTACHMENT_BYTES

    archivos = list(archivos)
    if len(archivos) > max_attachments:
        logger.warning(
            "Ticket #%s: se recibieron %d archivos, se truncó a los "
            "primeros %d (FEEDBACK_MAX_ATTACHMENTS).",
            ticket.pk,
            len(archivos),
            max_attachments,
        )
        archivos = archivos[:max_attachments]

    adjuntos_creados = []

    for archivo in archivos:
        nombre = getattr(archivo, "name", "") or "archivo"

        mime = normalizar_mime(getattr(archivo, "content_type", ""))
        if not mime.startswith(PREFIJOS_MIME_PERMITIDOS):
            logger.warning(
                "Ticket #%s: archivo '%s' descartado — content_type '%s' "
                "no es imagen, audio ni video.",
                ticket.pk,
                nombre,
                mime,
            )
            continue

        size = getattr(archivo, "size", None)
        if size is None or size > max_bytes:
            logger.warning(
                "Ticket #%s: archivo '%s' descartado — tamaño %s excede "
                "FEEDBACK_MAX_ATTACHMENT_BYTES (%s).",
                ticket.pk,
                nombre,
                size,
                max_bytes,
            )
            continue

        tipo = FeedbackAttachment.inferir_tipo(mime)

        if tipo == FeedbackAttachment.TIPO_IMAGEN:
            try:
                archivo.seek(0)
                Image.open(archivo).verify()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                logger.warning(
                    "Ticket #%s: archivo '%s' descartado — contenido no es "
                    "una imagen válida (posible content-type spoofeado): %s",
                    ticket.pk,
                    nombre,
                    exc,
                )
                continue
            finally:
                archivo.seek(0)

        adjunto = FeedbackAttachment.objects.create(
            ticket=ticket,
            archivo=archivo,
            tipo=tipo,
            mime_type=mime,
            nombre_original=nombre,
        )
        adjuntos_creados.append(adjunto)

    return adjuntos_creados


def sincronizar_ticket(ticket_id):
    """Sincroniza un `FeedbackTicket` como GitHub Issue (idempotente).

    Si `ticket.github_issue_number` ya está poblado, no vuelve a llamar a
    GitHub (protege contra doble-sync si esta función se invoca 2 veces
    por error) y devuelve `True` directamente.

    Si `crear_issue`/`asegurar_label_portal_web` levantan
    `GitHubClientError`, la excepción NO se propaga — el ticket ya está
    guardado en BD (eso no debe perderse): se captura, se deja
    `sincronizado_github=False` + `error_sincronizacion` poblado, se
    loguea el error, y se devuelve `False`.

    Devuelve `True` si el ticket quedó (o ya estaba) sincronizado, `False`
    en cualquier otro caso.
    """
    ticket = FeedbackTicket.objects.prefetch_related("adjuntos").get(pk=ticket_id)

    if ticket.github_issue_number is not None:
        return True

    try:
        client = GitHubFeedbackClient()
        client.asegurar_label_portal_web()
        resultado = client.crear_issue(
            ticket_id,
            ticket.asunto,
            ticket.descripcion,
            ticket.nombre_reportante,
            adjuntos=[
                {
                    "nombre": adjunto.nombre_original,
                    "url": adjunto.archivo.url,
                    "tipo": adjunto.tipo,
                }
                for adjunto in ticket.adjuntos.all()
            ],
        )
    except GitHubClientError as exc:
        logger.error(
            "Ticket #%s: fallo sincronizando con GitHub: %s", ticket_id, exc
        )
        ticket.sincronizado_github = False
        ticket.error_sincronizacion = str(exc)
        ticket.save(update_fields=["sincronizado_github", "error_sincronizacion"])
        return False

    ticket.github_issue_number = resultado["number"]
    ticket.github_url = resultado["html_url"]
    ticket.sincronizado_github = True
    ticket.error_sincronizacion = ""
    ticket.save(
        update_fields=[
            "github_issue_number",
            "github_url",
            "sincronizado_github",
            "error_sincronizacion",
        ]
    )
    return True


def encolar_sincronizacion_ticket(ticket_id):
    """Programa `sincronizar_ticket` para después de que la transacción
    actual (creación del ticket + adjuntos) haya committeado exitosamente.

    Mismo patrón que Arcopack, sin Celery: `transaction.on_commit` evita
    llamar a GitHub si el guardado en BD termina revertido.
    """
    transaction.on_commit(lambda: sincronizar_ticket(ticket_id))


# Prefijo con el que el equipo marca un comentario que NO debe verse en el
# portal público. El issue es público y el portal es anónimo, así que la
# conversación interna necesita una vía de escape explícita.
PREFIJO_COMENTARIO_INTERNO = "[INTERNO]"


def obtener_comentarios_github(ticket, usar_cache=True):
    """Devuelve los comentarios del issue de GitHub asociado al ticket.

    Modelo **pull**: se consulta la API en la vista de detalle, con caché de
    `CACHE_TTL_COMENTARIOS` segundos por issue. Se eligió sobre el webhook
    de Arcopack porque no requiere secret HMAC ni registrar un webhook en
    GitHub (infra que esta ronda no puede provisionar) y porque no acumula
    drift si se pierde un evento.

    Filtra los comentarios que empiezan con `[INTERNO]` — ver
    `PREFIJO_COMENTARIO_INTERNO`.

    Si el ticket todavía no tiene issue asociado devuelve `[]`. Si GitHub
    falla, propaga `GitHubClientError`: la vista de detalle lo captura y
    renderiza el ticket igual, con un aviso de que la conversación no se
    pudo cargar. Se propaga en vez de devolver `[]` para no confundir "no
    hay comentarios" con "no pudimos traerlos" — mostrar una conversación
    vacía cuando el equipo SÍ respondió es exactamente el reclamo del
    cliente que este cambio viene a cerrar.

    Devuelve una lista de dicts `{autor, cuerpo, created_at, url}`.
    """
    if not ticket.github_issue_number:
        return []

    cache_key = CACHE_KEY_COMENTARIOS.format(issue_number=ticket.github_issue_number)
    if usar_cache:
        cacheados = cache.get(cache_key)
        if cacheados is not None:
            return cacheados

    try:
        crudos = GitHubFeedbackClient().listar_comentarios(ticket.github_issue_number)
    except GitHubClientError as exc:
        logger.warning(
            "Ticket #%s: no se pudieron traer los comentarios del issue #%s: %s",
            ticket.pk,
            ticket.github_issue_number,
            exc,
        )
        raise

    comentarios = [
        c
        for c in crudos
        if not (c.get("cuerpo") or "").strip().upper().startswith(
            PREFIJO_COMENTARIO_INTERNO
        )
    ]

    cache.set(cache_key, comentarios, CACHE_TTL_COMENTARIOS)
    return comentarios


def invalidar_cache_comentarios(issue_number):
    """Borra la caché de comentarios de un issue.

    Se llama tras publicar un comentario nuestro (ej. al resolver) para que
    el usuario vea su propia acción reflejada de inmediato en vez de esperar
    a que expire el TTL.
    """
    if issue_number:
        cache.delete(CACHE_KEY_COMENTARIOS.format(issue_number=issue_number))


def resolver_ticket(ticket_id, resuelto_por):
    """Marca el ticket como resuelto y cierra su issue en GitHub.

    Orden deliberado — **primero el estado local, después GitHub**: el
    usuario pidió resolver su caso y esa intención no puede perderse porque
    la API de GitHub esté caída. Si el cierre remoto falla, el ticket queda
    igualmente `resuelto` en el portal y se loguea el error; el issue se
    puede cerrar a mano desde GitHub.

    Idempotente: si el ticket ya estaba resuelto no vuelve a llamar a
    GitHub.

    Devuelve `True` si además se cerró el issue en GitHub, `False` si solo
    se resolvió localmente.
    """
    ticket = FeedbackTicket.objects.get(pk=ticket_id)

    if ticket.estado == FeedbackTicket.ESTADO_RESUELTO:
        return True

    ticket.estado = FeedbackTicket.ESTADO_RESUELTO
    ticket.resuelto_por = resuelto_por
    ticket.resuelto_at = timezone.now()
    ticket.save(update_fields=["estado", "resuelto_por", "resuelto_at", "updated_at"])

    if not ticket.github_issue_number:
        return False

    comentario = (
        f"**{resuelto_por}** marcó este reporte como **resuelto** "
        f"desde el portal de SD - Cursos."
    )
    try:
        GitHubFeedbackClient().cerrar_issue(
            ticket.github_issue_number, comentario=comentario
        )
    except GitHubClientError as exc:
        logger.error(
            "Ticket #%s: resuelto localmente pero falló el cierre del issue "
            "#%s en GitHub: %s",
            ticket.pk,
            ticket.github_issue_number,
            exc,
        )
        return False

    invalidar_cache_comentarios(ticket.github_issue_number)
    return True
