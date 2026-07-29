"""
Form de creación de tickets del portal público de feedback.

`NuevoTicketForm` es un `forms.Form` simple (NO ModelForm): la creación real
del ticket, sus adjuntos y la sincronización a GitHub las orquesta
`services.py` (sub-item A4). Este form solo valida el input crudo que llega
del portal público/anónimo, incluyendo un campo honeypot (`website`) para
descartar envíos automatizados de bots simples.

A diferencia del portal de Arcopack (que usa Gemini para autocompletar
campos faltantes), SD no tiene ese soporte: todos los campos reales son
siempre obligatorios.
"""

from django import forms
from django.utils.translation import gettext_lazy as _


class NuevoTicketForm(forms.Form):
    """Formulario público para reportar un ticket de feedback."""

    nombre_reportante = forms.CharField(
        label=_("Nombre"),
        min_length=2,
        required=True,
    )
    asunto = forms.CharField(
        label=_("Asunto"),
        max_length=200,
        required=True,
    )
    descripcion = forms.CharField(
        label=_("Descripción"),
        min_length=10,
        required=True,
        widget=forms.Textarea,
    )
    # Honeypot anti-spam: campo invisible para un humano (oculto vía CSS),
    # que un bot que autocompleta formularios suele rellenar igual. Un
    # humano real nunca lo ve ni lo llena. Se mantiene `required=False`
    # para no delatarlo como obligatorio en el HTML generado.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "style": "position:absolute;left:-9999px",
                "tabindex": "-1",
                "autocomplete": "off",
            }
        ),
    )

    def clean_website(self):
        website = self.cleaned_data.get("website", "")
        if website:
            # Mensaje genérico a propósito: NO mencionar "bot"/"honeypot"/
            # "spam" para no darle pistas a quien intente evadir el filtro.
            raise forms.ValidationError(
                _("No se pudo procesar el formulario, intentá de nuevo.")
            )
        return website


class ResolverTicketForm(forms.Form):
    """Formulario público para marcar un ticket como resuelto.

    Pide el nombre de quien resuelve para dejar trazabilidad: el portal es
    anónimo (cualquiera con el link puede resolver, igual que en Arcopack),
    así que el nombre es el único registro de quién cerró el caso. Si se
    resuelve por error, el equipo puede reabrir el issue desde GitHub.
    """

    resuelto_por = forms.CharField(
        label=_("Tu nombre"),
        min_length=2,
        max_length=120,
        required=True,
    )
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "style": "position:absolute;left:-9999px",
                "tabindex": "-1",
                "autocomplete": "off",
            }
        ),
    )

    def clean_website(self):
        website = self.cleaned_data.get("website", "")
        if website:
            raise forms.ValidationError(
                _("No se pudo procesar el formulario, intentá de nuevo.")
            )
        return website
