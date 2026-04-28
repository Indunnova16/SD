# Generated migration to add signature fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0013_add_coordinator_viz_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="lessonevidence",
            name="signature",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="lesson_evidences/signatures/%Y/%m/",
                verbose_name="Firma",
            ),
        ),
        migrations.AddField(
            model_name="lessonevidence",
            name="signed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Fecha de firma"),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="completion_signature",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="enrollments/signatures/%Y/%m/",
                verbose_name="Firma de finalización",
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="completion_signed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Fecha de firma de finalización"
            ),
        ),
    ]
