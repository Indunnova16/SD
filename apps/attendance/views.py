"""
Vistas de asistencia con reconocimiento facial.

- `mobile_face_checkin`  : kiosko PÚBLICO (sin login). Identifica 1:N por selfie.
- `mobile_face_qr`       : QR a la URL del kiosko (rol=ADMINISTRADOR).
- `face_event_list`      : auditoría de marcaciones — listado ADMINISTRATIVO
                           (issue #58, A8): oculto para Ejecutor (403), completo
                           para Coordinador/Administrador. NO afecta el kiosko
                           público (`mobile_face_checkin`), que sigue siendo la
                           vía por la que el Ejecutor marca su propia asistencia.
- `reindex_user_face`    : (re)indexa la foto de un usuario en Rekognition
                           (rol=ADMINISTRADOR, sin cambio en A8 — fuera del
                           alcance del "listado" que pide el PLAN).
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import Rol, require_rol, user_has_rol

from .models import FaceCheckEvent
from .services import AttendanceService

User = get_user_model()
logger = logging.getLogger(__name__)


def _staff_required(view):
    """Decorator: solo usuarios con rol=ADMINISTRADOR (issue #58, ex-staff)."""
    return user_passes_test(lambda u: user_has_rol(u, Rol.ADMINISTRADOR))(view)


# ───────────────────────── Kiosko público ─────────────────────────


@require_http_methods(["GET", "POST"])
def mobile_face_checkin(request):
    """
    Vista pública (sin login) para que el personal tome selfie en su celular y
    el sistema lo identifique por reconocimiento facial (AWS Rekognition 1:N).

    GET: pinta la página con cámara.
    POST (multipart): `selfie` (archivo) + `kind` (check_in/check_out) +
    `latitude`/`longitude` opcionales. Si hay match crea/actualiza el
    AttendanceRecord del día y responde JSON.
    """
    if request.method == "GET":
        return render(request, "attendance/mobile_face_checkin.html")

    from .services_rekognition import (
        NoFaceDetectedError,
        RekognitionError,
        RekognitionService,
    )

    selfie = request.FILES.get("selfie")
    kind = request.POST.get("kind", "").strip()
    latitude = request.POST.get("latitude") or None
    longitude = request.POST.get("longitude") or None

    if kind not in (FaceCheckEvent.KIND_CHECK_IN, FaceCheckEvent.KIND_CHECK_OUT):
        return JsonResponse({"ok": False, "error": "kind inválido"}, status=400)
    if not selfie:
        return JsonResponse({"ok": False, "error": "No se recibió selfie"}, status=400)

    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR"
    )
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]

    event = FaceCheckEvent(
        kind=kind,
        selfie=selfie,
        latitude=latitude,
        longitude=longitude,
        user_agent=ua,
        ip_address=ip,
        status=FaceCheckEvent.STATUS_ERROR,
    )

    # Leer bytes para enviar a Rekognition (selfie ya está en event.selfie).
    selfie.seek(0)
    image_bytes = selfie.read()

    try:
        result = RekognitionService.search_face(image_bytes)
    except NoFaceDetectedError as exc:
        event.status = FaceCheckEvent.STATUS_NO_FACE
        event.error_message = str(exc)[:255]
        event.save()
        return JsonResponse(
            {
                "ok": False,
                "status": event.status,
                "error": "No se detectó un rostro en la foto. Intenta con buena iluminación.",
            },
            status=200,
        )
    except RekognitionError as exc:
        logger.warning("Rekognition error en marcación: %s", exc)
        event.status = FaceCheckEvent.STATUS_ERROR
        event.error_message = str(exc)[:255]
        event.save()
        return JsonResponse(
            {
                "ok": False,
                "status": event.status,
                "error": "Error del servicio de reconocimiento. Intenta nuevamente.",
            },
            status=200,
        )

    event.similarity = result.similarity
    event.aws_face_id = result.aws_face_id

    if not result.matched:
        event.status = (
            FaceCheckEvent.STATUS_LOW_CONFIDENCE
            if result.similarity > 0
            else FaceCheckEvent.STATUS_NO_MATCH
        )
        event.save()
        return JsonResponse(
            {
                "ok": False,
                "status": event.status,
                "similarity": float(result.similarity),
                "error": "No coincide con ningún usuario registrado.",
            },
            status=200,
        )

    # Match: crear o actualizar el AttendanceRecord del día.
    user = result.user
    if kind == FaceCheckEvent.KIND_CHECK_IN:
        record = AttendanceService.check_in(user, registered_by=None)
    else:
        record = AttendanceService.check_out(user, registered_by=None)

    event.user = user
    event.attendance_record = record
    event.status = FaceCheckEvent.STATUS_MATCHED
    event.save()

    local_now = timezone.localtime()
    time_obj = record.check_in if kind == FaceCheckEvent.KIND_CHECK_IN else record.check_out
    time_str = local_now.replace(hour=time_obj.hour, minute=time_obj.minute).strftime("%H:%M")
    return JsonResponse(
        {
            "ok": True,
            "status": event.status,
            "employee_name": user.get_full_name() or str(user),
            "cargo": getattr(user, "job_position", "") or "",
            "similarity": float(result.similarity),
            "kind": kind,
            "time": time_str,
            "date": local_now.strftime("%Y-%m-%d"),
        }
    )


# ───────────────────────── QR (staff) ─────────────────────────


@_staff_required
def mobile_face_qr(request):
    checkin_url = request.build_absolute_uri(reverse("attendance:mobile_face_checkin"))
    return render(
        request,
        "attendance/mobile_face_qr.html",
        {"checkin_url": checkin_url},
    )


# ────────────────── Auditoría (Coordinador/Administrador) ──────────────────


@login_required
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, raise_exception=True)
def face_event_list(request):
    """Listado ADMINISTRATIVO de marcaciones (issue #58, A8).

    Oculto para Ejecutor (403 explícito, ver PLAN A8), completo para
    Coordinador/Administrador — a diferencia de `mobile_face_qr` y
    `reindex_user_face` (abajo), que siguen restringidos a ADMINISTRADOR vía
    `_staff_required` (sin cambio, fuera del alcance de A8: el PLAN solo pide
    ampliar el listado, no estas otras dos acciones de configuración).
    """
    qs = FaceCheckEvent.objects.select_related("user").order_by("-created_at")

    status = request.GET.get("status", "").strip()
    kind = request.GET.get("kind", "").strip()
    if status:
        qs = qs.filter(status=status)
    if kind:
        qs = qs.filter(kind=kind)

    today = timezone.localdate()
    today_stats = FaceCheckEvent.objects.filter(created_at__date=today).aggregate(
        total=Count("id"),
        matched=Count("id", filter=Q(status=FaceCheckEvent.STATUS_MATCHED)),
        no_match=Count("id", filter=Q(status=FaceCheckEvent.STATUS_NO_MATCH)),
        low_conf=Count("id", filter=Q(status=FaceCheckEvent.STATUS_LOW_CONFIDENCE)),
        no_face=Count("id", filter=Q(status=FaceCheckEvent.STATUS_NO_FACE)),
        errors=Count("id", filter=Q(status=FaceCheckEvent.STATUS_ERROR)),
    )

    return render(
        request,
        "attendance/face_event_list.html",
        {
            "events": qs[:200],
            "today": today,
            "today_stats": today_stats,
            "status_choices": FaceCheckEvent.STATUS_CHOICES,
            "kind_choices": FaceCheckEvent.KIND_CHOICES,
            "filter_status": status,
            "filter_kind": kind,
        },
    )


# ───────────────────────── Reindexado de rostro (staff) ─────────────────────────


@_staff_required
@require_http_methods(["POST"])
def reindex_user_face(request, pk):
    from .services_rekognition import (
        MissingReferencePhotoError,
        NoFaceDetectedError,
        RekognitionError,
        RekognitionService,
    )

    user = get_object_or_404(User, pk=pk)
    if not user.photo:
        messages.warning(request, f"{user} no tiene foto de referencia.")
        return redirect(request.META.get("HTTP_REFERER", reverse("attendance:face_event_list")))

    try:
        RekognitionService.index_user_face(user)
        messages.success(request, f"Rostro indexado correctamente para {user}.")
    except NoFaceDetectedError as exc:
        messages.warning(request, f"No se detectó un rostro válido: {exc}")
    except MissingReferencePhotoError as exc:
        messages.error(request, str(exc))
    except RekognitionError as exc:
        messages.error(request, f"Error AWS Rekognition: {exc}")

    return redirect(request.META.get("HTTP_REFERER", reverse("attendance:face_event_list")))
