"""Management command to ensure admin superuser exists."""

from datetime import date

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.courses.models import JobProfileType


class Command(BaseCommand):
    help = "Create or reset the admin superuser for SD LMS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset password if the user already exists",
        )

    def handle(self, *args, **options):
        email = "admin@sd-lms.com"
        document_number = "1234567890"
        password = "admin123"

        user = User.objects.filter(document_number=document_number).first()
        admin_profile = JobProfileType.objects.get(code="ADMINISTRADOR")

        if user is None:
            user = User.objects.create_superuser(
                email=email,
                password=password,
                first_name="Admin",
                last_name="SD LMS",
                document_type="CC",
                document_number=document_number,
                phone="+573001234567",
                job_position="Administrador del Sistema",
                job_profile=admin_profile,
                hire_date=date.today(),
            )
            self.stdout.write(self.style.SUCCESS(f"Superuser created: {document_number} / {email}"))
        else:
            # Ensure user is superuser and active
            changed = False
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True

            if options["reset_password"]:
                user.set_password(password)
                changed = True
                self.stdout.write(self.style.WARNING("Password reset to default."))

            if changed:
                user.save()
                self.stdout.write(self.style.SUCCESS("Admin user updated."))
            else:
                self.stdout.write(self.style.SUCCESS("Admin user already exists and is active."))

        self.stdout.write(f"  Login: {document_number} or {email}")
        self.stdout.write(f"  Password: {password}")
