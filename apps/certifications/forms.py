"""
Forms for certifications app — staff-side panel to manage CertificateTemplate.

B2 sub-feature: CertificateTemplateForm exposes all template fields so staff
users can create / edit a CertificateTemplate from the custom UI panel
(`/certificates/admin/templates/`).
"""

from django import forms

from .models import CertificateTemplate


class CertificateTemplateForm(forms.ModelForm):
    """Form for staff to create/edit a CertificateTemplate from the custom panel."""

    class Meta:
        model = CertificateTemplate
        fields = [
            "name",
            "description",
            "template_file",
            "background_image",
            "logo",
            "signature_image",
            "signer_name",
            "signer_title",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "required": True}
            ),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 2}
            ),
            "template_file": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered w-full",
                    "accept": ".html",
                }
            ),
            "background_image": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered w-full",
                    "accept": "image/*",
                }
            ),
            "logo": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered w-full",
                    "accept": "image/*",
                }
            ),
            "signature_image": forms.ClearableFileInput(
                attrs={
                    "class": "file-input file-input-bordered w-full",
                    "accept": "image/*",
                }
            ),
            "signer_name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "signer_title": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
        }
