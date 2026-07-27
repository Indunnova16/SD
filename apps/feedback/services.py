"""
Capa de servicio del portal público de feedback (apps.feedback).

Dos responsabilidades separadas:

1. `procesar_archivos_subidos`: valida y guarda las imágenes adjuntas a un
   ticket ya creado. `FeedbackAttachment.objects.create(imagen=archivo)`
   fuera de un `ModelForm` NO ejecuta `full_clean()` — los validadores
   nativos de `ImageField` (Pillow) no corren automáticamente. En un form
   público anónimo esto deja abierta la superficie de "sube cualquier
   archivo con extensión de imagen falsa". Por eso este módulo valida
   EXPLÍCITAMENTE antes de crear cada `FeedbackAttachment`, best-effort por
   archivo: uno inválido nunca tumba el ticket ni los demás adjuntos.

2. `sincronizar_ticket` / `encolar_sincronizacion_ticket`: sincroniza el
   ticket como un GitHub Issue de forma síncrona (sin Celery, mismo patrón
   que Arcopack), disparada vía `transaction.on_commit` para que solo
   corra si el ticket+adjuntos ya quedaron persistidos en BD. Un fallo de
   GitHub NUNCA borra ni invalida el ticket: queda registrado con
   `sincronizado_github=False` + `error_sincronizacion` poblado.
"""

import logging

from django.conf import settings
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from apps.feedback.github_client import GitHubClientError, GitHubFeedbackClient
from apps.feedback.models import FeedbackAttachment, FeedbackTicket

logger = logging.getLogger(__name__)


def procesar_archivos_subidos(ticket, archivos):
    """Valida y guarda como `FeedbackAttachment` los archivos subidos.

    Recibe el `FeedbackTicket` ya guardado y una lista de `UploadedFile`
    (típicamente `request.FILES.getlist(...)`). Por cada archivo valida,
    en orden, EXPLÍCITAMENTE (porque `.create()` fuera de un `ModelForm`
    no dispara `full_clean()`):

        a. `content_type` empieza con 'image/'.
        b. `size <= settings.FEEDBACK_MAX_ATTACHMENT_BYTES`.
        c. El contenido real es una imagen válida (`PIL.Image.verify()`),
           defensivo contra content-type spoofeado.

    Un archivo que falla cualquiera de las 3 validaciones NO se guarda,
    se loguea como warning, y se continúa con el resto — un archivo
    inválido no debe tumbar la creación del ticket ni de los demás
    adjuntos válidos. Respeta `settings.FEEDBACK_MAX_ATTACHMENTS`: si
    vienen más archivos que el límite, solo se procesan los primeros N
    (se loguea que se truncó, no se falla).

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

        content_type = getattr(archivo, "content_type", "") or ""
        if not content_type.startswith("image/"):
            logger.warning(
                "Ticket #%s: archivo '%s' descartado — content_type '%s' "
                "no es de imagen.",
                ticket.pk,
                nombre,
                content_type,
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

        try:
            archivo.seek(0)
            Image.open(archivo).verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            logger.warning(
                "Ticket #%s: archivo '%s' descartado — contenido no es una "
                "imagen válida (posible content-type spoofeado): %s",
                ticket.pk,
                nombre,
                exc,
            )
            continue
        finally:
            archivo.seek(0)

        adjunto = FeedbackAttachment.objects.create(
            ticket=ticket,
            imagen=archivo,
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
                {"nombre": adjunto.nombre_original, "url": adjunto.imagen.url}
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
