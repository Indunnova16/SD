# Data migration: Migrate job_profile string values to ForeignKey

from django.db import migrations


def migrate_job_profiles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    JobProfileType = apps.get_model("courses", "JobProfileType")

    for user in User.objects.all():
        if user._job_profile_old:
            try:
                profile = JobProfileType.objects.get(code=user._job_profile_old)
                user.job_profile = profile
                user.save(update_fields=["job_profile"])
            except JobProfileType.DoesNotExist:
                # If profile doesn't exist, try COORDINADOR_VIZ → COORDINADOR_VIZ mapping
                if user._job_profile_old == "COORDINADOR_VISUALIZACION":
                    try:
                        profile = JobProfileType.objects.get(code="COORDINADOR_VIZ")
                        user.job_profile = profile
                        user.save(update_fields=["job_profile"])
                    except JobProfileType.DoesNotExist:
                        # Fallback to LINIERO if mapping fails
                        profile = JobProfileType.objects.get(code="LINIERO")
                        user.job_profile = profile
                        user.save(update_fields=["job_profile"])
                else:
                    # Fallback to LINIERO if profile not found
                    profile = JobProfileType.objects.get(code="LINIERO")
                    user.job_profile = profile
                    user.save(update_fields=["job_profile"])


def reverse_migrate(apps, schema_editor):
    # Reverse is a no-op since we're keeping the old field for now
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_job_profile_fk"),
    ]

    operations = [
        migrations.RunPython(migrate_job_profiles, reverse_migrate),
    ]
