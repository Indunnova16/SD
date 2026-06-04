"""
URL configuration for courses app.
"""

from django.urls import include, path

from . import views

app_name = "courses"

urlpatterns = [
    # API
    path("api/", include("apps.courses.api.urls")),
    # Web views
    path("", views.course_list, name="list"),
    path("my-courses/", views.my_courses, name="my_courses"),
    path(
        "enrollment/<int:enrollment_id>/reenable/",
        views.reenable_course,
        name="reenable_course",
    ),
    path("create/", views.course_create, name="create"),
    path("<int:course_id>/", views.course_detail, name="detail"),
    path("<int:course_id>/enroll/", views.enroll_course, name="enroll"),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/",
        views.lesson_view,
        name="lesson",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/file/",
        views.lesson_content_file,
        name="lesson_content_file",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/progress/",
        views.update_progress,
        name="update_progress",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/video-progress/",
        views.update_video_progress,
        name="update_video_progress",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/sign/",
        views.sign_lesson_evidence,
        name="sign_lesson_evidence",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/attendance/",
        views.attendance_lesson_view,
        name="attendance_lesson",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/attendance/sign/",
        views.save_attendance_signature,
        name="save_attendance_signature",
    ),
    path(
        "<int:course_id>/lessons/<int:lesson_id>/attendance/export-pdf/",
        views.export_attendance_pdf,
        name="export_attendance_pdf",
    ),
    path(
        "<int:course_id>/sign-completion/",
        views.sign_course_completion,
        name="sign_course_completion",
    ),
    # Parametrizacion hub
    path("parametrizacion/", views.parametrizacion_hub, name="parametrizacion"),
    # Course admin management (Parametrizacion)
    path("admin-courses/", views.course_admin_list, name="course_admin_list"),
    path(
        "admin-courses/<int:course_id>/edit-params/",
        views.course_edit_params,
        name="course_edit_params",
    ),
    path(
        "admin-courses/<int:course_id>/toggle-status/",
        views.course_toggle_status,
        name="course_toggle_status",
    ),
    path(
        "admin-courses/<int:course_id>/edit/",
        views.course_full_edit,
        name="course_full_edit",
    ),
    path(
        "admin-courses/<int:course_id>/delete/",
        views.course_delete,
        name="course_delete",
    ),
    # Job Profile Type management (Parametrizacion)
    path("profiles/create/", views.profile_type_create, name="profile_type_create"),
    path("profiles/<int:profile_id>/edit/", views.profile_type_edit, name="profile_type_edit"),
    path(
        "profiles/<int:profile_id>/delete/", views.profile_type_delete, name="profile_type_delete"
    ),
    path(
        "profiles/<int:profile_id>/toggle/",
        views.profile_type_toggle_active,
        name="profile_type_toggle",
    ),
    # Category management (Maestros)
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),
    path(
        "categories/<int:category_id>/toggle/", views.category_toggle_active, name="category_toggle"
    ),
    # Course Builder
    path(
        "admin-courses/<int:course_id>/builder/",
        views.course_builder,
        name="course_builder",
    ),
    path(
        "admin-courses/<int:course_id>/builder/update-info/",
        views.builder_update_course_info,
        name="builder_update_course_info",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/add/",
        views.builder_add_module,
        name="builder_add_module",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/edit/",
        views.builder_edit_module,
        name="builder_edit_module",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/delete/",
        views.builder_delete_module,
        name="builder_delete_module",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/reorder/",
        views.builder_reorder_modules,
        name="builder_reorder_modules",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/lessons/add/",
        views.builder_add_lesson,
        name="builder_add_lesson",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/lessons/<int:lesson_id>/edit/",
        views.builder_edit_lesson,
        name="builder_edit_lesson",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/lessons/<int:lesson_id>/delete/",
        views.builder_delete_lesson,
        name="builder_delete_lesson",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/update-time-limit/",
        views.builder_update_quiz_time_limit,
        name="builder_update_quiz_time_limit",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/lessons/reorder/",
        views.builder_reorder_lessons,
        name="builder_reorder_lessons",
    ),
    path(
        "admin-courses/<int:course_id>/builder/modules/<int:module_id>/lessons/<int:lesson_id>/assign-quiz/",
        views.builder_assign_quiz,
        name="builder_assign_quiz",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/create/",
        views.builder_create_quiz,
        name="builder_create_quiz",
    ),
    # Assessment Question Editor (Builder)
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/",
        views.builder_assessment_editor,
        name="builder_assessment_editor",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/edit/",
        views.builder_edit_assessment,
        name="builder_edit_assessment",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/questions/add/",
        views.builder_add_question,
        name="builder_add_question",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/questions/<int:question_id>/edit/",
        views.builder_edit_question,
        name="builder_edit_question",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/questions/<int:question_id>/delete/",
        views.builder_delete_question,
        name="builder_delete_question",
    ),
    path(
        "admin-courses/<int:course_id>/builder/quiz/<int:assessment_id>/questions/reorder/",
        views.builder_reorder_questions,
        name="builder_reorder_questions",
    ),
]
