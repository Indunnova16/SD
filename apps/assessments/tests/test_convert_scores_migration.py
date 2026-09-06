"""Tests for the SD#121 A2 historical score data migration."""

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps as django_apps
from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import Assessment, AssessmentAttempt

MIGRATION = importlib.import_module("apps.assessments.migrations.0009_convert_scores_data")


class ConvertScoresDataMigrationTests(TestCase):
    """Run the actual RunPython functions against legacy ORM rows."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="a2_convert_scores_migration@test.com",
            password="testpass123",
            first_name="A2",
            last_name="Migration",
            document_type="CC",
            document_number="1210001",
            job_position="Tech",
            hire_date=date(2024, 1, 1),
        )
        cls.assessment = Assessment.objects.create(
            title="Evaluación legacy A2",
            created_by=cls.user,
            # This is deliberately a pre-A1 persisted value.
            passing_score=Decimal("80.00"),
        )
        cls.attempt = AssessmentAttempt.objects.create(
            user=cls.user,
            assessment=cls.assessment,
            score=Decimal("64.50"),
        )
        cls.ungraded_attempt = AssessmentAttempt.objects.create(
            user=cls.user,
            assessment=cls.assessment,
            attempt_number=2,
            score=None,
        )

    def test_forward_converts_legacy_values_and_skips_null(self):
        MIGRATION.convert_forward(django_apps, None)

        self.assessment.refresh_from_db()
        self.attempt.refresh_from_db()
        self.ungraded_attempt.refresh_from_db()

        self.assertEqual(self.assessment.passing_score, Decimal("4.00"))
        # 64.50 / 20 = 3.225; default ROUND_HALF_EVEN quantizes to 3.22.
        self.assertEqual(self.attempt.score, Decimal("3.22"))
        self.assertIsNone(self.ungraded_attempt.score)

    def test_backward_restores_values_with_rounding_tolerance(self):
        MIGRATION.convert_forward(django_apps, None)
        MIGRATION.convert_backward(django_apps, None)

        self.assessment.refresh_from_db()
        self.attempt.refresh_from_db()

        self.assertEqual(self.assessment.passing_score, Decimal("80.00"))
        # The mandatory two-decimal HALF_EVEN quantization loses 0.005 on the
        # forward conversion, so 3.22 * 20 = 64.40 (a 0.10 difference).
        self.assertEqual(self.attempt.score, Decimal("64.40"))
