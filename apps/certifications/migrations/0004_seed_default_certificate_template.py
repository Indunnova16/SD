"""
Data migration: seed 1 active CertificateTemplate with the client's real
logo (SD#59, sub-item A2).

BD prod confirms 0 rows in `certificate_templates` (not just none active) ->
CertificateService.issue_certificate() never finds an `is_active=True`
template, so every certificate falls back to the "SD" text logo-fallback in
certificate_template.html. This migration seeds exactly one is_active=True
CertificateTemplate with the real client logo (issue #59 attachment
att_03.png, copied to apps/certifications/migrations/assets/sd_sas_logo.png,
MD5 fda0eb21a8e7bb8737b82fe44389f03b).

`template_file` is left blank (optional since migration 0003) --
CertificateService._generate_pdf therefore keeps rendering the default
certificate_template.html (the same file fixed by A1/A3), but now that
`template` resolves to a real (non-None) instance, the template's
`{% if template and template.logo %}` block renders the real logo instead
of the "SD" text fallback.

Idempotent: no-ops if ANY active template already exists (covers a template
created manually between the prod check and this deploy) and get_or_create
by name otherwise (safe to re-run / re-apply in any env).
"""

import os

from django.db import migrations

TEMPLATE_NAME = "Plantilla oficial S.D. S.A.S."
ASSET_FILENAME = "sd_sas_logo.png"


def seed_default_template(apps, schema_editor):
    CertificateTemplate = apps.get_model("certifications", "CertificateTemplate")

    if CertificateTemplate.objects.filter(is_active=True).exists():
        return

    template, created = CertificateTemplate.objects.get_or_create(
        name=TEMPLATE_NAME,
        defaults={
            "description": (
                "Plantilla por defecto sembrada por SD#59 (A2) con el logo "
                "real del cliente. Sin template_file: usa la plantilla HTML "
                "por defecto del sistema (certificate_template.html)."
            ),
            "is_active": True,
        },
    )
    if not created or template.logo:
        return

    asset_path = os.path.join(os.path.dirname(__file__), "assets", ASSET_FILENAME)
    if not os.path.exists(asset_path):
        # Defensive: never crash a deploy's `migrate` step over a missing
        # asset file -- the template still gets created (usable, just
        # without the logo) and can be fixed up later via /admin/.
        return

    from django.core.files.base import ContentFile

    with open(asset_path, "rb") as f:
        template.logo.save(ASSET_FILENAME, ContentFile(f.read()), save=True)


def reverse_seed(apps, schema_editor):
    CertificateTemplate = apps.get_model("certifications", "CertificateTemplate")
    CertificateTemplate.objects.filter(name=TEMPLATE_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("certifications", "0003_alter_certificatetemplate_template_file_optional"),
    ]

    operations = [
        migrations.RunPython(seed_default_template, reverse_seed),
    ]
