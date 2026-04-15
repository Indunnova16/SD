"""URLs para el módulo de inspecciones."""

from django.urls import path

from . import views

app_name = 'inspections'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Inspecciones
    path('inspecciones/', views.InspectionListView.as_view(), name='inspection-list'),
    path('inspecciones/nueva/', views.InspectionCreateView.as_view(), name='inspection-create'),
    path('inspecciones/<int:pk>/', views.InspectionDetailView.as_view(), name='inspection-detail'),

    # Equipos
    path('equipos/', views.EquipmentListView.as_view(), name='equipment-list'),

    # Hallazgos
    path('inspecciones/<int:inspection_id>/hallazgo/nuevo/', views.FindingCreateView.as_view(), name='finding-create'),

    # Acciones Correctivas
    path('hallazgos/<int:finding_id>/accion-correctiva/nueva/', views.CorrectiveActionCreateView.as_view(), name='corrective-action-create'),
]
