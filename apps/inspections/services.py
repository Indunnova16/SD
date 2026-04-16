"""Servicios y lógica de negocio para inspecciones.

Incluye operaciones complejas que no pertenecen a las vistas.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import CorrectiveAction, Equipment, Finding, Inspection


class InspectionService:
    """Servicio para operaciones de inspección"""

    @staticmethod
    def get_pending_inspections():
        """Obtiene inspecciones pendientes"""
        return Inspection.objects.filter(status="pending").order_by("scheduled_date")

    @staticmethod
    def get_overdue_inspections():
        """Obtiene inspecciones vencidas (programadas pero no realizadas)"""
        today = timezone.now().date()
        return Inspection.objects.filter(
            status__in=["pending", "in_progress"], scheduled_date__lt=today
        )

    @staticmethod
    def get_critical_inspections():
        """Obtiene inspecciones críticas"""
        return Inspection.objects.filter(criticality="critical")

    @staticmethod
    def get_inspections_by_week(year, week):
        """Obtiene inspecciones de una semana específica"""
        from django.db.models.functions import TruncWeek

        return Inspection.objects.annotate(week=TruncWeek("inspection_date")).filter(
            inspection_date__year=year, inspection_date__week=week
        )

    @staticmethod
    def calculate_completion_rate(equipment):
        """Calcula el porcentaje de inspecciones completadas de un equipo"""
        total = equipment.inspections.count()
        if total == 0:
            return 0
        completed = equipment.inspections.filter(status="completed").count()
        return (completed / total) * 100

    @staticmethod
    def get_inspection_summary(inspection):
        """Obtiene un resumen de la inspección con estadísticas"""
        return {
            "total_findings": inspection.findings.count(),
            "critical_findings": inspection.findings.filter(severity="critical").count(),
            "major_findings": inspection.findings.filter(severity="major").count(),
            "pending_actions": inspection.findings.count() > 0,
            "completion_percentage": (
                sum(
                    1
                    for f in inspection.findings.all()
                    if f.corrective_actions.filter(status="completed").exists()
                )
                / max(1, inspection.findings.count())
            )
            * 100,
        }


class FindingService:
    """Servicio para operaciones de hallazgos"""

    @staticmethod
    def get_critical_findings():
        """Obtiene hallazgos críticos"""
        return Finding.objects.filter(severity="critical")

    @staticmethod
    def get_findings_by_equipment(equipment):
        """Obtiene todos los hallazgos de un equipo"""
        return Finding.objects.filter(inspection__equipment=equipment).order_by("-created_at")

    @staticmethod
    def get_unresolved_findings():
        """Obtiene hallazgos sin acciones correctivas asignadas"""
        return Finding.objects.exclude(corrective_actions__status="completed").distinct()


class CorrectiveActionService:
    """Servicio para operaciones de acciones correctivas"""

    @staticmethod
    def get_overdue_actions():
        """Obtiene acciones correctivas vencidas"""
        today = timezone.now().date()
        return CorrectiveAction.objects.filter(
            status__in=["pending", "in_progress"], due_date__lt=today
        )

    @staticmethod
    def get_actions_by_responsible(user):
        """Obtiene acciones correctivas asignadas a un usuario"""
        return CorrectiveAction.objects.filter(
            responsible=user, status__in=["pending", "in_progress"]
        ).order_by("due_date")

    @staticmethod
    def get_actions_statistics():
        """Obtiene estadísticas de acciones correctivas"""
        return {
            "total": CorrectiveAction.objects.count(),
            "pending": CorrectiveAction.objects.filter(status="pending").count(),
            "in_progress": CorrectiveAction.objects.filter(status="in_progress").count(),
            "completed": CorrectiveAction.objects.filter(status="completed").count(),
            "overdue": CorrectiveAction.objects.filter(
                status__in=["pending", "in_progress"], due_date__lt=timezone.now().date()
            ).count(),
        }

    @staticmethod
    def mark_as_completed(action, completion_date=None):
        """Marca una acción como completada"""
        if completion_date is None:
            completion_date = timezone.now().date()
        action.status = "completed"
        action.completion_date = completion_date
        action.save()


class DashboardService:
    """Servicio para datos del dashboard"""

    @staticmethod
    def get_dashboard_stats():
        """Obtiene estadísticas para el dashboard"""
        now = timezone.now()
        one_week_ago = now - timedelta(days=7)

        return {
            "total_inspections": Inspection.objects.count(),
            "completed_inspections": Inspection.objects.filter(status="completed").count(),
            "in_progress": Inspection.objects.filter(status="in_progress").count(),
            "critical_inspections": Inspection.objects.filter(criticality="critical").count(),
            "recent_inspections": Inspection.objects.select_related(
                "equipment", "inspector"
            ).order_by("-inspection_date")[:10],
            "overdue_inspections": InspectionService.get_overdue_inspections(),
            "overdue_actions": CorrectiveActionService.get_overdue_actions(),
            "this_week_inspections": Inspection.objects.filter(
                inspection_date__gte=one_week_ago
            ).count(),
        }

    @staticmethod
    def get_equipment_stats():
        """Obtiene estadísticas por equipo"""
        return Equipment.objects.annotate(
            total_inspections=Count("inspections"),
            completed_inspections=Count("inspections", filter=Q(inspections__status="completed")),
            critical_inspections=Count(
                "inspections", filter=Q(inspections__criticality="critical")
            ),
        )
