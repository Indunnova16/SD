"""
Lessons Learned views for SD LMS.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import Rol, require_rol, user_has_rol
from apps.lessons_learned.models import Category, LessonLearned
from apps.lessons_learned.services import (
    LessonCommentService,
    LessonLearnedService,
)


@login_required
@require_GET
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, raise_exception=True)
def lesson_list(request):
    """Lesson list page.

    Listado ADMINISTRATIVO (issue #58, A8): oculto para Ejecutor (403), completo
    para Coordinador/Administrador. No afecta `my_lessons` (propias lecciones
    del Ejecutor) ni `lesson_detail`/`lesson_create`/`lesson_edit` — ver PLAN A8.
    """
    categories = Category.objects.filter(is_active=True).order_by("name")

    context = {
        "categories": categories,
    }

    # Check if this is an HTMX request for the grid
    if request.headers.get("HX-Request"):
        return lesson_grid(request)

    return render(request, "lessons_learned/lesson_list.html", context)


@login_required
@require_GET
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, raise_exception=True)
def lesson_grid(request):
    """Get lesson grid (HTMX partial).

    Mismo gate que `lesson_list` (issue #58, A8) — tiene su propia URL
    (`lessons_learned:grid`) además de ser invocada internamente por
    `lesson_list`; sin este gate un Ejecutor podría ver el listado completo
    pegándole directo a esa URL (hueco visible, scope ampliado dentro de A8).
    """
    category_id = request.GET.get("category")
    severity = request.GET.get("severity")
    lesson_type = request.GET.get("type")
    search = request.GET.get("search")
    page = request.GET.get("page", 1)

    # Get approved lessons
    category = None
    if category_id:
        category = Category.objects.filter(id=category_id, is_active=True).first()

    lessons = LessonLearnedService.get_approved_lessons(
        category=category,
        lesson_type=lesson_type,
        severity=severity,
        search=search,
    )

    paginator = Paginator(lessons, 12)
    page_obj = paginator.get_page(page)

    context = {"lessons": page_obj}
    return render(request, "lessons_learned/partials/lesson_grid.html", context)


@login_required
@require_GET
def lesson_detail(request, lesson_id):
    """Lesson detail page."""
    lesson = get_object_or_404(
        LessonLearned.objects.select_related("created_by", "category"), id=lesson_id
    )

    # Increment view count
    LessonLearnedService.increment_view_count(lesson)

    context = {"lesson": lesson}
    return render(request, "lessons_learned/lesson_detail.html", context)


@login_required
def lesson_create(request):
    """Create a new lesson."""
    categories = Category.objects.filter(is_active=True)

    if request.method == "POST":
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id) if category_id else None

        lesson = LessonLearnedService.create_lesson(
            title=request.POST.get("title", ""),
            description=request.POST.get("description", ""),
            category=category,
            situation=request.POST.get("situation", ""),
            lesson=request.POST.get("lesson", ""),
            recommendations=request.POST.get("recommendations", ""),
            created_by=request.user,
            lesson_type=request.POST.get("lesson_type", LessonLearned.Type.OBSERVATION),
            severity=request.POST.get("severity", LessonLearned.Severity.MEDIUM),
            root_cause=request.POST.get("root_cause", ""),
            location=request.POST.get("location", ""),
            date_occurred=request.POST.get("date_occurred") or None,
        )

        messages.success(request, "Lección creada exitosamente")
        return redirect("lessons_learned:detail", lesson_id=lesson.id)

    context = {"categories": categories}
    return render(request, "lessons_learned/lesson_form.html", context)


@login_required
def lesson_edit(request, lesson_id):
    """Edit a lesson."""
    lesson = get_object_or_404(LessonLearned, id=lesson_id)

    # Check permissions
    if lesson.created_by != request.user and not user_has_rol(request.user, Rol.ADMINISTRADOR):
        messages.error(request, "No tienes permiso para editar esta lección")
        return redirect("lessons_learned:detail", lesson_id=lesson.id)

    categories = Category.objects.filter(is_active=True)

    if request.method == "POST":
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id) if category_id else lesson.category

        lesson = LessonLearnedService.update_lesson(
            lesson=lesson,
            title=request.POST.get("title", ""),
            description=request.POST.get("description", ""),
            category=category,
            situation=request.POST.get("situation", ""),
            lesson_text=request.POST.get("lesson", ""),
            recommendations=request.POST.get("recommendations", ""),
            lesson_type=request.POST.get("lesson_type", lesson.lesson_type),
            severity=request.POST.get("severity", lesson.severity),
            root_cause=request.POST.get("root_cause", ""),
            location=request.POST.get("location", ""),
            date_occurred=request.POST.get("date_occurred") or None,
        )

        messages.success(request, "Lección actualizada exitosamente")
        return redirect("lessons_learned:detail", lesson_id=lesson.id)

    context = {"lesson": lesson, "categories": categories}
    return render(request, "lessons_learned/lesson_form.html", context)


@login_required
@require_POST
def submit_for_review(request, lesson_id):
    """Submit lesson for review."""
    lesson = get_object_or_404(LessonLearned, id=lesson_id)

    if lesson.created_by != request.user:
        return HttpResponse("No autorizado", status=403)

    LessonLearnedService.submit_for_review(lesson)

    if request.headers.get("HX-Request"):
        return HttpResponse('<span class="badge badge-warning">Pendiente revisión</span>')

    messages.success(request, "Lección enviada para revisión")
    return redirect("lessons_learned:detail", lesson_id=lesson.id)


@login_required
@require_POST
def approve_lesson(request, lesson_id):
    """Approve a lesson (staff only)."""
    if not user_has_rol(request.user, Rol.ADMINISTRADOR):
        return HttpResponse("No autorizado", status=403)

    lesson = get_object_or_404(LessonLearned, id=lesson_id)
    notes = request.POST.get("notes", "")

    LessonLearnedService.approve_lesson(lesson, request.user, notes)

    if request.headers.get("HX-Request"):
        return HttpResponse('<span class="badge badge-success">Aprobada</span>')

    messages.success(request, "Lección aprobada")
    return redirect("lessons_learned:detail", lesson_id=lesson.id)


@login_required
@require_POST
def reject_lesson(request, lesson_id):
    """Reject a lesson (staff only)."""
    if not user_has_rol(request.user, Rol.ADMINISTRADOR):
        return HttpResponse("No autorizado", status=403)

    lesson = get_object_or_404(LessonLearned, id=lesson_id)
    reason = request.POST.get("reason", "")

    if not reason:
        return HttpResponse("Debe indicar el motivo del rechazo", status=400)

    LessonLearnedService.reject_lesson(lesson, request.user, reason)

    if request.headers.get("HX-Request"):
        return HttpResponse('<span class="badge badge-error">Rechazada</span>')

    messages.info(request, "Lección rechazada")
    return redirect("lessons_learned:detail", lesson_id=lesson.id)


@login_required
@require_POST
def add_comment(request, lesson_id):
    """Add a comment to a lesson."""
    lesson = get_object_or_404(LessonLearned, id=lesson_id)
    content = request.POST.get("content", "").strip()

    if not content:
        return HttpResponse("El comentario no puede estar vacío", status=400)

    comment = LessonCommentService.add_comment(lesson, request.user, content)

    # Return the new comment HTML
    context = {"comment": comment}
    return render(request, "lessons_learned/partials/comment_item.html", context)


@login_required
@require_GET
def my_lessons(request):
    """Get user's lessons."""
    lessons = LessonLearned.objects.filter(created_by=request.user).order_by("-created_at")

    context = {"lessons": lessons}
    return render(request, "lessons_learned/my_lessons.html", context)
