from django.db import migrations


class Migration(migrations.Migration):
    """Quita el campo self-ref `Category.parent` (concepto de subcategoría).

    Separada de 0018 (que hace el DELETE de las subcategorías) a propósito:
    el DELETE debe commitear y resolver sus trigger events de FK ANTES de
    este ALTER TABLE, o Postgres lanza
    "cannot ALTER TABLE because it has pending trigger events".
    Depende de 0019 para correr al final de la cadena de courses.
    """

    dependencies = [
        ("courses", "0019_alter_lesson_lesson_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="category",
            name="parent",
        ),
    ]
