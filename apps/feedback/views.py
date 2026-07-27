"""
Vistas públicas del portal de feedback ("portal de SD - Cursos").

Superficie 100% pública/anónima (sin `@login_required`, sin sesión SD):
listar tickets, crear un ticket nuevo (con 0-N imágenes adjuntas) y ver el
detalle de un ticket, incluidas sus imágenes.

`nuevo_view` delega la creación de adjuntos y la sincronización a GitHub en
`apps.feedback.services` (sub-item A4): `procesar_archivos_subidos` y
`encolar_sincronizacion_ticket` corren DENTRO del mismo bloque que crea el
`FeedbackTicket`, para que `transaction.on_commit` (usado por
`encolar_sincronizacion_ticket`) se dispare justo al terminar la request.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.feedback.forms import NuevoTicketForm
from apps.feedback.models import FeedbackTicket
from apps.feedback.services import (
    encolar_sincronizacion_ticket,
    procesar_archivos_subidos,
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
            ticket = FeedbackTicket.objects.create(
                nombre_reportante=form.cleaned_data["nombre_reportante"],
                asunto=form.cleaned_data["asunto"],
                descripcion=form.cleaned_data["descripcion"],
            )
            procesar_archivos_subidos(ticket, request.FILES.getlist("imagenes"))
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

    return render(request, "feedback/nuevo.html", {"form": form})


def detalle_view(request, ticket_id):
    """Detalle público de un ticket, incluidas las imágenes que subió."""
    ticket = get_object_or_404(FeedbackTicket, id=ticket_id)
    adjuntos = ticket.adjuntos.all()

    context = {"ticket": ticket, "adjuntos": adjuntos}
    return render(request, "feedback/detalle.html", context)
