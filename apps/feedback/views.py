"""
Vistas públicas del portal de feedback ("portal de SD - Cursos").

Superficie 100% pública/anónima (sin `@login_required`, sin sesión SD):
listar tickets, crear un ticket nuevo (con 0-N adjuntos: imagen, audio o
video), ver el detalle de un ticket — sus adjuntos y la conversación del
equipo traída de GitHub — y marcar el caso como resuelto.

`nuevo_view` delega la creación de adjuntos y la sincronización a GitHub en
`apps.feedback.services` (sub-item A4): `procesar_archivos_subidos` y
`encolar_sincronizacion_ticket` corren DENTRO de un `transaction.atomic()`
junto con la creación del `FeedbackTicket` (issue #81) — así (a)
`transaction.on_commit` (usado por `encolar_sincronizacion_ticket`) se
dispara justo al terminar la request, y (b) si algo revienta procesando un
adjunto, el ticket entero se revierte en vez de quedar huérfano en BD sin
sincronizar.
"""

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.feedback.forms import NuevoTicketForm, ResolverTicketForm
from apps.feedback.github_client import GitHubClientError
from apps.feedback.models import FeedbackTicket
from apps.feedback.services import (
    encolar_sincronizacion_ticket,
    obtener_comentarios_github,
    procesar_archivos_subidos,
    resolver_ticket,
)

TICKETS_POR_PAGINA = 20


def lista_view(request):
    """Tablero público: lista TODOS los tickets, paginados, más recientes primero.

    Sin filtro de estado — ese campo no existe en el modelo v1.0.
    """
    tickets = FeedbackTicket.objects.all().order_by("-created_at")
    paginator = Paginator(tickets, TICKETS_POR_PAGINA)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {"page_obj": page_obj, "tickets": page_obj}
    return render(request, "feedback/lista.html", context)


def nuevo_view(request):
    """Muestra (GET) o procesa (POST) el formulario público de nuevo ticket."""
    if request.method == "POST":
        form = NuevoTicketForm(request.POST)
        if form.is_valid():
            # `transaction.atomic()` envuelve la creación del ticket + el
            # procesamiento de adjuntos + el encolado de sincronización
            # (issue #81): si CUALQUIER excepción escapa dentro del bloque
            # (ej. una variante de PIL no contemplada por el except de
            # `procesar_archivos_subidos`), Django hace ROLLBACK del
            # INSERT del ticket — nunca queda un `FeedbackTicket` huérfano
            # en BD (creado pero sin adjuntos procesados ni sincronización
            # encolada). Es la red de seguridad estructural; el except
            # ampliado de `services.py` es la que evita el 500 en sí.
            with transaction.atomic():
                ticket = FeedbackTicket.objects.create(
                    nombre_reportante=form.cleaned_data["nombre_reportante"],
                    asunto=form.cleaned_data["asunto"],
                    descripcion=form.cleaned_data["descripcion"],
                )
                procesar_archivos_subidos(
                    ticket, request.FILES.getlist("imagenes")
                )
                # Debe ir DENTRO de este mismo bloque: transaction.on_commit
                # necesita dispararse cuando la transacción de esta request
                # (ticket + adjuntos) termine de committear.
                encolar_sincronizacion_ticket(ticket.id)

            messages.success(
                request, "¡Gracias! Tu reporte fue registrado correctamente."
            )
            return redirect("feedback:detalle", ticket_id=ticket.id)
    else:
        form = NuevoTicketForm()

    # Los límites van al template para que el JS del grabador rechace en el
    # cliente exactamente lo mismo que `procesar_archivos_subidos` descarta
    # en el servidor. Duplicarlos hardcodeados en el JS es cómo se
    # desincronizan.
    context = {
        "form": form,
        "max_attachments": settings.FEEDBACK_MAX_ATTACHMENTS,
        "max_attachment_bytes": settings.FEEDBACK_MAX_ATTACHMENT_BYTES,
    }
    return render(request, "feedback/nuevo.html", context)


def detalle_view(request, ticket_id):
    """Detalle público de un ticket: adjuntos + conversación de GitHub.

    Los comentarios se traen de la API de GitHub en vivo (con caché corta,
    ver `services.obtener_comentarios_github`). Si GitHub falla, la página
    se renderiza igual con `comentarios_error=True` — el detalle del ticket
    nunca depende de que GitHub esté arriba.
    """
    ticket = get_object_or_404(FeedbackTicket, id=ticket_id)
    adjuntos = ticket.adjuntos.all()

    comentarios = []
    comentarios_error = False
    try:
        comentarios = obtener_comentarios_github(ticket)
    except GitHubClientError:
        comentarios_error = True

    context = {
        "ticket": ticket,
        "adjuntos": adjuntos,
        "comentarios": comentarios,
        "comentarios_error": comentarios_error,
        "resolver_form": ResolverTicketForm(),
    }
    return render(request, "feedback/detalle.html", context)


@require_POST
def resolver_view(request, ticket_id):
    """Marca un ticket como resuelto y cierra su issue en GitHub.

    Sin autenticación, por diseño: el portal es 100% anónimo y el criterio
    del protocolo es que **el cliente cierra al validar**. La trazabilidad
    es el nombre que se pide en el form; si alguien resuelve por error, el
    equipo reabre desde GitHub.

    Solo POST (`@require_POST`): resolver es una acción con efecto, no debe
    poder dispararse con un GET (un prefetch del navegador o un crawler
    cerraría tickets ajenos).
    """
    ticket = get_object_or_404(FeedbackTicket, id=ticket_id)

    if ticket.esta_resuelto:
        messages.info(request, "Este ticket ya estaba marcado como resuelto.")
        return redirect("feedback:detalle", ticket_id=ticket.id)

    form = ResolverTicketForm(request.POST)
    if not form.is_valid():
        adjuntos = ticket.adjuntos.all()
        comentarios = []
        comentarios_error = False
        try:
            comentarios = obtener_comentarios_github(ticket)
        except GitHubClientError:
            comentarios_error = True
        context = {
            "ticket": ticket,
            "adjuntos": adjuntos,
            "comentarios": comentarios,
            "comentarios_error": comentarios_error,
            "resolver_form": form,
        }
        return render(request, "feedback/detalle.html", context)

    cerrado_en_github = resolver_ticket(
        ticket.id, form.cleaned_data["resuelto_por"]
    )
    if cerrado_en_github:
        messages.success(request, "¡Listo! El caso quedó marcado como resuelto.")
    else:
        # El ticket SÍ quedó resuelto localmente (ver services.resolver_ticket):
        # no mentimos diciendo que falló, pero tampoco afirmamos que se
        # cerró en GitHub cuando no pudimos confirmarlo.
        messages.success(
            request,
            "El caso quedó marcado como resuelto. Estamos terminando de "
            "sincronizarlo con el equipo.",
        )
    return redirect("feedback:detalle", ticket_id=ticket.id)
