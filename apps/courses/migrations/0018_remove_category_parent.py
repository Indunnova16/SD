from django.db import migrations


def remove_subcategories(apps, schema_editor):
    """Re-parent any courses under subcategories to the top-level parent,
    then delete the subcategory rows. In production there are 0 courses under
    subcategories, so this is a clean delete of the 4 existing subcategories.
    """
    Category = apps.get_model("courses", "Category")
    Course = apps.get_model("courses", "Course")

    subcategories = Category.objects.filter(parent__isnull=False)
    for sub in subcategories:
        if sub.parent_id:
            Course.objects.filter(category=sub).update(category=sub.parent_id)

    # Delete subcategories (parent IS NOT NULL).
    subcategories.delete()


def noop_reverse(apps, schema_editor):
    """Removal of subcategories is not reversible (no data of value)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0017_lesson_scheduled_date"),
    ]

    # Solo la limpieza de datos (DELETE de subcategorías). El RemoveField del
    # campo `parent` va en una migración separada (0020) para que el DELETE
    # commitee y se resuelvan sus trigger events de FK antes del ALTER TABLE.
    # Si van juntos en la misma transacción, Postgres lanza:
    #   "cannot ALTER TABLE because it has pending trigger events".
    operations = [
        migrations.RunPython(remove_subcategories, noop_reverse),
    ]
