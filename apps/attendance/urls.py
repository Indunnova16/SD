"""URL configuration for attendance app."""

from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    # Kiosko móvil con reconocimiento facial (PÚBLICO — sin login)
    path("marcacion-movil/", views.mobile_face_checkin, name="mobile_face_checkin"),
    # Staff
    path("marcacion-movil/qr/", views.mobile_face_qr, name="mobile_face_qr"),
    path("eventos-faciales/", views.face_event_list, name="face_event_list"),
    path("usuarios/<int:pk>/reindexar-rostro/", views.reindex_user_face, name="reindex_user_face"),
]
