"""
Forms for pre-operational talks app.
"""

from django import forms
from apps.preop_talks.models import TalkTemplate


class TalkTemplateForm(forms.ModelForm):
    """Form for creating and editing talk templates."""

    key_points = forms.CharField(
        label="Puntos Clave",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Ingresa cada punto clave en una línea nueva",
        required=False,
    )

    safety_topics = forms.CharField(
        label="Temas de Seguridad",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Ingresa cada tema de seguridad en una línea nueva",
        required=False,
    )

    target_activities = forms.CharField(
        label="Actividades Objetivo",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Ingresa cada actividad objetivo en una línea nueva",
        required=False,
    )

    class Meta:
        model = TalkTemplate
        fields = [
            "title",
            "description",
            "talk_type",
            "content",
            "key_points",
            "safety_topics",
            "estimated_duration",
            "requires_signature",
            "target_activities",
            "recurrence_months",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input input-bordered",
                    "placeholder": "Ej: Charla de Seguridad en Alturas",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered",
                    "rows": 3,
                    "placeholder": "Breve descripción de la plantilla",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered",
                    "rows": 6,
                    "placeholder": "Contenido completo de la charla",
                }
            ),
            "talk_type": forms.Select(attrs={"class": "select select-bordered"}),
            "estimated_duration": forms.NumberInput(
                attrs={
                    "class": "input input-bordered",
                    "min": "5",
                    "max": "480",
                    "placeholder": "Duración en minutos",
                }
            ),
            "requires_signature": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "recurrence_months": forms.NumberInput(
                attrs={
                    "class": "input input-bordered",
                    "min": "1",
                    "placeholder": "Cada cuántos meses reciclar",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def clean_key_points(self):
        """Convert key_points from textarea to list."""
        data = self.cleaned_data.get("key_points", "").strip()
        if data:
            return [point.strip() for point in data.split("\n") if point.strip()]
        return []

    def clean_safety_topics(self):
        """Convert safety_topics from textarea to list."""
        data = self.cleaned_data.get("safety_topics", "").strip()
        if data:
            return [topic.strip() for topic in data.split("\n") if topic.strip()]
        return []

    def clean_target_activities(self):
        """Convert target_activities from textarea to list."""
        data = self.cleaned_data.get("target_activities", "").strip()
        if data:
            return [activity.strip() for activity in data.split("\n") if activity.strip()]
        return []

    def save(self, commit=True):
        """Save the form and convert text lists to JSON."""
        instance = super().save(commit=False)
        instance.key_points = self.clean_key_points()
        instance.safety_topics = self.clean_safety_topics()
        instance.target_activities = self.clean_target_activities()
        if commit:
            instance.save()
        return instance
