# Generated migration: Remove old _job_profile_old field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_migrate_job_profile_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="_job_profile_old",
        ),
    ]
