"""
Data migration: fix the logo of the default CertificateTemplate (SD#59,
REPROCESO -- gap A of the 2026-07-13 client rebound).

Migration 0004 (commit ae06f22, 2026-07-10) seeded exactly one active
CertificateTemplate but with the WRONG attachment from the issue: it used
att_01.png (a full screenshot/mockup of a certificate, including browser
chrome, MD5 fda0eb21a8e7bb8737b82fe44389f03b) instead of the client's real
logo (an electrical tower icon + "SD S.A.S. Salomon Duran" text, att_04/05,
MD5 9148226dea74ef3fea2d7044e7d381a8). The 0004 commit message itself
mis-labeled the mockup's MD5 as "the real logo" -- both images were attached
to the same client comment and were never opened/compared visually before
deciding which one was the logo.

Confirmed in this round (F2) with the strongest evidence yet: pdfimages
extraction of the image ACTUALLY EMBEDDED in a real, already-issued
certificate in prod (id=51) matches the mockup pixel-for-pixel, not the
real logo.

This migration UPDATES (does not re-create) the row already seeded by 0004
-- looked up by name="Plantilla oficial S.D. S.A.S." (0004's TEMPLATE_NAME)
first, falling back to the single is_active=True row if the name ever
diverges. It replaces `logo` with a NEW asset file
(sd_sas_logo_v2_real.png -- deliberately a DIFFERENT filename than the
broken sd_sas_logo.png, so a post-deploy check on the stored filename can
mechanically tell "still broken" from "fixed" without ambiguity).

Idempotent: safe to re-run in any environment.
  - If the 0004 template row doesn't exist yet (fresh env, migrations run
    in order 0004 then 0005), 0004 already seeds the WRONG asset -- this
    migration then immediately corrects it in the same `migrate` run.
  - If the row already points at the NEW filename (re-run, or the fix was
    already applied), this is a no-op.
"""

import os

from django.db import migrations

TEMPLATE_NAME = "Plantilla oficial S.D. S.A.S."
NEW_ASSET_FILENAME = "sd_sas_logo_v2_real.png"
# Stem (no extension) used for the idempotency check below -- Django's
# default (non-overwriting) storage backend appends a random suffix BEFORE
# the extension when a file with the exact target name already exists
# (e.g. "sd_sas_logo_v2_real_XyZ123.png"), so matching the literal
# NEW_ASSET_FILENAME (with ".png") would never match on a re-run and this
# migration would keep re-saving a new copy on every call. Matching the
# stem catches both "exact name" and "name_<suffix>.png".
NEW_ASSET_STEM = "sd_sas_logo_v2_real"


def fix_template_logo(apps, schema_editor):
    CertificateTemplate = apps.get_model("certifications", "CertificateTemplate")

    template = CertificateTemplate.objects.filter(name=TEMPLATE_NAME).first()
    if template is None:
        # Fall back to the single active template if the name ever diverges
        # from what 0004 seeded (defensive -- should not happen in practice).
        template = CertificateTemplate.objects.filter(is_active=True).first()
    if template is None:
        # Nothing to fix (e.g. 0004's RunPython no-op'd because an active
        # template already existed from elsewhere) -- never crash `migrate`.
        return

    # Already fixed (re-run, or applied in a prior deploy) -- no-op.
    if template.logo and NEW_ASSET_STEM in template.logo.name:
        return

    asset_path = os.path.join(os.path.dirname(__file__), "assets", NEW_ASSET_FILENAME)
    if not os.path.exists(asset_path):
        # Defensive: never crash a deploy's `migrate` step over a missing
        # asset file -- fixable later via /admin/.
        return

    from django.core.files.base import ContentFile

    with open(asset_path, "rb") as f:
        template.logo.save(NEW_ASSET_FILENAME, ContentFile(f.read()), save=True)


def reverse_fix(apps, schema_editor):
    # Reversing would mean going back to the broken asset -- intentionally
    # a no-op (there is nothing safe/desirable to restore).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("certifications", "0004_seed_default_certificate_template"),
    ]

    operations = [
        migrations.RunPython(fix_template_logo, reverse_fix),
    ]
