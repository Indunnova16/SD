"""
Web views for courses app.
"""

import base64
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    AssessmentEditForm,
    AttendanceSignatureForm,
    CategoryForm,
    CourseCreateForm,
    CourseEditParamsForm,
    CourseFullEditForm,
    JobProfileTypeForm,
    LessonBuilderForm,
    ModuleBuilderForm,
    QuickAssessmentForm,
)
from .models import (
    AttendanceSignature,
    Category,
    Course,
    Enrollment,
    JobProfileType,
    Lesson,
    LessonProgress,
    Module,
)
from .services import EnrollmentService
from .utils import get_client_ip


@login_required
def course_list(request):
    """List all published courses."""
    courses = (
        Course.objects.filter(status=Course.Status.PUBLISHED)
        .select_related("category", "created_by")
        .prefetch_related("modules")
        .annotate(modules_count=Count("modules"))
    )

    # Filtering
    category_slug = request.GET.get("category")

    if category_slug:
        courses = courses.filter(category__slug=category_slug)

    course_type = request.GET.get("type")
    if course_type:
        courses = courses.filter(course_type=course_type)

    search = request.GET.get("search")
    if search:
        courses = courses.filter(Q(title__icontains=search) | Q(description__icontains=search))

    # Get categories for filter
    categories = Category.objects.filter(is_active=True).annotate(
        course_count=Count("courses", filter=Q(courses__status="published"))
    )

    # Get user's enrollments
    user_enrollments = set(
        Enrollment.objects.filter(user=request.user).values_list("course_id", flat=True)
    )

    context = {
        "courses": courses,
        "categories": categories,
        "user_enrollments": user_enrollments,
        "current_category": category_slug,
        "current_type": course_type,
        "search_query": search,
    }
    return render(request, "courses/course_list.html", context)


@login_required
def course_detail(request, course_id):
    """View course details."""
    course = get_object_or_404(
        Course.objects.select_related("category", "created_by").prefetch_related(
            "modules__lessons", "prerequisites"
        ),
        id=course_id,
    )

    # Check if user is enrolled
    enrollment = Enrollment.objects.filter(user=request.user, course=course).first()

    # Get lesson progress and accessibility if enrolled
    lesson_progress = {}
    lesson_accessibility = {}
    if enrollment:
        progress_qs = LessonProgress.objects.filter(enrollment=enrollment)
        lesson_progress = {lp.lesson_id: lp for lp in progress_qs}
        lesson_accessibility = EnrollmentService.get_lesson_accessibility_map(enrollment)

    context = {
        "course": course,
        "enrollment": enrollment,
        "lesson_progress": lesson_progress,
        "lesson_accessibility": lesson_accessibility,
    }
    return render(request, "courses/course_detail.html", context)


@login_required
@require_http_methods(["POST"])
def enroll_course(request, course_id):
    """Enroll current user in a course."""
    course = get_object_or_404(Course, id=course_id, status=Course.Status.PUBLISHED)

    # Check prerequisites
    if course.prerequisites.exists():
        completed_prereqs = Enrollment.objects.filter(
            user=request.user,
            course__in=course.prerequisites.all(),
            status=Enrollment.Status.COMPLETED,
        ).count()

        if completed_prereqs < course.prerequisites.count():
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "courses/partials/enroll_error.html",
                    {"error": "Debes completar los prerrequisitos primero."},
                )
            return redirect("courses:detail", course_id=course_id)

    enrollment, created = Enrollment.objects.get_or_create(
        user=request.user,
        course=course,
        defaults={"assigned_by": request.user},
    )

    if request.headers.get("HX-Request"):
        return render(
            request,
            "courses/partials/enrollment_status.html",
            {"enrollment": enrollment, "course": course},
        )
    return redirect("courses:detail", course_id=course_id)


@login_required
def lesson_view(request, course_id, lesson_id):
    """View a lesson."""
    from datetime import date

    from dateutil.relativedelta import relativedelta

    course = get_object_or_404(Course, id=course_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)

    # Get or create enrollment
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)

    # Start the course timer on first lesson access
    if not enrollment.started_at:
        enrollment.started_at = timezone.now()
        if enrollment.status == Enrollment.Status.ENROLLED:
            enrollment.status = Enrollment.Status.IN_PROGRESS
        # Calculate due_date based on course validity
        if not enrollment.due_date and course.validity_months:
            enrollment.due_date = date.today() + relativedelta(months=course.validity_months)
        enrollment.save()

    # Check lesson accessibility (sequential locking)
    is_accessible, blocking_lesson = EnrollmentService.is_lesson_accessible(enrollment, lesson)
    if not is_accessible:
        messages.warning(
            request,
            f'Debes completar la leccion "{blocking_lesson.title}" primero.',
        )
        return redirect("courses:detail", course_id=course_id)

    # Get or create lesson progress
    progress, _ = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
    )

    # Get next and previous lessons
    all_lessons = list(
        Lesson.objects.filter(module__course=course).order_by("module__order", "order")
    )
    current_index = next((i for i, lsn in enumerate(all_lessons) if lsn.id == lesson.id), 0)
    prev_lesson = all_lessons[current_index - 1] if current_index > 0 else None
    next_lesson = all_lessons[current_index + 1] if current_index < len(all_lessons) - 1 else None

    # Check if next lesson is accessible
    next_lesson_accessible = True
    if next_lesson:
        accessible, _ = EnrollmentService.is_lesson_accessible(enrollment, next_lesson)
        next_lesson_accessible = accessible

    # Get lesson evidence for presential lessons
    lesson_evidence = None
    if lesson.is_presential:
        lesson_evidence = LessonEvidence.objects.filter(lesson=lesson, user=request.user).first()

    # Get assessment for quiz lessons
    assessment = None
    if lesson.lesson_type == "quiz":
        assessment = lesson.assessments.first()

    context = {
        "course": course,
        "lesson": lesson,
        "progress": progress,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "next_lesson_accessible": next_lesson_accessible,
        "enrollment": enrollment,
        "lesson_evidence": lesson_evidence,
        "assessment": assessment,
    }
    return render(request, "courses/lesson_view.html", context)


@login_required
def lesson_content_file(request, course_id, lesson_id):
    """Serve lesson content file with proper headers (for PDF viewing, etc.)."""
    course = get_object_or_404(Course, id=course_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)

    if not lesson.content_file:
        return HttpResponse("Archivo no disponible", status=404)

    response = FileResponse(lesson.content_file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{lesson.content_file.name.split("/")[-1]}"'
    )
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@login_required
@require_http_methods(["POST"])
def update_progress(request, course_id, lesson_id):
    """Update lesson progress via HTMX."""
    course = get_object_or_404(Course, id=course_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)

    progress, _ = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
    )

    # Update progress
    new_progress = request.POST.get("progress", 0)
    progress.progress_percent = min(float(new_progress), 100)

    if progress.progress_percent >= 100:
        progress.is_completed = True
        from django.utils import timezone

        progress.completed_at = timezone.now()

    progress.save()

    # Update enrollment progress using the service
    EnrollmentService.update_enrollment_progress(enrollment)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "courses/partials/progress_bar.html",
            {"progress": progress, "enrollment": enrollment},
        )

    return JsonResponse({"status": "ok", "progress": float(progress.progress_percent)})


@login_required
@require_http_methods(["POST"])
def update_video_progress(request, course_id, lesson_id):
    """Update video progress from the player (AJAX)."""
    import json

    course = get_object_or_404(Course, id=course_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)

    progress, _ = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
    )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Datos invalidos"}, status=400)

    current_time = float(data.get("current_time", 0))
    max_reached = float(data.get("max_reached", 0))
    duration = float(data.get("duration", 0))
    completed = data.get("completed", False)

    # Anti-cheat: max_reached can only increase
    saved_max = (progress.last_position or {}).get("max_reached", 0)
    max_reached = max(max_reached, saved_max)

    # Update progress
    progress.last_position = {
        "video_seconds": current_time,
        "max_reached": max_reached,
        "duration": duration,
    }

    if duration > 0:
        progress.progress_percent = min((max_reached / duration) * 100, 100)

    progress.time_spent = int(max_reached)

    if completed or (duration > 0 and max_reached / duration >= 0.95):
        if not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = timezone.now()

    progress.save()
    EnrollmentService.update_enrollment_progress(enrollment)

    return JsonResponse(
        {
            "status": "ok",
            "progress_percent": float(progress.progress_percent),
            "is_completed": progress.is_completed,
        }
    )


@login_required
def my_courses(request):
    """View user's enrolled courses."""
    user = request.user

    # Auto-enroll in profile courses that are missing
    if user.job_profile:
        existing_course_ids = set(
            Enrollment.objects.filter(user=user).values_list("course_id", flat=True)
        )
        courses_to_enroll = []
        for course in Course.objects.filter(status=Course.Status.PUBLISHED):
            if (
                course.target_profiles
                and user.job_profile
                and user.job_profile.code in course.target_profiles
                and course.id not in existing_course_ids
            ):
                courses_to_enroll.append(
                    Enrollment(
                        user=user,
                        course=course,
                        status=Enrollment.Status.ENROLLED,
                    )
                )
        if courses_to_enroll:
            Enrollment.objects.bulk_create(
                courses_to_enroll,
                ignore_conflicts=True,
            )

    enrollments = (
        Enrollment.objects.filter(user=user)
        .select_related("course", "course__category")
        .order_by("-updated_at")
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        enrollments = enrollments.filter(status=status_filter)

    context = {
        "enrollments": enrollments,
        "current_status": status_filter,
    }
    return render(request, "courses/my_courses.html", context)


@login_required
@require_POST
def reenable_course(request, enrollment_id):
    """Re-enable an expired course with 5 days less than original duration."""
    from datetime import date, timedelta

    from dateutil.relativedelta import relativedelta

    from apps.courses.models import CompletionRecord

    enrollment = get_object_or_404(
        Enrollment.objects.select_related("course"),
        pk=enrollment_id,
        user=request.user,
    )

    if enrollment.status != Enrollment.Status.EXPIRED:
        messages.error(request, "Solo se pueden re-habilitar cursos vencidos.")
        return redirect("courses:my_courses")

    # Save completion record before reset
    if enrollment.progress > 0:
        CompletionRecord.objects.create(
            user=request.user,
            course=enrollment.course,
            completed_at=enrollment.completed_at or enrollment.updated_at,
            progress=enrollment.progress,
            reset_reason="Re-habilitación por vencimiento",
        )

    # Calculate new due_date with 5 days penalty
    course = enrollment.course
    if course.validity_months:
        new_due_date = (
            date.today() + relativedelta(months=course.validity_months) - timedelta(days=5)
        )
    else:
        new_due_date = date.today() + timedelta(days=25)  # 30 - 5 = 25

    # Reset enrollment
    enrollment.status = Enrollment.Status.ENROLLED
    enrollment.progress = 0
    enrollment.started_at = None
    enrollment.completed_at = None
    enrollment.due_date = new_due_date
    enrollment.save()

    # Reset lesson progress
    LessonProgress.objects.filter(enrollment=enrollment).update(
        is_completed=False,
        progress_percent=0,
        time_spent=0,
        completed_at=None,
    )

    messages.success(
        request,
        f"Curso '{course.title}' habilitado de nuevo. "
        f"Nueva fecha límite: {new_due_date.strftime('%d/%m/%Y')}.",
    )
    return redirect("courses:my_courses")


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def course_create(request):
    """Create a new course (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    form = CourseCreateForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        try:
            course = form.save(commit=False)
            course.created_by = request.user
            course.save()
            messages.success(
                request, f"Curso '{course.title}' creado exitosamente. Agregue modulos y lecciones."
            )
            return redirect("courses:course_builder", course_id=course.id)
        except Exception as e:
            messages.error(request, f"Error al crear el curso: {str(e)}")

    context = {"form": form}
    return render(request, "courses/course_create.html", context)


# =============================================================================
# Category Management Views (Maestros de Categorías)
# =============================================================================


@login_required
def category_list(request):
    """List all categories (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    categories = (
        Category.objects.annotate(course_count=Count("courses"))
        .order_by("order", "name")
    )

    context = {"categories": categories}
    return render(request, "courses/category_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def category_create(request):
    """Create a new category (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    form = CategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            category = form.save()
            messages.success(request, f"Categoría '{category.name}' creada exitosamente.")

            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "courses/partials/category_row.html",
                    {"category": category},
                )
            return redirect("courses:category_list")
        except Exception as e:
            messages.error(request, f"Error al crear la categoría: {str(e)}")

    context = {"form": form, "action": "Crear"}
    return render(request, "courses/category_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def category_edit(request, category_id):
    """Edit a category (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    category = get_object_or_404(Category, id=category_id)
    form = CategoryForm(request.POST or None, instance=category)

    if request.method == "POST" and form.is_valid():
        try:
            category = form.save()
            messages.success(request, f"Categoría '{category.name}' actualizada exitosamente.")
            return redirect("courses:category_list")
        except Exception as e:
            messages.error(request, f"Error al actualizar la categoría: {str(e)}")

    context = {"form": form, "category": category, "action": "Editar"}
    return render(request, "courses/category_form.html", context)


@login_required
@require_http_methods(["POST"])
def category_delete(request, category_id):
    """Delete a category (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    category = get_object_or_404(Category, id=category_id)

    # Check if category has courses
    if category.courses.exists():
        messages.error(
            request,
            f"No se puede eliminar la categoría '{category.name}' porque tiene cursos asociados.",
        )
        return redirect("courses:category_list")

    name = category.name
    category.delete()
    messages.success(request, f"Categoría '{name}' eliminada exitosamente.")

    if request.headers.get("HX-Request"):
        return render(request, "courses/partials/category_deleted.html", {})
    return redirect("courses:category_list")


# =============================================================================
# Category Toggle Active/Inactive
# =============================================================================


@login_required
@require_http_methods(["POST"])
def category_toggle_active(request, category_id):
    """Toggle category is_active status (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    category = get_object_or_404(Category, id=category_id)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])

    action = "activada" if category.is_active else "desactivada"
    messages.success(request, f"Categoría '{category.name}' {action} exitosamente.")

    if request.headers.get("HX-Request"):
        return render(
            request,
            "courses/partials/category_status_badge.html",
            {"category": category},
        )
    return redirect("courses:category_list")


# =============================================================================
# Parametrización Hub & Course Admin Views
# =============================================================================


@login_required
def parametrizacion_hub(request):
    """Parametrizacion hub - central admin page for categories, courses and profiles."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    # Stats
    total_categories = Category.objects.count()
    active_categories = Category.objects.filter(is_active=True).count()
    inactive_categories = total_categories - active_categories
    total_courses = Course.objects.count()
    published_courses = Course.objects.filter(status=Course.Status.PUBLISHED).count()
    draft_courses = Course.objects.filter(status=Course.Status.DRAFT).count()
    archived_courses = Course.objects.filter(status=Course.Status.ARCHIVED).count()
    uncategorized_courses = Course.objects.filter(category__isnull=True).count()
    total_profiles = JobProfileType.objects.count()
    active_profiles = JobProfileType.objects.filter(is_active=True).count()

    # Data for tabs
    courses = Course.objects.select_related("category", "created_by").order_by("title")
    categories = (
        Category.objects.annotate(course_count=Count("courses"))
        .order_by("order", "name")
    )
    all_categories = Category.objects.filter(is_active=True).order_by("name")
    profiles = JobProfileType.objects.all().order_by("order", "name")

    active_tab = request.GET.get("tab", "cursos")

    context = {
        "total_categories": total_categories,
        "active_categories": active_categories,
        "inactive_categories": inactive_categories,
        "total_courses": total_courses,
        "published_courses": published_courses,
        "draft_courses": draft_courses,
        "archived_courses": archived_courses,
        "uncategorized_courses": uncategorized_courses,
        "total_profiles": total_profiles,
        "active_profiles": active_profiles,
        "courses": courses,
        "categories": categories,
        "all_categories": all_categories,
        "profiles": profiles,
        "active_tab": active_tab,
    }
    return render(request, "courses/parametrizacion_hub.html", context)


@login_required
def course_admin_list(request):
    """Admin course list for parametrización (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    courses = Course.objects.select_related("category", "created_by").order_by("title")

    # Filters
    search = request.GET.get("search")
    if search:
        courses = courses.filter(Q(title__icontains=search) | Q(code__icontains=search))

    category_filter = request.GET.get("category")
    if category_filter:
        if category_filter == "none":
            courses = courses.filter(category__isnull=True)
        else:
            courses = courses.filter(category_id=category_filter)

    status_filter = request.GET.get("status")
    if status_filter:
        courses = courses.filter(status=status_filter)

    type_filter = request.GET.get("type")
    if type_filter:
        courses = courses.filter(course_type=type_filter)

    categories = Category.objects.filter(is_active=True).order_by("name")

    context = {
        "courses": courses,
        "categories": categories,
        "search": search or "",
        "category_filter": category_filter or "",
        "status_filter": status_filter or "",
        "type_filter": type_filter or "",
    }

    if request.headers.get("HX-Request"):
        return render(request, "courses/partials/course_admin_table.html", context)

    return render(request, "courses/course_admin_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def course_edit_params(request, course_id):
    """Edit course parameters from parametrización (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta página.")
        return redirect("courses:list")

    course = get_object_or_404(Course, id=course_id)
    form = CourseEditParamsForm(request.POST or None, instance=course)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Curso '{course.title}' actualizado exitosamente.")
        return redirect("courses:course_admin_list")

    context = {"form": form, "course": course}
    return render(request, "courses/course_edit_params.html", context)


@login_required
@require_http_methods(["POST"])
def course_toggle_status(request, course_id):
    """Toggle course status (draft/published/archived) via HTMX (staff only)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "No autorizado"}, status=403)

    course = get_object_or_404(Course, id=course_id)
    new_status = request.POST.get("status")

    valid_statuses = [s.value for s in Course.Status]
    if new_status in valid_statuses:
        course.status = new_status
        if new_status == Course.Status.PUBLISHED and not course.published_at:
            from django.utils import timezone

            course.published_at = timezone.now()
        course.save(update_fields=["status", "published_at"])

    if request.headers.get("HX-Request"):
        return render(
            request,
            "courses/partials/course_status_cell.html",
            {"course": course},
        )
    return redirect("courses:course_admin_list")


# =============================================================================
# Full Course Edit & Delete (Parametrizacion)
# =============================================================================


@login_required
@require_http_methods(["GET", "POST"])
def course_full_edit(request, course_id):
    """Full course edit from Parametrizacion (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    course = get_object_or_404(Course, id=course_id)
    form = CourseFullEditForm(request.POST or None, request.FILES or None, instance=course)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Curso '{course.title}' actualizado exitosamente.")
        return redirect("courses:course_admin_list")

    # Include builder context for modules/lessons editing
    builder_ctx = _get_builder_context(course)
    context = {"form": form, "course": course, **builder_ctx}
    return render(request, "courses/course_full_edit.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def course_delete(request, course_id):
    """Delete a course with confirmation (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    course = get_object_or_404(Course, id=course_id)

    if request.method == "POST":
        active_enrollments = course.enrollments.filter(
            status__in=[Enrollment.Status.ENROLLED, Enrollment.Status.IN_PROGRESS]
        ).count()

        if active_enrollments > 0:
            messages.error(
                request,
                f"No se puede eliminar el curso '{course.title}' porque tiene "
                f"{active_enrollments} inscripciones activas.",
            )
            return redirect("courses:parametrizacion")

        title = course.title
        course.delete()
        messages.success(request, f"Curso '{title}' eliminado exitosamente.")
        return redirect("courses:parametrizacion")

    context = {
        "course": course,
        "enrollment_count": course.enrollments.count(),
        "active_enrollment_count": course.enrollments.filter(
            status__in=[Enrollment.Status.ENROLLED, Enrollment.Status.IN_PROGRESS]
        ).count(),
    }
    return render(request, "courses/course_delete_confirm.html", context)


# =============================================================================
# Job Profile Type CRUD (Parametrizacion)
# =============================================================================


@login_required
@require_http_methods(["GET", "POST"])
def profile_type_create(request):
    """Create a new job profile type (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    form = JobProfileTypeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Perfil '{form.cleaned_data['name']}' creado exitosamente.")
        return redirect("courses:parametrizacion")

    context = {"form": form, "action": "Crear"}
    return render(request, "courses/profile_type_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def profile_type_edit(request, profile_id):
    """Edit a job profile type (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    profile = get_object_or_404(JobProfileType, id=profile_id)
    form = JobProfileTypeForm(request.POST or None, instance=profile)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Perfil '{profile.name}' actualizado exitosamente.")
        return redirect("courses:parametrizacion")

    context = {"form": form, "profile": profile, "action": "Editar"}
    return render(request, "courses/profile_type_form.html", context)


@login_required
@require_http_methods(["POST"])
def profile_type_delete(request, profile_id):
    """Delete a job profile type (staff only)."""
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")

    profile = get_object_or_404(JobProfileType, id=profile_id)

    # Check if any courses use this profile
    courses_using = Course.objects.filter(target_profiles__contains=[profile.code])
    if courses_using.exists():
        messages.error(
            request,
            f"No se puede eliminar el perfil '{profile.name}' porque "
            f"{courses_using.count()} curso(s) lo utilizan.",
        )
        return redirect("courses:parametrizacion")

    name = profile.name
    profile.delete()
    messages.success(request, f"Perfil '{name}' eliminado exitosamente.")
    return redirect("courses:parametrizacion")


@login_required
@require_http_methods(["POST"])
def profile_type_toggle_active(request, profile_id):
    """Toggle profile type active status (staff only)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "No autorizado"}, status=403)

    profile = get_object_or_404(JobProfileType, id=profile_id)
    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active"])

    action = "activado" if profile.is_active else "desactivado"
    messages.success(request, f"Perfil '{profile.name}' {action} exitosamente.")

    if request.headers.get("HX-Request"):
        return render(
            request,
            "courses/partials/profile_status_badge.html",
            {"profile": profile},
        )
    return redirect("courses:parametrizacion")


# =============================================================================
# Course Builder Views
# =============================================================================


def _parse_points(raw, default="1"):
    """Parse a points value from request data into a Decimal.

    Returns a Decimal quantized to 2 decimal places. Raises InvalidOperation
    for unparseable input so callers can return a 400.
    """
    value = Decimal(str(raw if raw not in (None, "") else default))
    if value < 0:
        raise InvalidOperation("Los puntos no pueden ser negativos")
    return value.quantize(Decimal("0.01"))


def _staff_required(request):
    """Check if user is staff, return error response or None."""
    if not request.user.is_staff:
        if request.headers.get("HX-Request"):
            return JsonResponse({"error": "No autorizado"}, status=403)
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")
    return None


def _get_available_assessments(course):
    """Get assessments available for assignment in this course."""
    from apps.assessments.models import Assessment

    return Assessment.objects.filter(
        Q(course=course) | Q(course__isnull=True, lesson__isnull=True)
    ).order_by("title")


def _get_builder_context(course):
    """Get common context for builder templates."""
    modules = course.modules.prefetch_related("lessons__assessments").order_by("order")
    available_assessments = _get_available_assessments(course)

    return {
        "course": course,
        "modules": modules,
        "module_form": ModuleBuilderForm(),
        "lesson_form": LessonBuilderForm(),
        "quiz_form": QuickAssessmentForm(),
        "available_assessments": available_assessments,
    }


@login_required
@require_http_methods(["GET"])
def course_builder(request, course_id):
    """Main course builder page."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    context = _get_builder_context(course)
    return render(request, "courses/course_builder.html", context)


@login_required
@require_http_methods(["POST"])
def builder_update_course_info(request, course_id):
    """Update course basic info from builder."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    form = CourseEditParamsForm(request.POST, instance=course)

    if form.is_valid():
        form.save()

    context = _get_builder_context(course)
    if request.headers.get("HX-Request"):
        return render(request, "courses/partials/builder/course_info_card.html", context)
    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["POST"])
def builder_add_module(request, course_id):
    """Add a new module to the course."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    form = ModuleBuilderForm(request.POST, request.FILES)

    if form.is_valid():
        with transaction.atomic():
            locked_course = Course.objects.select_for_update().get(id=course.id)
            module = form.save(commit=False)
            module.course = locked_course
            max_order = locked_course.modules.aggregate(max_order=models.Max("order"))["max_order"]
            module.order = max_order + 1 if max_order is not None else 0
            module.save()

        if request.headers.get("HX-Request"):
            return render(
                request,
                "courses/partials/builder/module_card.html",
                {
                    "module": module,
                    "course": course,
                    "lesson_form": LessonBuilderForm(),
                    "available_assessments": _get_available_assessments(course),
                },
            )

    context = _get_builder_context(course)
    return render(request, "courses/course_builder.html", context)


@login_required
@require_http_methods(["POST"])
def builder_edit_module(request, course_id, module_id):
    """Edit an existing module."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    form = ModuleBuilderForm(request.POST, request.FILES, instance=module)

    if form.is_valid():
        form.save()

    if request.headers.get("HX-Request"):
        module.refresh_from_db()
        return render(
            request,
            "courses/partials/builder/module_card.html",
            {
                "module": module,
                "course": course,
                "lesson_form": LessonBuilderForm(),
                "available_assessments": _get_available_assessments(course),
            },
        )

    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["POST"])
def builder_delete_module(request, course_id, module_id):
    """Delete a module and its lessons."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    module.delete()

    if request.headers.get("HX-Request"):
        return HttpResponse("")

    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["POST"])
def builder_reorder_modules(request, course_id):
    """Reorder modules via drag & drop."""
    import json

    from django.db import transaction

    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)

    try:
        data = json.loads(request.body)
        module_ids = data.get("order", [])
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Datos invalidos"}, status=400)

    with transaction.atomic():
        # Step 1: Set all to negative to avoid unique_together violation
        for i, mid in enumerate(module_ids):
            Module.objects.filter(id=mid, course=course).update(order=-(i + 1))
        # Step 2: Set final order
        for i, mid in enumerate(module_ids):
            Module.objects.filter(id=mid, course=course).update(order=i)

    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["POST"])
def builder_add_lesson(request, course_id, module_id):
    """Add a lesson to a module."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    form = LessonBuilderForm(request.POST, request.FILES)

    if form.is_valid():
        try:
            lesson = form.save(commit=False)
            lesson.module = module
            max_order = module.lessons.aggregate(max_order=models.Max("order"))["max_order"]
            lesson.order = max_order + 1 if max_order is not None else 0
            lesson.save()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Error saving lesson")
            form.add_error(None, f"Error al guardar la leccion: {e}")
        else:
            # Auto-create assessment + questions for quiz-type lessons
            if lesson.lesson_type == "quiz":
                from apps.assessments.models import Answer, Assessment, Question

                try:
                    assessment = Assessment.objects.create(
                        title=lesson.title,
                        assessment_type="quiz",
                        passing_score=80,
                        max_attempts=3,
                        course=course,
                        lesson=lesson,
                        created_by=request.user,
                        status="published",
                    )

                    # Parse inline quiz questions from JSON
                    import json

                    quiz_questions_json = request.POST.get("quiz_questions", "[]")
                    try:
                        quiz_questions = json.loads(quiz_questions_json)
                    except (json.JSONDecodeError, TypeError):
                        quiz_questions = []

                    for i, qdata in enumerate(quiz_questions):
                        try:
                            q_points = _parse_points(qdata.get("points", "1"))
                        except InvalidOperation:
                            q_points = Decimal("1.00")
                        question = Question.objects.create(
                            assessment=assessment,
                            question_type=qdata.get("type", "single_choice"),
                            text=qdata.get("text", ""),
                            explanation=qdata.get("explanation", ""),
                            points=q_points,
                            order=i,
                        )
                        q_type = qdata.get("type", "single_choice")
                        if q_type in ("single_choice", "multiple_choice"):
                            for j, adata in enumerate(qdata.get("answers", [])):
                                Answer.objects.create(
                                    question=question,
                                    text=adata.get("text", ""),
                                    is_correct=adata.get("is_correct", False),
                                    order=j,
                                )
                        elif q_type == "true_false":
                            is_true = qdata.get("trueFalseCorrect", "true") == "true"
                            Answer.objects.create(
                                question=question, text="Verdadero", is_correct=is_true, order=0
                            )
                            Answer.objects.create(
                                question=question, text="Falso", is_correct=not is_true, order=1
                            )
                        elif q_type == "matching":
                            for j, pair in enumerate(qdata.get("matchPairs", [])):
                                Answer.objects.create(
                                    question=question,
                                    text=pair.get("left", ""),
                                    feedback=pair.get("right", ""),
                                    is_correct=True,
                                    order=j,
                                )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.exception("Error creating assessment for quiz lesson")
                    messages.error(request, f"Error al crear el quiz: {e}")

            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "courses/partials/builder/lesson_item.html",
                    {
                        "lesson": lesson,
                        "course": course,
                        "module": module,
                        "available_assessments": _get_available_assessments(course),
                    },
                )

    # Form invalid or save error — return form with errors
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "courses/partials/builder/lesson_form.html",
            {"lesson_form": form, "course": course, "module": module, "is_new": True},
        )
        response["HX-Retarget"] = "closest form"
        response["HX-Reswap"] = "outerHTML"
        return response

    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["GET", "POST"])
def builder_edit_lesson(request, course_id, module_id, lesson_id):
    """Edit a lesson."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)

    if request.method == "POST":
        form = LessonBuilderForm(request.POST, request.FILES, instance=lesson)

        if form.is_valid():
            try:
                form.save()

                # Handle quiz time_limit if present
                if lesson.lesson_type == "quiz":
                    quiz_time_limit = request.POST.get("quiz_time_limit", "").strip()
                    assessment = lesson.assessments.first()

                    import logging

                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"Quiz edit - lesson_id={lesson.id}, quiz_time_limit='{quiz_time_limit}', has_assessment={assessment is not None}"
                    )

                    # If quiz lesson has no assessment, create one
                    if not assessment:
                        from apps.assessments.models import Assessment

                        try:
                            assessment = Assessment.objects.create(
                                title=lesson.title,
                                assessment_type="quiz",
                                passing_score=80,
                                max_attempts=3,
                                course=course,
                                lesson=lesson,
                                created_by=request.user,
                                status="published",
                            )
                            logger.info(
                                f"Created assessment {assessment.id} for quiz lesson {lesson.id}"
                            )
                            messages.info(request, "Quiz creado automáticamente.")
                        except Exception as e:
                            logger.exception("Error creating assessment for quiz lesson")
                            messages.error(request, f"Error al crear el quiz: {e}")

                    if assessment:
                        if quiz_time_limit:
                            try:
                                time_limit_int = int(quiz_time_limit)
                                logger.info(
                                    f"Saving time_limit={time_limit_int} to assessment {assessment.id}"
                                )
                                assessment.time_limit = time_limit_int
                                assessment.save(update_fields=["time_limit"])
                                logger.info(f"Saved successfully")
                            except (ValueError, TypeError) as ve:
                                logger.warning(f"Failed to parse time_limit: {ve}")
                        # Refresh to ensure latest value is displayed
                        assessment.refresh_from_db()
                        logger.info(
                            f"Assessment refreshed - current time_limit={assessment.time_limit}"
                        )

                messages.success(request, "Lección actualizada correctamente.")

                if request.headers.get("HX-Request"):
                    lesson.refresh_from_db()
                    return render(
                        request,
                        "courses/partials/builder/lesson_item.html",
                        {
                            "lesson": lesson,
                            "course": course,
                            "module": module,
                            "available_assessments": _get_available_assessments(course),
                        },
                    )
                return redirect("courses:course_builder", course_id=course.id)
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.exception("Error saving lesson")
                form.add_error(None, f"Error al guardar la leccion: {e}")
                messages.error(request, f"Error al guardar: {e}")

        if form.errors and request.headers.get("HX-Request"):
            lesson.refresh_from_db()
            response = render(
                request,
                "courses/partials/builder/lesson_item.html",
                {
                    "lesson_form": form,
                    "lesson": lesson,
                    "course": course,
                    "module": module,
                    "available_assessments": _get_available_assessments(course),
                },
            )
            return response

    else:
        form = LessonBuilderForm(instance=lesson)

    context = {
        "lesson_form": form,
        "course": course,
        "module": module,
        "lesson": lesson,
        "is_new": False,
    }
    return render(request, "courses/partials/builder/lesson_form.html", context)


@login_required
@require_http_methods(["POST"])
def builder_update_quiz_time_limit(request, course_id, assessment_id):
    """Update quiz time limit."""
    from apps.assessments.models import Assessment
    from django.urls import reverse

    if err := _staff_required(request):
        return err

    assessment = get_object_or_404(Assessment, id=assessment_id)
    time_limit = request.POST.get("time_limit", "").strip()

    if not time_limit:
        # Clear time limit
        assessment.time_limit = None
        assessment.save(update_fields=["time_limit"])
    else:
        try:
            assessment.time_limit = int(time_limit)
            assessment.save(update_fields=["time_limit"])
        except (ValueError, TypeError):
            return HttpResponse(
                '<div class="alert alert-error">Ingresa un número válido</div>',
                status=400,
            )

    update_url = reverse(
        "courses:builder_update_quiz_time_limit",
        kwargs={"course_id": course_id, "assessment_id": assessment_id},
    )
    lesson_id = assessment.lesson.id
    current_value = assessment.time_limit or ""

    html = f"""
    <div class="form-control mt-2">
        <label class="label py-1">
            <span class="label-text text-xs">Límite de tiempo (minutos)</span>
        </label>
        <div class="flex gap-2">
            <input type="number" id="quiz_time_limit_{lesson_id}" value="{current_value}"
                   class="input input-bordered input-sm flex-1" min="0"
                   placeholder="Sin límite si está vacío">
            <button type="button" class="btn btn-sm btn-ghost"
                    onclick="this.setAttribute('hx-vals', JSON.stringify({{time_limit: document.getElementById('quiz_time_limit_{lesson_id}').value}}))"
                    hx-post="{update_url}" hx-target="closest .form-control" hx-swap="outerHTML">
                Guardar tiempo
            </button>
        </div>
        <span class="text-sm text-success">✓ Guardado</span>
    </div>
    """
    return HttpResponse(html.strip(), status=200)


@login_required
@require_http_methods(["POST"])
def builder_delete_lesson(request, course_id, module_id, lesson_id):
    """Delete a lesson."""
    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)
    lesson.delete()

    if request.headers.get("HX-Request"):
        return HttpResponse("")

    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["POST"])
def builder_reorder_lessons(request, course_id, module_id):
    """Reorder lessons within a module."""
    import json

    if err := _staff_required(request):
        return err

    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)

    try:
        data = json.loads(request.body)
        lesson_ids = data.get("order", [])
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Datos invalidos"}, status=400)

    for i, lid in enumerate(lesson_ids):
        Lesson.objects.filter(id=lid, module=module).update(order=i)

    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["POST"])
def builder_create_quiz(request, course_id):
    """Create a new assessment from the builder."""
    if err := _staff_required(request):
        return err

    from apps.assessments.models import Assessment

    course = get_object_or_404(Course, id=course_id)
    form = QuickAssessmentForm(request.POST)

    if form.is_valid():
        assessment = Assessment.objects.create(
            title=form.cleaned_data["title"],
            assessment_type=form.cleaned_data["assessment_type"],
            passing_score=form.cleaned_data["passing_score"],
            time_limit=form.cleaned_data.get("time_limit"),
            max_attempts=form.cleaned_data["max_attempts"],
            course=course,
            created_by=request.user,
            status="draft",
        )

        if request.headers.get("HX-Request"):
            return render(
                request,
                "courses/partials/builder/quiz_selector.html",
                {
                    "course": course,
                    "available_assessments": _get_available_assessments(course),
                    "new_assessment": assessment,
                },
            )

    return redirect("courses:course_builder", course_id=course.id)


@login_required
@require_http_methods(["GET", "POST"])
def builder_edit_assessment(request, course_id, assessment_id):
    """Edit Assessment properties from the course builder.

    GET  -> renders the inline edit form partial.
    POST -> validates + persists changes atomically and returns refreshed editor partial.
    Permission: staff OR Assessment.created_by == request.user.
    """
    from apps.assessments.models import Assessment

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)

    # Permission: staff OR creator
    if not (request.user.is_staff or assessment.created_by_id == request.user.id):
        if request.headers.get("HX-Request"):
            return JsonResponse({"error": "No autorizado"}, status=403)
        messages.error(request, "No tiene permisos para editar esta evaluacion.")
        return redirect("courses:course_builder", course_id=course.id)

    if request.method == "GET":
        form = AssessmentEditForm(instance=assessment)
        return render(
            request,
            "courses/partials/builder/assessment_properties_form.html",
            {"course": course, "assessment": assessment, "form": form},
        )

    # POST
    form = AssessmentEditForm(request.POST, instance=assessment)
    if not form.is_valid():
        return render(
            request,
            "courses/partials/builder/assessment_properties_form.html",
            {"course": course, "assessment": assessment, "form": form},
            status=400,
        )

    with transaction.atomic():
        form.save()

    assessment.refresh_from_db()
    questions = assessment.questions.prefetch_related("answers").order_by("order")
    response = render(
        request,
        "courses/partials/builder/assessment_editor.html",
        {
            "course": course,
            "assessment": assessment,
            "questions": questions,
            "saved": True,
        },
    )
    response["HX-Trigger"] = "assessment-updated"
    return response


# =============================================================================
# Assessment Question Editor Views (Builder)
# =============================================================================


@login_required
@require_http_methods(["GET"])
def builder_assessment_editor(request, course_id, assessment_id):
    """Return the assessment question editor partial."""
    if err := _staff_required(request):
        return err

    from apps.assessments.models import Assessment

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)
    questions = assessment.questions.prefetch_related("answers").order_by("order")

    context = {
        "course": course,
        "assessment": assessment,
        "questions": questions,
    }
    return render(request, "courses/partials/builder/assessment_editor.html", context)


@login_required
@require_http_methods(["POST"])
def builder_add_question(request, course_id, assessment_id):
    """Add a question to an assessment from the builder."""
    if err := _staff_required(request):
        return err

    from apps.assessments.models import Answer, Assessment, Question

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)

    question_type = request.POST.get("question_type", "single_choice")
    text = request.POST.get("text", "").strip()
    explanation = request.POST.get("explanation", "").strip()
    try:
        points = _parse_points(request.POST.get("points", "1"))
    except InvalidOperation:
        return JsonResponse({"error": "Puntos inválido"}, status=400)

    if not text:
        return JsonResponse({"error": "La pregunta es requerida"}, status=400)

    max_order = assessment.questions.aggregate(max_order=models.Max("order"))["max_order"]
    question = Question.objects.create(
        assessment=assessment,
        question_type=question_type,
        text=text,
        explanation=explanation,
        points=points,
        order=max_order + 1 if max_order is not None else 0,
    )

    # Create answers based on question type
    if question_type in ("single_choice", "multiple_choice"):
        answer_texts = request.POST.getlist("answer_text")
        correct_answers = request.POST.getlist("correct_answer")
        for i, a_text in enumerate(answer_texts):
            a_text = a_text.strip()
            if a_text:
                Answer.objects.create(
                    question=question,
                    text=a_text,
                    is_correct=str(i) in correct_answers,
                    order=i,
                )

    elif question_type == "true_false":
        correct = request.POST.get("correct_answer", "true")
        Answer.objects.create(
            question=question, text="Verdadero", is_correct=(correct == "true"), order=0
        )
        Answer.objects.create(
            question=question, text="Falso", is_correct=(correct == "false"), order=1
        )

    elif question_type == "matching":
        left_items = request.POST.getlist("match_left")
        right_items = request.POST.getlist("match_right")
        pairs = []
        for i, (left, right) in enumerate(zip(left_items, right_items)):
            left, right = left.strip(), right.strip()
            if left and right:
                pairs.append({"left": left, "right": right})
                Answer.objects.create(question=question, text=left, feedback=right, order=i)
        question.metadata = {"match_pairs": pairs}
        question.save(update_fields=["metadata"])

    if request.headers.get("HX-Request"):
        question = Question.objects.prefetch_related("answers").get(id=question.id)
        return render(
            request,
            "courses/partials/builder/question_item.html",
            {"question": question, "course": course, "assessment": assessment},
        )

    return redirect("courses:course_builder", course_id=course_id)


@login_required
@require_http_methods(["POST"])
def builder_edit_question(request, course_id, assessment_id, question_id):
    """Edit a question in an assessment."""
    if err := _staff_required(request):
        return err

    from apps.assessments.models import Answer, Assessment, Question

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)
    question = get_object_or_404(Question, id=question_id, assessment=assessment)

    question_type = request.POST.get("question_type", question.question_type)
    text = request.POST.get("text", "").strip()
    explanation = request.POST.get("explanation", "").strip()
    try:
        points = _parse_points(request.POST.get("points", "1"))
    except InvalidOperation:
        return JsonResponse({"error": "Puntos inválido"}, status=400)

    if not text:
        return JsonResponse({"error": "La pregunta es requerida"}, status=400)

    question.question_type = question_type
    question.text = text
    question.explanation = explanation
    question.points = points
    question.save(update_fields=["question_type", "text", "explanation", "points"])

    # Re-create answers
    question.answers.all().delete()

    if question_type in ("single_choice", "multiple_choice"):
        answer_texts = request.POST.getlist("answer_text")
        correct_answers = request.POST.getlist("correct_answer")
        for i, a_text in enumerate(answer_texts):
            a_text = a_text.strip()
            if a_text:
                Answer.objects.create(
                    question=question,
                    text=a_text,
                    is_correct=str(i) in correct_answers,
                    order=i,
                )

    elif question_type == "true_false":
        correct = request.POST.get("correct_answer", "true")
        Answer.objects.create(
            question=question, text="Verdadero", is_correct=(correct == "true"), order=0
        )
        Answer.objects.create(
            question=question, text="Falso", is_correct=(correct == "false"), order=1
        )

    elif question_type == "matching":
        left_items = request.POST.getlist("match_left")
        right_items = request.POST.getlist("match_right")
        pairs = []
        for i, (left, right) in enumerate(zip(left_items, right_items)):
            left, right = left.strip(), right.strip()
            if left and right:
                pairs.append({"left": left, "right": right})
                Answer.objects.create(question=question, text=left, feedback=right, order=i)
        question.metadata = {"match_pairs": pairs}
        question.save(update_fields=["metadata"])

    if request.headers.get("HX-Request"):
        question = Question.objects.prefetch_related("answers").get(id=question.id)
        return render(
            request,
            "courses/partials/builder/question_item.html",
            {"question": question, "course": course, "assessment": assessment},
        )

    return redirect("courses:course_builder", course_id=course_id)


@login_required
@require_http_methods(["POST"])
def builder_delete_question(request, course_id, assessment_id, question_id):
    """Delete a question from an assessment."""
    if err := _staff_required(request):
        return err

    from apps.assessments.models import Assessment, Question

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)
    question = get_object_or_404(Question, id=question_id, assessment=assessment)
    question.delete()

    if request.headers.get("HX-Request"):
        return HttpResponse("")

    return redirect("courses:course_builder", course_id=course_id)


@login_required
@require_http_methods(["POST"])
def builder_reorder_questions(request, course_id, assessment_id):
    """Reorder questions within an assessment."""
    import json as json_module

    if err := _staff_required(request):
        return err

    from apps.assessments.models import Assessment, Question

    course = get_object_or_404(Course, id=course_id)
    assessment = get_object_or_404(Assessment, id=assessment_id, course=course)

    try:
        data = json_module.loads(request.body)
        question_ids = data.get("order", [])
    except (json_module.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Datos invalidos"}, status=400)

    for i, qid in enumerate(question_ids):
        Question.objects.filter(id=qid, assessment=assessment).update(order=i)

    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["POST"])
def sign_lesson_evidence(request, course_id, lesson_id):
    """Record a signature for a presential lesson."""
    import base64
    from django.core.files.base import ContentFile
    from django.utils import timezone

    lesson = get_object_or_404(Lesson, id=lesson_id, module__course_id=course_id)
    signature_data = request.POST.get("signature")
    if not signature_data:
        return JsonResponse({"error": "Firma requerida"}, status=400)

    try:
        format_part, imgstr = signature_data.split(";base64,")
        img_file = ContentFile(
            base64.b64decode(imgstr), name=f"sig_{request.user.id}_{lesson_id}.png"
        )
    except (ValueError, IndexError):
        return JsonResponse({"error": "Formato de firma inválido"}, status=400)

    evidence, _ = LessonEvidence.objects.get_or_create(
        lesson=lesson,
        user=request.user,
        defaults={"evidence_type": LessonEvidence.EvidenceType.ATTENDANCE, "file": img_file},
    )
    evidence.signature = img_file
    evidence.signed_at = timezone.now()
    evidence.save()

    enrollment = get_object_or_404(Enrollment, user=request.user, course_id=course_id)
    progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
    progress.is_completed = True
    progress.progress_percent = 100
    progress.completed_at = timezone.now()
    progress.save()

    total = enrollment.course.get_total_lessons()
    completed = enrollment.lesson_progress.filter(is_completed=True).count()
    new_progress = (completed / total * 100) if total > 0 else 0
    enrollment.progress = new_progress

    if new_progress >= 100:
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.completed_at = timezone.now()
    elif enrollment.status == Enrollment.Status.ENROLLED:
        enrollment.status = Enrollment.Status.IN_PROGRESS
        enrollment.started_at = enrollment.started_at or timezone.now()

    enrollment.save()

    if request.headers.get("HX-Request"):
        return JsonResponse(
            {
                "success": True,
                "progress": float(new_progress),
                "status": enrollment.status,
                "show_completion_modal": new_progress >= 100,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "progress": float(new_progress),
            "status": enrollment.status,
            "show_completion_modal": new_progress >= 100,
        }
    )


@login_required
@require_http_methods(["POST"])
def sign_course_completion(request, course_id):
    """Record user signature upon course completion."""
    import base64
    from django.core.files.base import ContentFile
    from django.utils import timezone

    enrollment = get_object_or_404(Enrollment, user=request.user, course_id=course_id)
    signature_data = request.POST.get("signature")
    if not signature_data:
        return JsonResponse({"error": "Firma requerida"}, status=400)

    try:
        format_part, imgstr = signature_data.split(";base64,")
        img_file = ContentFile(
            base64.b64decode(imgstr), name=f"sig_completion_{request.user.id}_{course_id}.png"
        )
    except (ValueError, IndexError):
        return JsonResponse({"error": "Formato de firma inválido"}, status=400)

    enrollment.completion_signature = img_file
    enrollment.completion_signed_at = timezone.now()
    enrollment.save()

    if request.headers.get("HX-Request"):
        return JsonResponse({"success": True, "signed_at": str(enrollment.completion_signed_at)})

    return JsonResponse({"success": True, "signed_at": str(enrollment.completion_signed_at)})


@login_required
def attendance_lesson_view(request, course_id, lesson_id):
    """View for attendance lesson with signature capture."""
    course = get_object_or_404(Course, pk=course_id)
    lesson = get_object_or_404(
        Lesson,
        pk=lesson_id,
        module__course=course,
        lesson_type=Lesson.Type.ATTENDANCE,
    )

    enrollment = get_object_or_404(Enrollment, course=course, user=request.user)

    existing_signature = AttendanceSignature.objects.filter(
        lesson=lesson,
        user=request.user,
    ).first()

    is_instructor = lesson.metadata.get("instructor_id") == request.user.id

    context = {
        "course": course,
        "lesson": lesson,
        "enrollment": enrollment,
        "existing_signature": existing_signature,
        "is_instructor": is_instructor,
        "form": AttendanceSignatureForm(),
    }

    # Admin attendance summary (SD#40): staff see the per-session roster with
    # derived Presente/Ausente status, totals and attendance percentage.
    if request.user.is_staff:
        summary = _build_attendance_summary(course, lesson)
        context.update(
            {
                "attendance_summary": summary["rows"],
                "total_inscritos": summary["total_inscritos"],
                "total_presentes": summary["total_presentes"],
                "total_ausentes": summary["total_ausentes"],
                "porcentaje_asistencia": summary["porcentaje_asistencia"],
            }
        )

    return render(request, "courses/attendance_lesson.html", context)


@login_required
@require_http_methods(["POST"])
def save_attendance_signature(request, course_id, lesson_id):
    """Save attendance signature."""
    course = get_object_or_404(Course, pk=course_id)
    lesson = get_object_or_404(
        Lesson,
        pk=lesson_id,
        module__course=course,
        lesson_type=Lesson.Type.ATTENDANCE,
    )

    enrollment = get_object_or_404(Enrollment, course=course, user=request.user)

    signature_data = request.POST.get("signature_data")
    if not signature_data:
        return JsonResponse({"error": "No signature data provided"}, status=400)

    is_instructor = lesson.metadata.get("instructor_id") == request.user.id
    signature_type = (
        AttendanceSignature.SignatureType.INSTRUCTOR
        if is_instructor
        else AttendanceSignature.SignatureType.STUDENT
    )

    try:
        header, image_data = signature_data.split(",")
        image_bytes = base64.b64decode(image_data)

        signature_obj, created = AttendanceSignature.objects.get_or_create(
            lesson=lesson,
            user=request.user,
            defaults={
                "signature_type": signature_type,
                "instructor_id": lesson.metadata.get("instructor_id"),
                "ip_address": get_client_ip(request),
            },
        )

        if not created:
            return JsonResponse(
                {
                    "error": "Ya has registrado tu firma en esta lección. Si deseas reemplazarla, por favor contacta al instructor.",
                    "already_signed": True,
                    "signed_at": str(signature_obj.signed_at),
                },
                status=400,
            )

        filename = f"signature_{lesson.id}_{request.user.id}_{timezone.now().timestamp()}.png"
        signature_obj.signature_image.save(
            filename,
            ContentFile(image_bytes),
            save=True,
        )

        LessonProgress.objects.get_or_create(
            lesson=lesson,
            enrollment=enrollment,
            defaults={"is_completed": True, "completed_at": timezone.now()},
        )

        messages.success(request, "Firma registrada correctamente.")
        return JsonResponse(
            {
                "success": True,
                "message": "Firma guardada correctamente",
                "signed_at": str(signature_obj.signed_at),
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def _build_attendance_summary(course, lesson):
    """Build the attendance summary for an attendance lesson.

    Returns a dict with:
      - rows: list of per-enrollee dicts {user, full_name, document_number,
        estado ("Presente"/"Ausente"), presente (bool), signed_at,
        signature_image_url}
      - total_inscritos, total_presentes, total_ausentes
      - porcentaje_asistencia: presentes / inscritos * 100, rounded to 1
        decimal (0 if there are no enrollees -> no ZeroDivisionError)

    Shared by ``attendance_lesson_view`` (admin summary, SD#40) and
    ``export_attendance_pdf`` (SD#33) so both surfaces stay consistent.
    The "Presente"/"Ausente" status is derived: an enrollee with an
    ``AttendanceSignature`` for this lesson is Presente, otherwise Ausente.
    """
    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__document_number")
    )

    signatures = AttendanceSignature.objects.filter(lesson=lesson).select_related("user")
    signatures_by_user = {sig.user_id: sig for sig in signatures}

    rows = []
    total_presentes = 0
    for enrollment in enrollments:
        user = enrollment.user
        sig = signatures_by_user.get(user.id)
        presente = sig is not None
        if presente:
            total_presentes += 1
        signature_image_url = ""
        if sig and sig.signature_image:
            try:
                signature_image_url = sig.signature_image.url
            except Exception:
                signature_image_url = ""
        rows.append(
            {
                "user": user,
                "full_name": user.get_full_name() or user.document_number,
                "document_number": user.document_number,
                "presente": presente,
                "estado": "Presente" if presente else "Ausente",
                "signed_at": sig.signed_at if sig else None,
                "signature_image_url": signature_image_url,
            }
        )

    total_inscritos = len(rows)
    total_ausentes = total_inscritos - total_presentes
    if total_inscritos:
        porcentaje_asistencia = round(total_presentes / total_inscritos * 100, 1)
    else:
        porcentaje_asistencia = 0.0

    return {
        "rows": rows,
        "total_inscritos": total_inscritos,
        "total_presentes": total_presentes,
        "total_ausentes": total_ausentes,
        "porcentaje_asistencia": porcentaje_asistencia,
    }


@login_required
def export_attendance_pdf(request, course_id, lesson_id):
    """Export the attendance list of an attendance lesson as PDF (staff only).

    Includes, per enrollee: full name, document number (cédula), status
    (Presente/Ausente), signature timestamp and the signature image, plus
    totals and the attendance percentage for the session (SD#33 + SD#40).
    """
    if err := _staff_required(request):
        return err

    from io import BytesIO

    from django.template.loader import render_to_string
    from xhtml2pdf import pisa

    course = get_object_or_404(Course, pk=course_id)
    lesson = get_object_or_404(
        Lesson,
        pk=lesson_id,
        module__course=course,
        lesson_type=Lesson.Type.ATTENDANCE,
    )

    summary = _build_attendance_summary(course, lesson)

    context = {
        "course": course,
        "lesson": lesson,
        "rows": summary["rows"],
        "total_inscritos": summary["total_inscritos"],
        "total_presentes": summary["total_presentes"],
        "total_ausentes": summary["total_ausentes"],
        "porcentaje_asistencia": summary["porcentaje_asistencia"],
        "generated_at": timezone.now(),
        "request_user": request.user,
    }

    html_string = render_to_string("courses/attendance_pdf.html", context)

    result = BytesIO()
    pdf = pisa.CreatePDF(html_string, dest=result, encoding="utf-8")

    if pdf.err:
        messages.error(request, "Error al generar el PDF de asistencia.")
        return redirect("courses:attendance_lesson", course_id=course.id, lesson_id=lesson.id)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    filename = f"asistencia_{lesson.id}_{timezone.now().strftime('%Y%m%d')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
