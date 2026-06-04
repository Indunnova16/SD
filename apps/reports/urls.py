"""
URL configuration for reports app.
"""

from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    # Report list and generation
    path("", views.report_list, name="list"),
    path("generate/<int:template_id>/", views.generate_report, name="generate"),
    path("my-reports/", views.my_reports, name="my-reports"),
    path("<int:report_id>/status/", views.report_status, name="status"),
    path("<int:report_id>/delete/", views.delete_report, name="delete"),
    # Scheduled reports
    path("scheduled/", views.scheduled_list, name="scheduled-list"),
    path("scheduled/create/", views.schedule_create, name="schedule-create"),
    path("scheduled/<int:schedule_id>/toggle/", views.schedule_toggle, name="schedule-toggle"),
    # Dashboard views
    path("dashboard/", views.admin_dashboard, name="dashboard"),
    path("dashboard/stats/", views.dashboard_stats, name="dashboard-stats"),
    path("dashboard/compliance-chart/", views.compliance_chart, name="dashboard-compliance-chart"),
    path("dashboard/training-trend/", views.training_trend, name="dashboard-training-trend"),
    path("dashboard/expiring-certs/", views.expiring_certs, name="dashboard-expiring-certs"),
    path(
        "dashboard/overdue-assignments/",
        views.overdue_assignments,
        name="dashboard-overdue-assignments",
    ),
    path("dashboard/recent-activity/", views.recent_activity, name="dashboard-recent-activity"),
    path("dashboard/course-progress/", views.course_progress, name="dashboard-course-progress"),
    path("dashboard/course-types/", views.course_type_distribution, name="dashboard-course-types"),
    path(
        "dashboard/assessment-performance/",
        views.assessment_performance,
        name="dashboard-assessment-performance",
    ),
]
