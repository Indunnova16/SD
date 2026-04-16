"""Modelos para el sistema de inspecciones de equipos y maquinaria.

Incluye:
- Inspecciones de máquinas/equipos
- Formularios de inspección
- Hallazgos y acciones correctivas
- Firmas digitales
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class EquipmentCategory(models.Model):
    """Categoría de equipos (Excavadoras, Grúas, Compresores, etc.)"""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoría de Equipo"
        verbose_name_plural = "Categorías de Equipos"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Máquinas y equipos a inspeccionar"""

    folio = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(EquipmentCategory, on_delete=models.PROTECT)
    location = models.CharField(max_length=200)
    acquisition_date = models.DateField()
    serial_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.folio} - {self.name}"


class Inspection(models.Model):
    """Registro de inspección de un equipo"""

    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("in_progress", "En Proceso"),
        ("completed", "Completada"),
        ("rejected", "Rechazada"),
    )

    CRITICALITY_CHOICES = (
        ("low", "Baja"),
        ("medium", "Media"),
        ("critical", "Crítica"),
    )

    folio = models.CharField(max_length=50, unique=True)
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="inspections")
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inspections_conducted",
    )
    inspection_date = models.DateTimeField(default=timezone.now)
    scheduled_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    criticality = models.CharField(max_length=20, choices=CRITICALITY_CHOICES, default="low")

    # Detalles de la inspección
    location = models.CharField(max_length=200)
    observations = models.TextField(blank=True)

    # Firma digital
    signature_image = models.ImageField(upload_to="signatures/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Inspección"
        verbose_name_plural = "Inspecciones"
        ordering = ["-inspection_date"]
        indexes = [
            models.Index(fields=["folio"]),
            models.Index(fields=["equipment", "inspection_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.folio} - {self.equipment.name}"

    def mark_as_completed(self):
        """Marca la inspección como completada"""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save()


class InspectionChecklist(models.Model):
    """Checklist de inspección con items verificables"""

    inspection = models.OneToOneField(
        Inspection, on_delete=models.CASCADE, related_name="checklist"
    )

    # Items de verificación (generales)
    operational_condition = models.BooleanField(null=True, blank=True)
    safety_devices_ok = models.BooleanField(null=True, blank=True)
    maintenance_current = models.BooleanField(null=True, blank=True)
    documentation_complete = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Checklist de Inspección"
        verbose_name_plural = "Checklists de Inspección"

    def __str__(self):
        return f"Checklist - {self.inspection.folio}"


class Finding(models.Model):
    """Hallazgos encontrados durante la inspección"""

    SEVERITY_CHOICES = (
        ("minor", "Menor"),
        ("major", "Mayor"),
        ("critical", "Crítica"),
    )

    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="findings")
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    photo = models.ImageField(upload_to="findings/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hallazgo"
        verbose_name_plural = "Hallazgos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.inspection.folio} - {self.description[:50]}"


class CorrectiveAction(models.Model):
    """Acciones correctivas para resolver hallazgos"""

    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("in_progress", "En Progreso"),
        ("completed", "Completada"),
        ("cancelled", "Cancelada"),
    )

    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="corrective_actions"
    )
    description = models.TextField()
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="corrective_actions",
    )
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    completion_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acción Correctiva"
        verbose_name_plural = "Acciones Correctivas"
        ordering = ["due_date"]

    def __str__(self):
        return f"AC - {self.finding.inspection.folio}: {self.description[:50]}"

    @property
    def is_overdue(self):
        """Verifica si la acción está vencida"""
        if self.status != "completed":
            from datetime import date

            return self.due_date < date.today()
        return False
