"""
URLs del portal público de feedback (apps.feedback).

Montado en `config/urls.py` bajo el prefijo `feedback/`. Debe crearse en el
MISMO commit que agrega el `include("apps.feedback.urls")` en la raíz — ver
nota de riesgo de secuencia en `config/urls.py` y en el PLAN del issue #71.
"""

from django.urls import path

from apps.feedback import views

app_name = "feedback"

urlpatterns = [
    path("", views.lista_view, name="lista"),
    path("nuevo/", views.nuevo_view, name="nuevo"),
    path("<int:ticket_id>/", views.detalle_view, name="detalle"),
]
