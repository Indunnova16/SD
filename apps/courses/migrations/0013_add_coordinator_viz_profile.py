"""
Data migration to add missing COORDINADOR_VIZ profile.
"""

from django.db import migrations


def add_coordinator_viz(apps, schema_editor):
    JobProfileType = apps.get_model("courses", "JobProfileType")
    JobProfileType.objects.get_or_create(
        code="COORDINADOR_VIZ",
        defaults={
            "name": "Coordinador (Solo Visualización)",
            "description": "Coordinador con permisos de solo visualización",
            "order": 8,
        },
    )


def remove_coordinator_viz(apps, schema_editor):
    JobProfileType = apps.get_model("courses", "JobProfileType")
    JobProfileType.objects.filter(code="COORDINADOR_VIZ").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0012_add_course_styling_and_module_image"),
    ]

    operations = [
        migrations.RunPython(add_coordinator_viz, remove_coordinator_viz),
    ]
