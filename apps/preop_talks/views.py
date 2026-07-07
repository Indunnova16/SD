"""
Pre-operational Talks views for SD LMS.
"""

import base64
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.models import User
from apps.accounts.permissions import Rol, require_rol, user_has_rol
from apps.preop_talks.forms import TalkTemplateForm
from apps.preop_talks.models import PreopTalk, TalkAttendee, TalkTemplate
from apps.preop_talks.services import PreopTalkService, TalkAttendeeService


@login_required
@require_GET
def talk_list(request):
    """Talk list page.

    Issue #58, A12-fix (revierte parte del gate de A8): esta página aloja el
    widget `today_talks` — la ÚNICA vía de la UI (navbar) para que un
    Ejecutor llegue a firmar SU charla pre-operacional del día. Gatearla
    completa con `raise_exception=True` (como hacía A8) le tiraba 403 y le
    rompía el flujo diario real.

    Ahora la vista es accesible a cualquier usuario autenticado; el gate se
    mueve a nivel de contenido vía `can_manage` en el contexto (ver
    `talk_list.html`, patrón propio/equipo/todos de A6/A7/A9): el widget
    `today_talks` (propio) siempre visible, la gestión/historial completo
    (todos) solo si `can_manage`. `talks_table` — el endpoint HTMX de la
    tabla paginada completa, dato puramente administrativo — SIGUE gateado
    tal cual con `require_rol(..., raise_exception=True)`.
    """
    can_manage = user_has_rol(request.user, Rol.COORDINADOR, Rol.ADMINISTRADOR)
    context = {"today": timezone.localdate(), "can_manage": can_manage}

    # Check if this is an HTMX request for the table
    if request.headers.get("HX-Request"):
        return talks_table(request)

    return render(request, "preop_talks/talk_list.html", context)


@login_required
@require_GET
def today_talks(request):
    """Get today's talks (HTMX partial)."""
    talks = PreopTalkService.get_today_talks(conducted_by=request.user)
    context = {"talks": talks}
    return render(request, "preop_talks/partials/today_talks.html", context)


@login_required
@require_GET
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, raise_exception=True)
def talks_table(request):
    """Get talks table (HTMX partial).

    Mismo gate que `talk_list` (issue #58, A8) — `talks_table` tiene su propia
    URL (`preop_talks:table`) además de ser invocada internamente por
    `talk_list`; sin este gate un Ejecutor podría ver el listado completo
    pegándole directo a esa URL aunque `talk_list` lo bloquee (hueco visible,
    scope ampliado dentro de A8 — ver notas del sub-item).
    """
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    status = request.GET.get("status")
    search = request.GET.get("search")
    page = request.GET.get("page", 1)

    talks = PreopTalk.objects.select_related("template", "conducted_by").prefetch_related(
        "attendees"
    )

    if date_from:
        talks = talks.filter(scheduled_at__date__gte=date_from)
    if date_to:
        talks = talks.filter(scheduled_at__date__lte=date_to)
    if status:
        talks = talks.filter(status=status)
    if search:
        talks = talks.filter(
            Q(title__icontains=search)
            | Q(project_name__icontains=search)
            | Q(location__icontains=search)
        )

    talks = talks.order_by("-scheduled_at")

    paginator = Paginator(talks, 20)
    page_obj = paginator.get_page(page)

    context = {"talks": page_obj}
    return render(request, "preop_talks/partials/talks_table.html", context)


@login_required
@require_GET
def talk_detail(request, talk_id):
    """Talk detail page."""
    talk = get_object_or_404(
        PreopTalk.objects.select_related("template", "conducted_by"), id=talk_id
    )
    context = {"talk": talk}
    return render(request, "preop_talks/talk_detail.html", context)


@login_required
def talk_create(request):
    """Create a new talk."""
    templates = TalkTemplate.objects.filter(is_active=True).order_by("title")

    if request.method == "POST":
        template_id = request.POST.get("template")
        template = get_object_or_404(TalkTemplate, id=template_id) if template_id else None

        scheduled_at_str = request.POST.get("scheduled_at")
        scheduled_at = (
            datetime.fromisoformat(scheduled_at_str) if scheduled_at_str else timezone.now()
        )

        if template:
            talk = PreopTalkService.create_talk_from_template(
                template=template,
                conducted_by=request.user,
                project_name=request.POST.get("project_name", ""),
                location=request.POST.get("location", ""),
                work_activity=request.POST.get("work_activity", ""),
                scheduled_at=scheduled_at,
            )
        else:
            talk = PreopTalkService.create_custom_talk(
                title=request.POST.get("title", "Charla Preoperacional"),
                content=request.POST.get("content", ""),
                conducted_by=request.user,
                project_name=request.POST.get("project_name", ""),
                location=request.POST.get("location", ""),
                work_activity=request.POST.get("work_activity", ""),
                scheduled_at=scheduled_at,
            )

        messages.success(request, "Charla creada exitosamente")
        return redirect("preop_talks:detail", talk_id=talk.id)

    context = {"templates": templates}
    return render(request, "preop_talks/talk_form.html", context)


@login_required
@require_GET
def talk_conduct(request, talk_id):
    """Conduct talk page (interactive)."""
    talk = get_object_or_404(
        PreopTalk.objects.select_related("template", "conducted_by"), id=talk_id
    )

    # Only conductor can access
    if talk.conducted_by != request.user and not user_has_rol(request.user, Rol.ADMINISTRADOR):
        messages.error(request, "No tienes permiso para conducir esta charla")
        return redirect("preop_talks:detail", talk_id=talk.id)

    context = {"talk": talk}
    return render(request, "preop_talks/talk_conduct.html", context)


@login_required
@require_POST
def start_talk(request, talk_id):
    """Start a talk."""
    talk = get_object_or_404(PreopTalk, id=talk_id)

    if talk.conducted_by != request.user and not user_has_rol(request.user, Rol.ADMINISTRADOR):
        return HttpResponse("No autorizado", status=403)

    gps_lat = request.POST.get("gps_latitude")
    gps_lon = request.POST.get("gps_longitude")

    talk = PreopTalkService.start_talk(
        talk,
        gps_latitude=float(gps_lat) if gps_lat else None,
        gps_longitude=float(gps_lon) if gps_lon else None,
    )

    if request.headers.get("HX-Request"):
        return redirect("preop_talks:conduct", talk_id=talk.id)

    return redirect("preop_talks:conduct", talk_id=talk.id)


@login_required
@require_POST
def complete_talk(request, talk_id):
    """Complete a talk."""
    talk = get_object_or_404(PreopTalk, id=talk_id)

    if talk.conducted_by != request.user and not user_has_rol(request.user, Rol.ADMINISTRADOR):
        return HttpResponse("No autorizado", status=403)

    notes = request.POST.get("notes", "")
    talk = PreopTalkService.complete_talk(talk, notes)

    messages.success(request, "Charla completada exitosamente")
    return redirect("preop_talks:detail", talk_id=talk.id)


@login_required
@require_GET
def attendees_list(request, talk_id):
    """Get attendees list (HTMX partial)."""
    talk = get_object_or_404(PreopTalk, id=talk_id)
    attendees = talk.attendees.select_related("user").order_by("user__last_name")

    signed_count = attendees.filter(signed_at__isnull=False).count()
    total = attendees.count()
    signature_percentage = (signed_count / total * 100) if total > 0 else 0

    context = {
        "attendees": attendees,
        "signed_count": signed_count,
        "signature_percentage": signature_percentage,
    }
    return render(request, "preop_talks/partials/attendees_list.html", context)


@login_required
@require_POST
def add_attendee(request, talk_id):
    """Add an attendee to a talk."""
    talk = get_object_or_404(PreopTalk, id=talk_id)
    user_id = request.POST.get("user_id")

    if not user_id:
        return HttpResponse("Usuario no especificado", status=400)

    user = get_object_or_404(User, id=user_id)

    TalkAttendeeService.add_attendee(talk, user)

    return attendees_list(request, talk_id)


@login_required
@require_http_methods(["DELETE"])
def remove_attendee(request, attendee_id):
    """Remove an attendee from a talk."""
    attendee = get_object_or_404(TalkAttendee, id=attendee_id)

    # Can't remove signed attendees
    if attendee.signed_at:
        return HttpResponse("No se puede eliminar un asistente que ya firmó", status=400)

    TalkAttendeeService.remove_attendee(attendee)

    return HttpResponse("")  # Row will be removed


@login_required
@require_POST
def sign_attendance(request, attendee_id):
    """Sign attendance for an attendee."""
    attendee = get_object_or_404(TalkAttendee, id=attendee_id)
    talk_id = attendee.talk_id

    signature_data = request.POST.get("signature")

    # Process signature image
    signature_file = None
    if signature_data and signature_data.startswith("data:image"):
        # Extract base64 data
        format_str, imgstr = signature_data.split(";base64,")
        ext = format_str.split("/")[-1]
        signature_file = ContentFile(
            base64.b64decode(imgstr), name=f"signature_{attendee_id}.{ext}"
        )

    TalkAttendeeService.sign_attendance(attendee, signature_file)

    return attendees_list(request, talk_id)


@login_required
@require_GET
def search_users(request):
    """Search users for adding to talk."""
    search = request.GET.get("search", "")

    if len(search) < 2:
        return HttpResponse("")

    users = User.objects.filter(
        Q(first_name__icontains=search)
        | Q(last_name__icontains=search)
        | Q(document_number__icontains=search)
    ).filter(is_active=True)[:10]

    html = ""
    for user in users:
        html += f"""
        <div class="p-2 hover:bg-base-200 cursor-pointer rounded"
             hx-post="" hx-include="this"
             onclick="document.querySelector('[name=user_id]').value='{user.id}'; this.closest('form').requestSubmit()">
            <input type="hidden" name="user_id" value="{user.id}">
            <div class="font-medium">{user.get_full_name()}</div>
            <div class="text-sm text-gray-500">{user.document_number} - {user.job_position}</div>
        </div>
        """

    return HttpResponse(
        html
        if users
        else '<p class="text-center py-4 text-gray-500">No se encontraron usuarios</p>'
    )


@login_required
@require_POST
def update_notes(request, talk_id):
    """Update talk notes/risks (auto-save)."""
    talk = get_object_or_404(PreopTalk, id=talk_id)

    if "risks_identified" in request.POST:
        talk.risks_identified = request.POST.get("risks_identified", "")
    if "notes" in request.POST:
        talk.notes = request.POST.get("notes", "")

    talk.save()

    return HttpResponse("")  # Silent save


@login_required
@require_GET
def talk_report(request, talk_id):
    """Generate talk report."""
    talk = get_object_or_404(
        PreopTalk.objects.select_related("template", "conducted_by"), id=talk_id
    )
    attendees = talk.attendees.select_related("user").order_by("user__last_name")

    context = {
        "talk": talk,
        "attendees": attendees,
        "signed_count": attendees.filter(signed_at__isnull=False).count(),
    }
    return render(request, "preop_talks/talk_report.html", context)


@login_required
@require_GET
def templates_list(request):
    """Talk templates list."""
    templates = TalkTemplate.objects.filter(is_active=True).order_by("title")
    context = {"templates": templates}
    return render(request, "preop_talks/templates_list.html", context)


@login_required
def template_create(request):
    """Create a new talk template."""
    if request.method == "POST":
        form = TalkTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.save()
            messages.success(request, "Plantilla creada exitosamente")
            return redirect("preop_talks:templates")
    else:
        form = TalkTemplateForm()

    context = {"form": form, "title": "Nueva Plantilla"}
    return render(request, "preop_talks/template_form.html", context)
