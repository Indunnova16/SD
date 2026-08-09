"""Convert legacy assessment scores from a 0-100 scale to a 0-5 scale."""

from decimal import Decimal

from django.db import migrations


def convert_forward(apps, schema_editor):
    """Convert all persisted scores proportionally, preserving null scores."""
    Assessment = apps.get_model("assessments", "Assessment")
    AssessmentAttempt = apps.get_model("assessments", "AssessmentAttempt")

    for assessment in Assessment.objects.all():
        assessment.passing_score = (
            assessment.passing_score / Decimal("20")
        ).quantize(Decimal("0.01"))
        assessment.save(update_fields=["passing_score"])

    for attempt in AssessmentAttempt.objects.exclude(score__isnull=True):
        attempt.score = (attempt.score / Decimal("20")).quantize(Decimal("0.01"))
        attempt.save(update_fields=["score"])


def convert_backward(apps, schema_editor):
    """Restore scores to the legacy 0-100 scale where precision permits."""
    Assessment = apps.get_model("assessments", "Assessment")
    AssessmentAttempt = apps.get_model("assessments", "AssessmentAttempt")

    for assessment in Assessment.objects.all():
        assessment.passing_score = (
            assessment.passing_score * Decimal("20")
        ).quantize(Decimal("0.01"))
        assessment.save(update_fields=["passing_score"])

    for attempt in AssessmentAttempt.objects.exclude(score__isnull=True):
        attempt.score = (attempt.score * Decimal("20")).quantize(Decimal("0.01"))
        attempt.save(update_fields=["score"])


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0008_alter_score_scale"),
    ]

    operations = [
        migrations.RunPython(convert_forward, convert_backward),
    ]
