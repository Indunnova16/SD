"""
Dashboard views for SD LMS.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.models import User
from apps.accounts.permissions import Rol, require_rol
from apps.certifications.models import Certificate
from apps.courses.models import Category, Course, Enrollment
from apps.learning_paths.models import PathAssignment
from apps.reports.services import AnalyticsService


def _get_filter_params(request):
    """Extract dashboard filter parameters from request."""
    return {
        "category": request.GET.get("category", ""),
        "job_profile": request.GET.get("job_profile", ""),
    }


def _apply_category_filter(qs, filters, course_field="course__category"):
    """Apply category filter to a queryset."""
    category = filters["category"]
    if category:
        qs = qs.filter(**{f"{course_field}_id": category})
    return qs


def _apply_profile_filter(qs, filters, user_field="user__job_profile"):
    """Apply job profile filter to a queryset."""
    if filters["job_profile"]:
        qs = qs.filter(**{user_field: filters["job_profile"]})
    return qs


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def admin_dashboard(request):
    """Main admin dashboard view."""
    from apps.courses.models import JobProfileType

    categories = Category.objects.filter(is_active=True).order_by(
        "order", "name"
    )
    context = {
        "categories": categories,
        "job_profiles": JobProfileType.objects.filter(is_active=True).values_list("code", "name"),
    }
    return render(request, "dashboard/admin.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def dashboard_stats(request):
    """Get dashboard statistics cards."""
    filters = _get_filter_params(request)

    # Active users (filtered by profile)
    users_qs = User.objects.filter(is_active=True)
    if filters["job_profile"]:
        users_qs = users_qs.filter(job_profile__code=filters["job_profile"])
    active_users = users_qs.count()

    # Users change (vs last month)
    last_month = timezone.now() - timedelta(days=30)
    new_users_qs = users_qs.filter(date_joined__gte=last_month)
    new_users_this_month = new_users_qs.count()
    users_change = round((new_users_this_month / max(active_users, 1)) * 100, 1)

    # Compliance rate
    compliance_data = AnalyticsService.get_compliance_report()
    compliance_rate = compliance_data.get("compliance_score", 0)

    # Courses completed (filtered)
    enrollments_completed = Enrollment.objects.filter(status=Enrollment.Status.COMPLETED)
    enrollments_completed = _apply_category_filter(enrollments_completed, filters)
    enrollments_completed = _apply_profile_filter(enrollments_completed, filters)
    courses_completed = enrollments_completed.count()

    enrollments_in_progress = Enrollment.objects.filter(status=Enrollment.Status.IN_PROGRESS)
    enrollments_in_progress = _apply_category_filter(enrollments_in_progress, filters)
    enrollments_in_progress = _apply_profile_filter(enrollments_in_progress, filters)
    courses_in_progress = enrollments_in_progress.count()

    # Valid certificates (filtered)
    certs_qs = Certificate.objects.filter(status=Certificate.Status.ISSUED)
    certs_qs = _apply_category_filter(certs_qs, filters)
    certs_qs = _apply_profile_filter(certs_qs, filters)
    valid_certificates = certs_qs.count()

    # Expiring certificates (next 30 days, filtered)
    expiring_date = timezone.now() + timedelta(days=30)
    expiring_qs = Certificate.objects.filter(
        status=Certificate.Status.ISSUED,
        expires_at__lte=expiring_date,
        expires_at__gt=timezone.now(),
    )
    expiring_qs = _apply_category_filter(expiring_qs, filters)
    expiring_qs = _apply_profile_filter(expiring_qs, filters)
    expiring_certificates = expiring_qs.count()

    context = {
        "stats": {
            "active_users": active_users,
            "users_change": users_change,
            "compliance_rate": compliance_rate,
            "courses_completed": courses_completed,
            "courses_in_progress": courses_in_progress,
            "valid_certificates": valid_certificates,
            "expiring_certificates": expiring_certificates,
        }
    }

    return render(request, "dashboard/partials/stats_cards.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def compliance_chart(request):
    """Get compliance chart data."""
    filters = _get_filter_params(request)

    # Get enrollment stats by status (filtered)
    enrollments_qs = Enrollment.objects.all()
    enrollments_qs = _apply_category_filter(enrollments_qs, filters)
    enrollments_qs = _apply_profile_filter(enrollments_qs, filters)
    enrollments = enrollments_qs.values("status").annotate(count=Count("id"))

    data = {
        "completed": 0,
        "in_progress": 0,
        "not_started": 0,
        "expired": 0,
    }

    for item in enrollments:
        status = item["status"]
        if status == Enrollment.Status.COMPLETED:
            data["completed"] = item["count"]
        elif status == Enrollment.Status.IN_PROGRESS:
            data["in_progress"] = item["count"]
        elif status == Enrollment.Status.ENROLLED:
            data["not_started"] = item["count"]
        elif status == Enrollment.Status.EXPIRED:
            data["expired"] = item["count"]

    context = {"chart_data": data}
    return render(request, "dashboard/partials/compliance_chart.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def training_trend(request):
    """Get training trend chart data."""
    filters = _get_filter_params(request)

    # Build filtered completion trend inline instead of using AnalyticsService
    from django.db.models.functions import TruncWeek

    enrollments_qs = Enrollment.objects.filter(
        status=Enrollment.Status.COMPLETED,
        completed_at__isnull=False,
    )
    enrollments_qs = _apply_category_filter(enrollments_qs, filters)
    enrollments_qs = _apply_profile_filter(enrollments_qs, filters)

    completion_trend = (
        enrollments_qs.annotate(week=TruncWeek("completed_at"))
        .values("week")
        .annotate(count=Count("id"))
        .order_by("week")
    )
    # Take last 12 weeks
    trend_list = list(completion_trend)[-12:]
    trend_data = [
        {"week": item["week"].isoformat() if item["week"] else None, "count": item["count"]}
        for item in trend_list
    ]

    context = {"trend_data": trend_data}
    return render(request, "dashboard/partials/training_trend.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def expiring_certs(request):
    """Get expiring certificates list."""
    filters = _get_filter_params(request)
    expiring_date = timezone.now() + timedelta(days=30)
    now = timezone.now()

    certs_qs = Certificate.objects.filter(
        status=Certificate.Status.ISSUED,
        expires_at__lte=expiring_date,
        expires_at__gt=now,
    )
    certs_qs = _apply_category_filter(certs_qs, filters)
    certs_qs = _apply_profile_filter(certs_qs, filters)
    certificates = certs_qs.select_related("user", "course").order_by("expires_at")[:10]

    # Add days until expiry
    for cert in certificates:
        if cert.expires_at:
            cert.days_until_expiry = (cert.expires_at - now).days

    context = {"certificates": certificates}
    return render(request, "dashboard/partials/expiring_certs.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def overdue_assignments(request):
    """Get overdue assignments list."""
    filters = _get_filter_params(request)
    today = timezone.now().date()

    assignments_qs = PathAssignment.objects.filter(
        due_date__lt=today,
        status__in=[
            PathAssignment.Status.ASSIGNED,
            PathAssignment.Status.IN_PROGRESS,
        ],
    )
    assignments_qs = _apply_profile_filter(assignments_qs, filters)
    assignments = assignments_qs.select_related("user", "learning_path").order_by("due_date")[:10]

    # Add days overdue
    for assignment in assignments:
        if assignment.due_date:
            assignment.days_overdue = (today - assignment.due_date).days

    context = {"assignments": assignments}
    return render(request, "dashboard/partials/overdue_assignments.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def recent_activity(request):
    """Get recent activity feed."""
    filters = _get_filter_params(request)
    filter_type = request.GET.get("filter", "all")
    activities = []

    # Get recent enrollments
    if filter_type in ["all", "enrollments"]:
        enroll_qs = Enrollment.objects.all()
        enroll_qs = _apply_category_filter(enroll_qs, filters)
        enroll_qs = _apply_profile_filter(enroll_qs, filters)
        enrollments = enroll_qs.select_related("user", "course").order_by("-created_at")[:10]

        for e in enrollments:
            activities.append(
                {
                    "type": "enrollment",
                    "description": f"Se inscribió en {e.course.title}",
                    "user": e.user,
                    "timestamp": e.created_at,
                    "url": f"/courses/{e.course.id}/",
                }
            )

    # Get recent completions
    if filter_type in ["all", "completions"]:
        comp_qs = Enrollment.objects.filter(
            status=Enrollment.Status.COMPLETED,
            completed_at__isnull=False,
        )
        comp_qs = _apply_category_filter(comp_qs, filters)
        comp_qs = _apply_profile_filter(comp_qs, filters)
        completions = comp_qs.select_related("user", "course").order_by("-completed_at")[:10]

        for e in completions:
            activities.append(
                {
                    "type": "completion",
                    "description": f"Completó {e.course.title}",
                    "user": e.user,
                    "timestamp": e.completed_at,
                    "url": f"/courses/{e.course.id}/",
                }
            )

    # Get recent certifications
    if filter_type in ["all", "certifications"]:
        certs_qs = Certificate.objects.filter(
            status=Certificate.Status.ISSUED,
        )
        certs_qs = _apply_category_filter(certs_qs, filters)
        certs_qs = _apply_profile_filter(certs_qs, filters)
        certs = certs_qs.select_related("user", "course").order_by("-issued_at")[:10]

        for c in certs:
            activities.append(
                {
                    "type": "certification",
                    "description": f"Obtuvo certificado de {c.course.title}",
                    "user": c.user,
                    "timestamp": c.issued_at,
                    "url": f"/certifications/{c.id}/",
                }
            )

    # Sort by timestamp
    activities.sort(key=lambda x: x["timestamp"] or timezone.now(), reverse=True)
    activities = activities[:20]

    context = {"activities": activities}
    return render(request, "dashboard/partials/recent_activity.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def course_progress(request):
    """Get per-course enrollment/completion stats for chart."""
    filters = _get_filter_params(request)

    courses_qs = Course.objects.filter(status=Course.Status.PUBLISHED)
    courses_qs = _apply_category_filter(courses_qs, filters, course_field="category")

    # Build enrollment filter conditions for annotations
    enroll_filter = Q()
    if filters["job_profile"]:
        enroll_filter &= Q(enrollments__user__job_profile__code=filters["job_profile"])

    courses = (
        courses_qs.annotate(
            total_enrolled=Count("enrollments", filter=enroll_filter if enroll_filter else None),
            total_completed=Count(
                "enrollments",
                filter=(enroll_filter & Q(enrollments__status=Enrollment.Status.COMPLETED))
                if enroll_filter
                else Q(enrollments__status=Enrollment.Status.COMPLETED),
            ),
            total_in_progress=Count(
                "enrollments",
                filter=(
                    enroll_filter
                    & Q(
                        enrollments__status__in=[
                            Enrollment.Status.IN_PROGRESS,
                            Enrollment.Status.ENROLLED,
                        ]
                    )
                )
                if enroll_filter
                else Q(
                    enrollments__status__in=[
                        Enrollment.Status.IN_PROGRESS,
                        Enrollment.Status.ENROLLED,
                    ]
                ),
            ),
            avg_progress=Avg(
                "enrollments__progress",
                filter=enroll_filter if enroll_filter else None,
            ),
        )
        .filter(total_enrolled__gt=0)
        .order_by("-total_enrolled")[:10]
    )

    context = {"courses": courses}
    return render(request, "dashboard/partials/course_progress.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def course_type_distribution(request):
    """Get course type distribution data."""
    filters = _get_filter_params(request)

    courses_qs = Course.objects.filter(status=Course.Status.PUBLISHED)
    courses_qs = _apply_category_filter(courses_qs, filters, course_field="category")

    distribution = courses_qs.values("course_type").annotate(count=Count("id"))

    type_labels = {
        Course.Type.MANDATORY: "Obligatorio",
        Course.Type.OPTIONAL: "Opcional",
        Course.Type.REFRESHER: "Refuerzo",
    }

    data = []
    for item in distribution:
        data.append(
            {
                "name": type_labels.get(item["course_type"], item["course_type"]),
                "value": item["count"],
            }
        )

    # Enrollment stats by course type (filtered)
    enroll_qs = Enrollment.objects.all()
    enroll_qs = _apply_category_filter(enroll_qs, filters)
    enroll_qs = _apply_profile_filter(enroll_qs, filters)

    enrollment_by_type = enroll_qs.values("course__course_type").annotate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=Enrollment.Status.COMPLETED)),
    )

    enrollment_data = {}
    for item in enrollment_by_type:
        label = type_labels.get(item["course__course_type"], item["course__course_type"])
        enrollment_data[label] = {
            "total": item["total"],
            "completed": item["completed"],
        }

    context = {
        "type_data": data,
        "enrollment_data": enrollment_data,
    }
    return render(request, "dashboard/partials/course_type_chart.html", context)


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def assessment_performance(request):
    """Get assessment performance stats for chart."""
    filters = _get_filter_params(request)
    from apps.assessments.models import Assessment, AssessmentAttempt

    assessments_qs = Assessment.objects.all()

    # Filter by course category
    category = filters["category"]
    if category:
        assessments_qs = assessments_qs.filter(course__category_id=category)

    # Build attempt filter for profile
    attempt_filter = Q(attempts__status=AssessmentAttempt.Status.GRADED)
    if filters["job_profile"]:
        attempt_filter &= Q(attempts__user__job_profile__code=filters["job_profile"])

    assessments = (
        assessments_qs.annotate(
            total_attempts=Count("attempts", filter=attempt_filter),
            passed=Count(
                "attempts",
                filter=attempt_filter & Q(attempts__passed=True),
            ),
            avg_score=Avg(
                "attempts__score",
                filter=attempt_filter,
            ),
        )
        .filter(total_attempts__gt=0)
        .order_by("-total_attempts")[:10]
    )

    context = {"assessments": assessments}
    return render(request, "dashboard/partials/assessment_performance.html", context)


# ============================================================================
# Report Views
# ============================================================================

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from apps.reports.models import GeneratedReport, ReportTemplate, ScheduledReport
from apps.reports.services import ReportService, ScheduledReportService


@login_required
@require_GET
def report_list(request):
    """Report templates list."""
    templates = ReportTemplate.objects.filter(is_active=True).order_by("name")
    context = {"templates": templates}
    return render(request, "reports/report_list.html", context)


@login_required
@require_POST
def generate_report(request, template_id):
    """Generate a report from template."""
    template = get_object_or_404(ReportTemplate, id=template_id, is_active=True)

    format_type = request.POST.get("format", template.default_format)
    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")

    filters = {}
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date

    report = ReportService.create_report_request(
        template=template,
        user=request.user,
        format_type=format_type,
        filters=filters,
    )

    # In production, this would trigger a Celery task
    # For now, we'll return the pending report card
    context = {"reports": [report]}
    return render(request, "reports/partials/generated_reports.html", context)


@login_required
@require_GET
def my_reports(request):
    """Get user's generated reports."""
    reports = ReportService.get_user_reports(request.user, limit=20)
    context = {"reports": reports}
    return render(request, "reports/partials/generated_reports.html", context)


@login_required
@require_GET
def report_status(request, report_id):
    """Get report generation status (for polling)."""
    report = get_object_or_404(GeneratedReport, id=report_id, generated_by=request.user)

    if (
        report.status == GeneratedReport.Status.COMPLETED
        or report.status == GeneratedReport.Status.FAILED
    ):
        return render(request, "reports/partials/report_row.html", {"report": report})
    else:
        # Still processing
        return HttpResponse(
            f'<span class="badge badge-info gap-1" '
            f'hx-get="/reports/{report_id}/status/" '
            f'hx-trigger="every 3s" hx-swap="outerHTML">'
            f'<span class="loading loading-spinner loading-xs"></span>'
            f"Generando</span>"
        )


@login_required
@require_http_methods(["DELETE"])
def delete_report(request, report_id):
    """Delete a generated report."""
    report = get_object_or_404(GeneratedReport, id=report_id, generated_by=request.user)

    if report.file:
        report.file.delete(save=False)
    report.delete()

    return HttpResponse("")  # Empty response removes the row


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def scheduled_list(request):
    """Get scheduled reports list."""
    schedules = (
        ScheduledReport.objects.filter(created_by=request.user)
        .select_related("template")
        .order_by("-created_at")
    )

    context = {"schedules": schedules}
    return render(request, "reports/partials/scheduled_list.html", context)


@login_required
@require_POST
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def schedule_create(request):
    """Create a scheduled report."""
    template_id = request.POST.get("template")
    template = get_object_or_404(ReportTemplate, id=template_id)

    frequency = request.POST.get("frequency", "daily")
    time_str = request.POST.get("time_of_day", "08:00")
    recipients_str = request.POST.get("recipients", "")

    from datetime import datetime

    time_of_day = datetime.strptime(time_str, "%H:%M").time()
    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

    ScheduledReportService.create_schedule(
        template=template,
        name=f"{template.name} - {frequency.title()}",
        frequency=frequency,
        format_type=template.default_format,
        time_of_day=time_of_day,
        user=request.user,
        recipients=recipients,
    )

    schedules = (
        ScheduledReport.objects.filter(created_by=request.user)
        .select_related("template")
        .order_by("-created_at")
    )

    context = {"schedules": schedules}
    return render(request, "reports/partials/scheduled_list.html", context)


@login_required
@require_POST
@require_rol(Rol.ADMINISTRADOR, redirect_url="reports:list")
def schedule_toggle(request, schedule_id):
    """Toggle scheduled report active status."""
    schedule = get_object_or_404(ScheduledReport, id=schedule_id, created_by=request.user)
    ScheduledReportService.toggle_schedule(schedule)

    return HttpResponse(
        f'<span class="badge {"badge-success" if schedule.is_active else "badge-ghost"}">'
        f"{'Activo' if schedule.is_active else 'Inactivo'}</span>"
    )
