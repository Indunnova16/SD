"""
URL configuration for SD LMS project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Admin site customization
admin.site.site_header = "SD LMS Administración"
admin.site.site_title = "SD LMS"
admin.site.index_title = "Panel de Administración"


def home(request):
    """Redirect to dashboard if logged in, otherwise to login."""
    if request.user.is_authenticated:
        return redirect("reports:dashboard")
    return redirect("accounts:login")


def health_check(request):
    """Health check endpoint."""
    return HttpResponse("OK")


urlpatterns = [
    # Health check
    path("health/", health_check, name="health"),
    # Home
    path("", home, name="home"),
    # Admin
    path("admin/", admin.site.urls),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API v1
    path("api/v1/auth/", include("apps.accounts.api.urls")),
    path("api/v1/users/", include("apps.accounts.api.urls_users")),
    path("api/v1/courses/", include("apps.courses.api.urls")),
    path("api/v1/learning-paths/", include("apps.learning_paths.api.urls")),
    path("api/v1/assessments/", include("apps.assessments.api.urls")),
    path("api/v1/certifications/", include("apps.certifications.api.urls")),
    path("api/v1/lessons-learned/", include("apps.lessons_learned.api.urls")),
    path("api/v1/preop-talks/", include("apps.preop_talks.api.urls")),
    path("api/v1/notifications/", include("apps.notifications.api.urls")),
    path("api/v1/sync/", include("apps.sync.api.urls")),
    path("api/v1/reports/", include("apps.reports.api.urls")),
    path("api/v1/integrations/", include("apps.integrations.api.urls")),
    path("api/v1/occupational-profiles/", include("apps.occupational_profiles.api.urls")),
    # Web views (HTMX)
    path("accounts/", include("apps.accounts.urls")),
    path("courses/", include("apps.courses.urls")),
    path("learning-paths/", include("apps.learning_paths.urls")),
    path("assessments/", include("apps.assessments.urls")),
    path("certifications/", include("apps.certifications.urls")),
    path("lessons-learned/", include("apps.lessons_learned.urls")),
    path("preop-talks/", include("apps.preop_talks.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("reports/", include("apps.reports.urls")),
    path("gamification/", include("apps.gamification.urls")),
]

# Debug toolbar (only in debug mode)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
