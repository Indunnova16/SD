"""
Web views for learning paths app.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import Rol, require_rol, user_has_rol
from apps.courses.models import Enrollment

from .forms import LearningPathCreateForm
from .models import LearningPath, PathAssignment


def _target_profiles_contains(field_prefix, profile_code):
    """Q object para `<field_prefix>__contains=[profile_code]`, con fallback
    SQLite (issue #58, sub-item A6) — ver docstring gemelo en
    `apps.courses.views._target_profiles_contains`. El lookup `contains` de
    `JSONField` no esta soportado en SQLite (`config/settings/test.py`)."""
    db_engine = settings.DATABASES["default"]["ENGINE"]
    if "postgresql" in db_engine:
        return Q(**{f"{field_prefix}__contains": [profile_code]})
    return Q(**{f"{field_prefix}__icontains": profile_code})


@login_required
def learning_path_list(request):
    """List all active learning paths."""
    paths = LearningPath.objects.filter(status=LearningPath.Status.ACTIVE).prefetch_related(
        "path_courses", "path_courses__course"
    )

    # RBAC — filtrado por rol (issue #58, sub-item A6): Ejecutor (o rol sin
    # asignar) ve solo el subconjunto de rutas dirigidas a su `job_profile`
    # (via `target_profiles`), + rutas sin perfil objetivo (genéricas,
    # visibles a todos). Coordinador/Administrador ven todas las rutas.
    if not user_has_rol(request.user, Rol.COORDINADOR, Rol.ADMINISTRADOR):
        profile_code = request.user.job_profile.code if request.user.job_profile else None
        if profile_code:
            paths = paths.filter(
                Q(target_profiles=[]) | _target_profiles_contains("target_profiles", profile_code)
            )
        else:
            paths = paths.filter(target_profiles=[])

    # Filter by profile
    profile = request.GET.get("profile")
    if profile:
        paths = paths.filter(target_profiles__contains=[profile])

    # Filter mandatory only
    mandatory = request.GET.get("mandatory")
    if mandatory:
        paths = paths.filter(is_mandatory=True)

    # Search
    search = request.GET.get("search")
    if search:
        paths = paths.filter(Q(name__icontains=search) | Q(description__icontains=search))

    # Get user's assignments
    user_assignments = {
        a.learning_path_id: a for a in PathAssignment.objects.filter(user=request.user)
    }

    # Add progress info to paths
    paths_with_progress = []
    for path in paths:
        assignment = user_assignments.get(path.id)
        paths_with_progress.append(
            {
                "path": path,
                "assignment": assignment,
                "progress": float(assignment.progress) if assignment else None,
            }
        )

    context = {
        "paths": paths_with_progress,
        "current_profile": profile,
        "mandatory_only": mandatory,
        "search_query": search,
    }
    return render(request, "learning_paths/path_list.html", context)


@login_required
def learning_path_detail(request, path_id):
    """View learning path details."""
    path = get_object_or_404(
        LearningPath.objects.prefetch_related(
            "path_courses", "path_courses__course", "path_courses__unlock_after"
        ),
        id=path_id,
    )

    # Get user's assignment
    assignment = PathAssignment.objects.filter(
        user=request.user,
        learning_path=path,
    ).first()

    # Get course completion status
    courses_status = []
    user_enrollments = {e.course_id: e for e in Enrollment.objects.filter(user=request.user)}

    for path_course in path.path_courses.all():
        enrollment = user_enrollments.get(path_course.course.id)
        is_unlocked = True

        # Check if prerequisite is completed
        if path_course.unlock_after:
            prereq_enrollment = user_enrollments.get(path_course.unlock_after.course.id)
            is_unlocked = (
                prereq_enrollment and prereq_enrollment.status == Enrollment.Status.COMPLETED
            )

        courses_status.append(
            {
                "path_course": path_course,
                "enrollment": enrollment,
                "is_unlocked": is_unlocked,
                "is_completed": (enrollment and enrollment.status == Enrollment.Status.COMPLETED),
            }
        )

    context = {
        "path": path,
        "assignment": assignment,
        "courses_status": courses_status,
    }
    return render(request, "learning_paths/path_detail.html", context)


@login_required
@require_http_methods(["POST"])
def join_learning_path(request, path_id):
    """Join a learning path."""
    path = get_object_or_404(
        LearningPath,
        id=path_id,
        status=LearningPath.Status.ACTIVE,
    )

    assignment, created = PathAssignment.objects.get_or_create(
        user=request.user,
        learning_path=path,
        defaults={"assigned_by": request.user},
    )

    if created:
        # Auto-enroll in all courses
        path_courses = path.path_courses.select_related("course")
        course_ids = [pc.course_id for pc in path_courses]

        # Get existing enrollments
        existing = set(
            Enrollment.objects.filter(user=request.user, course_id__in=course_ids).values_list(
                "course_id", flat=True
            )
        )

        # Create missing enrollments in bulk
        to_create = [
            Enrollment(
                user=request.user,
                course=path_course.course,
                assigned_by=request.user,
            )
            for path_course in path_courses
            if path_course.course_id not in existing
        ]

        if to_create:
            Enrollment.objects.bulk_create(to_create, ignore_conflicts=True)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "learning_paths/partials/assignment_status.html",
            {"path": path, "assignment": assignment},
        )

    return redirect("learning_paths:detail", path_id=path_id)


@login_required
def my_learning_paths(request):
    """View user's learning path assignments."""
    assignments = (
        PathAssignment.objects.filter(user=request.user)
        .select_related("learning_path")
        .prefetch_related(
            "learning_path__path_courses",
            "learning_path__path_courses__course",
        )
        .order_by("-updated_at")
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        assignments = assignments.filter(status=status_filter)

    context = {
        "assignments": assignments,
        "current_status": status_filter,
    }
    return render(request, "learning_paths/my_paths.html", context)


@login_required
@require_http_methods(["GET", "POST"])
@require_rol(Rol.ADMINISTRADOR, redirect_url="learning_paths:list")
def learning_path_create(request):
    """Create a new learning path (Administrador only)."""
    form = LearningPathCreateForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        path = form.save(commit=False)
        path.created_by = request.user
        path.save()
        messages.success(request, f"Ruta '{path.name}' creada exitosamente.")
        return redirect("learning_paths:detail", path_id=path.id)

    context = {"form": form}
    return render(request, "learning_paths/path_create.html", context)
