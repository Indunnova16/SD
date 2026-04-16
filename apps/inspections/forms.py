"""Formularios para el sistema de inspecciones."""

from django import forms

from .models import CorrectiveAction, Finding, Inspection, InspectionChecklist


class InspectionForm(forms.ModelForm):
    """Formulario para crear/editar inspecciones"""

    class Meta:
        model = Inspection
        fields = ["equipment", "scheduled_date", "location", "observations", "criticality"]
        labels = {
            "equipment": "Equipo a Inspeccionar",
            "scheduled_date": "Fecha de Inspección",
            "location": "Ubicación",
            "observations": "Observaciones",
            "criticality": "Nivel de Criticidad",
        }
        widgets = {
            "equipment": forms.Select(
                attrs={
                    "class": "form-select form-select-lg",
                    "required": True,
                }
            ),
            "scheduled_date": forms.DateInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "type": "date",
                    "required": True,
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "placeholder": "Ej: Línea Bogotá-Medellín, km 45",
                    "required": True,
                }
            ),
            "observations": forms.Textarea(
                attrs={
                    "class": "form-control form-control-lg",
                    "rows": 4,
                    "placeholder": "Detalles relevantes sobre la inspección a realizar...",
                }
            ),
            "criticality": forms.Select(
                attrs={
                    "class": "form-select form-select-lg",
                    "required": True,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mejorar presentación del campo equipment
        self.fields["equipment"].queryset = self.fields["equipment"].queryset.select_related(
            "category"
        )
        self.fields["equipment"].label_from_instance = lambda obj: (
            f"[{obj.category}] {obj.folio} - {obj.name}"
        )


class InspectionChecklistForm(forms.ModelForm):
    """Formulario para el checklist de inspección"""

    class Meta:
        model = InspectionChecklist
        fields = [
            "operational_condition",
            "safety_devices_ok",
            "maintenance_current",
            "documentation_complete",
        ]
        widgets = {
            "operational_condition": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "safety_devices_ok": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "maintenance_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "documentation_complete": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class FindingForm(forms.ModelForm):
    """Formulario para registrar hallazgos"""

    class Meta:
        model = Finding
        fields = ["description", "severity", "photo"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Descripción del hallazgo",
                }
            ),
            "severity": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),
        }


class CorrectiveActionForm(forms.ModelForm):
    """Formulario para acciones correctivas"""

    class Meta:
        model = CorrectiveAction
        fields = ["description", "responsible", "due_date", "notes"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Descripción de la acción correctiva",
                }
            ),
            "responsible": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "due_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Notas adicionales",
                }
            ),
        }
