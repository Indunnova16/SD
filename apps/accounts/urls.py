"""
URL configuration for accounts app (web views).
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Authentication
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Password management
    path("password/change/", views.change_password, name="change_password"),
    path("password/reset/", views.password_reset_request, name="password_reset"),
    path(
        "password/reset/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    # Profile
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    # Lockout
    path("lockout/", views.lockout_view, name="lockout"),
    # User Management (Admin only)
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("users/<int:user_id>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:user_id>/toggle-status/", views.user_toggle_status, name="user_toggle_status"),
    path("users/<int:user_id>/delete/", views.user_delete, name="user_delete"),
    path("users/<int:user_id>/export-pdf/", views.user_export_pdf, name="user_export_pdf"),
    path("users/<int:user_id>/learning-history/", views.user_learning_history, name="user_learning_history"),
    path(
        "users/<int:user_id>/reset-password/",
        views.admin_reset_password,
        name="admin_reset_password",
    ),
    # Bulk Upload
    path("users/bulk-upload/", views.bulk_upload, name="bulk_upload"),
    path("users/bulk-upload/template/", views.download_template, name="download_template"),
    # Export
    path("users/export/pending/", views.export_pending_users, name="export_pending_users"),
    # Help / User Manual
    path("help/admin/", views.help_admin, name="help_admin"),
    path("help/worker/", views.help_worker, name="help_worker"),
]
