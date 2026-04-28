# Generated migration: Add job_profile as ForeignKey to JobProfileType

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0013_add_coordinator_viz_profile"),
        ("accounts", "0009_rename_job_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="job_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="courses.jobprofiletype",
                verbose_name="Perfil ocupacional",
            ),
        ),
    ]
