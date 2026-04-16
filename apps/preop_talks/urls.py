"""
URL configuration for preop_talks app.
"""

from django.urls import path

from apps.preop_talks import views

app_name = "preop_talks"

urlpatterns = [
    # Talk list
    path("", views.talk_list, name="list"),
    path("today/", views.today_talks, name="today"),
    path("table/", views.talks_table, name="table"),
    # Templates
    path("templates/", views.templates_list, name="templates"),
    path("templates/create/", views.template_create, name="template-create"),
    # Talk CRUD
    path("create/", views.talk_create, name="create"),
    path("<int:talk_id>/", views.talk_detail, name="detail"),
    path("<int:talk_id>/conduct/", views.talk_conduct, name="conduct"),
    path("<int:talk_id>/report/", views.talk_report, name="report"),
    # Talk actions
    path("<int:talk_id>/start/", views.start_talk, name="start"),
    path("<int:talk_id>/complete/", views.complete_talk, name="complete"),
    path("<int:talk_id>/update-notes/", views.update_notes, name="update-notes"),
    # Attendees
    path("<int:talk_id>/attendees/", views.attendees_list, name="attendees"),
    path("<int:talk_id>/add-attendee/", views.add_attendee, name="add-attendee"),
    path("attendees/<int:attendee_id>/remove/", views.remove_attendee, name="remove-attendee"),
    path("attendees/<int:attendee_id>/sign/", views.sign_attendance, name="sign"),
    # User search
    path("search-users/", views.search_users, name="search-users"),
]
