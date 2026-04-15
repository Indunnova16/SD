"""Configuración del panel de administración para inspecciones."""

from django.contrib import admin

from .models import (
    CorrectiveAction,
    Equipment,
    EquipmentCategory,
    Finding,
    Inspection,
    InspectionChecklist,
)


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ['folio', 'name', 'category', 'location', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['folio', 'name', 'serial_number']
    date_hierarchy = 'created_at'


class InspectionChecklistInline(admin.TabularInline):
    model = InspectionChecklist
    extra = 1


class FindingInline(admin.TabularInline):
    model = Finding
    extra = 1


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ['folio', 'equipment', 'inspector', 'status', 'criticality', 'inspection_date', 'completed_at']
    list_filter = ['status', 'criticality', 'inspection_date']
    search_fields = ['folio', 'equipment__name', 'inspector__first_name']
    date_hierarchy = 'inspection_date'
    inlines = [InspectionChecklistInline, FindingInline]
    readonly_fields = ['folio', 'created_at', 'updated_at', 'completed_at']

    fieldsets = (
        ('Información General', {
            'fields': ('folio', 'equipment', 'inspector', 'status')
        }),
        ('Detalles', {
            'fields': ('inspection_date', 'scheduled_date', 'location', 'observations', 'criticality')
        }),
        ('Firma Digital', {
            'fields': ('signature_image',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InspectionChecklist)
class InspectionChecklistAdmin(admin.ModelAdmin):
    list_display = ['inspection', 'operational_condition', 'safety_devices_ok', 'maintenance_current']
    list_filter = ['operational_condition', 'safety_devices_ok']
    search_fields = ['inspection__folio']


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ['inspection', 'description', 'severity', 'created_at']
    list_filter = ['severity', 'created_at']
    search_fields = ['inspection__folio', 'description']
    date_hierarchy = 'created_at'


@admin.register(CorrectiveAction)
class CorrectiveActionAdmin(admin.ModelAdmin):
    list_display = ['finding', 'responsible', 'status', 'due_date', 'completion_date']
    list_filter = ['status', 'due_date', 'created_at']
    search_fields = ['finding__inspection__folio', 'description']
    date_hierarchy = 'due_date'

    fieldsets = (
        ('Información General', {
            'fields': ('finding', 'description', 'responsible', 'status')
        }),
        ('Cronograma', {
            'fields': ('due_date', 'completion_date')
        }),
        ('Notas', {
            'fields': ('notes',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
