"""
URL configuration for certifications app.
"""

from django.urls import include, path

from . import views

app_name = "certifications"

urlpatterns = [
    # API
    path("api/", include("apps.certifications.api.urls")),
    # Web views
    path("", views.my_certificates, name="my_certificates"),
    path("<int:certificate_id>/", views.certificate_detail, name="detail"),
    path("<int:certificate_id>/download/", views.certificate_download, name="download"),
    path("verify/", views.verify_certificate, name="verify"),
    path("verify/<str:certificate_number>/", views.verify_certificate, name="verify_number"),
    # Staff admin panel (B2)
    path("admin/templates/", views.template_list, name="template_list"),
    path("admin/templates/new/", views.template_create, name="template_create"),
    path(
        "admin/templates/<int:template_id>/edit/",
        views.template_edit,
        name="template_edit",
    ),
    path(
        "admin/templates/<int:template_id>/preview/",
        views.template_preview,
        name="template_preview",
    ),
    path(
        "admin/templates/<int:template_id>/toggle/",
        views.template_toggle_active,
        name="template_toggle_active",
    ),
]
