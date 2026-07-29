"""
Ronda 2 del portal de tickets (issue #71): adjuntos de audio/video + estado
resuelto.

Escrita a mano (no `makemigrations`) para que el cambio de `imagen` a
`archivo` sea un **RenameField** explícito y no un drop+create: en Postgres
eso es un `ALTER TABLE … RENAME COLUMN`, que preserva las filas que ya
existen en prod (el portal está deployado desde 2026-07-27 y ya tiene
tickets reales). Un `RemoveField` + `AddField` habría borrado esas rutas de
archivo en silencio.

`tipo` entra con `default="imagen"`, que es exacto para el histórico: v1.0
solo aceptaba imágenes (`services.py` exigía `content_type` `image/*`), así
que toda fila preexistente es una imagen.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0001_initial"),
    ]

    operations = [
        # --- FeedbackAttachment: imagen (ImageField) -> archivo (FileField) ---
        migrations.RenameField(
            model_name="feedbackattachment",
            old_name="imagen",
            new_name="archivo",
        ),
        migrations.AlterField(
            model_name="feedbackattachment",
            name="archivo",
            field=models.FileField(upload_to="feedback/adjuntos/%Y/%m/", verbose_name="Archivo"),
        ),
        migrations.AddField(
            model_name="feedbackattachment",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("imagen", "🖼 Imagen"),
                    ("audio", "🔊 Audio"),
                    ("video", "🎬 Video"),
                ],
                default="imagen",
                max_length=10,
                verbose_name="Tipo",
            ),
        ),
        migrations.AddField(
            model_name="feedbackattachment",
            name="mime_type",
            field=models.CharField(blank=True, max_length=120, verbose_name="MIME type"),
        ),
        # --- FeedbackTicket: estado resuelto ---
        migrations.AddField(
            model_name="feedbackticket",
            name="estado",
            field=models.CharField(
                choices=[("abierto", "🔵 Abierto"), ("resuelto", "🟢 Resuelto")],
                default="abierto",
                max_length=20,
                verbose_name="Estado",
            ),
        ),
        migrations.AddField(
            model_name="feedbackticket",
            name="resuelto_por",
            field=models.CharField(blank=True, max_length=120, verbose_name="Resuelto por"),
        ),
        migrations.AddField(
            model_name="feedbackticket",
            name="resuelto_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Resuelto el"),
        ),
    ]
