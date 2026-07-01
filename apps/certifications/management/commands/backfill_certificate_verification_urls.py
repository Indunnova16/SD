"""
Backfill verification_url on legacy Certificate rows that were generated
before SD#43's fix, so they used the hardcoded broken domain+path
(``https://lms.sd.com.co/certificates/verify/<num>/``) instead of the real
service URL and the ``/certifications/verify/`` path
(``config/settings/cloudrun.py`` SITE_URL + ``apps/certifications/services.py``).

Read-only by default (``--dry-run`` behavior is the default): prints what
WOULD change. Pass ``--apply`` to actually write to the database.

This command touches production data and must be run manually, with
authorization, AFTER the SD#43 fix is deployed:

    python manage.py backfill_certificate_verification_urls --apply
"""

from django.core.management.base import BaseCommand

from apps.certifications.models import Certificate

LEGACY_DOMAIN = "lms.sd.com.co"
LEGACY_PATH_SEGMENT = "/certificates/verify/"
CORRECT_PATH_SEGMENT = "/certifications/verify/"


class Command(BaseCommand):
    help = (
        "Backfill Certificate.verification_url for rows still pointing at the "
        "legacy broken domain (lms.sd.com.co) and/or the wrong path segment "
        "(/certificates/verify/ instead of /certifications/verify/). SD#43."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="https://sd-lms-rvfp6uj2va-uc.a.run.app",
            help="Base URL to rebuild verification_url with (default: prod Cloud Run URL).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the changes. Without this flag, only previews them.",
        )

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        apply_changes = options["apply"]

        affected = Certificate.objects.filter(verification_url__icontains=LEGACY_DOMAIN)
        count = affected.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No certificates with the legacy domain found."))
            return

        self.stdout.write(f"Found {count} certificate(s) with legacy verification_url:")

        updated = 0
        for cert in affected:
            new_url = f"{base_url}{CORRECT_PATH_SEGMENT}{cert.certificate_number}/"
            self.stdout.write(
                f"  id={cert.id} certificate_number={cert.certificate_number} "
                f"old={cert.verification_url!r} -> new={new_url!r}"
            )
            if apply_changes:
                cert.verification_url = new_url
                cert.save(update_fields=["verification_url"])
                updated += 1

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"\nUpdated {updated} certificate(s)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry-run only, no changes written. Re-run with --apply to "
                    f"update these {count} certificate(s)."
                )
            )
