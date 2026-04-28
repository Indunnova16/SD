# Generated migration: Rename job_profile to _job_profile_old

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_set_admin_is_staff"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="job_profile",
            new_name="_job_profile_old",
        ),
    ]
