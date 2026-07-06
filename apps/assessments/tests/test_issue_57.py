"""
Tests for SD#57 (assessments app side):
  - sub-item 2: Assessment.max_attempts default cambia de 3 a 0 (ilimitado).
  - sub-item 3: backfill de migracion 0007 deriva question.metadata['match_pairs']
    de los Answer YA CREADOS, para preguntas Emparejamiento legacy con metadata
    vacio (patron confirmado en BD prod: questions id=25, id=37).
"""

import importlib
from datetime import date

from django.apps import apps as django_apps
from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, Question


class MaxAttemptsDefaultIssue57Tests(TestCase):
    """SD#57.2: el default del modelo pasa de 3 a 0 (ilimitado)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin_sd57b@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="SD57B",
            document_number="57000011",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )

    def test_model_field_default_is_zero(self):
        field = Assessment._meta.get_field("max_attempts")
        self.assertEqual(field.default, 0)

    def test_new_assessment_without_explicit_max_attempts_is_unlimited(self):
        assessment = Assessment.objects.create(
            title="SD57 default check", created_by=self.admin
        )
        self.assertEqual(assessment.max_attempts, 0)


class BackfillMatchingMetadataMigrationIssue57Tests(TestCase):
    """SD#57.3: la migracion de datos 0007_backfill_matching_metadata deriva
    metadata['match_pairs'] de los Answer ya creados, para preguntas
    Emparejamiento legacy con metadata vacio -- SIN tocar attempt_answers ni
    assessment_attempts (decision explicita de Miguel: no re-calificar
    historicos)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin_sd57@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="SD57",
            document_number="57000010",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.assessment = Assessment.objects.create(
            title="SD57 legacy matching assessment",
            assessment_type=Assessment.Type.QUIZ,
            created_by=self.admin,
        )

    def _migration_module(self):
        return importlib.import_module(
            "apps.assessments.migrations.0007_backfill_matching_metadata"
        )

    def test_backfill_populates_metadata_from_existing_answers(self):
        """Reproduce el patron real de BD prod (questions id=25/id=37): pregunta
        matching con metadata={} pero Answer YA creados (text=left,
        feedback=right) -- el backfill debe derivar match_pairs de esos Answer."""
        question = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.MATCHING,
            text="SD57 legacy matching question",
            metadata={},
        )
        Answer.objects.create(question=question, text="q", feedback="w", is_correct=True, order=0)
        Answer.objects.create(question=question, text="w", feedback="q", is_correct=True, order=1)

        mod = self._migration_module()
        mod.backfill_matching_metadata(django_apps, None)

        question.refresh_from_db()
        self.assertEqual(
            question.metadata,
            {"match_pairs": [{"left": "q", "right": "w"}, {"left": "w", "right": "q"}]},
        )

    def test_backfill_skips_non_matching_and_already_populated_questions(self):
        """No debe tocar preguntas que no son matching, ni las que ya tienen
        metadata poblado (idempotente / no pisa datos existentes)."""
        single_choice = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="SD57 single choice (no matching)",
            metadata={},
        )
        already_populated = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.MATCHING,
            text="SD57 matching ya poblado (Ruta A)",
            metadata={"match_pairs": [{"left": "1", "right": "1"}]},
        )
        Answer.objects.create(
            question=already_populated, text="1", feedback="1", is_correct=True, order=0
        )

        mod = self._migration_module()
        mod.backfill_matching_metadata(django_apps, None)

        single_choice.refresh_from_db()
        already_populated.refresh_from_db()
        self.assertEqual(single_choice.metadata, {})
        self.assertEqual(
            already_populated.metadata, {"match_pairs": [{"left": "1", "right": "1"}]}
        )

    def test_backfill_does_not_touch_attempt_answers(self):
        """El backfill SOLO escribe Question.metadata -- no debe existir
        ninguna referencia a AttemptAnswer/AssessmentAttempt en el modulo de
        la migracion (decision explicita de Miguel: no re-calificar
        historicos ya guardados)."""
        mod = self._migration_module()
        import inspect

        source = inspect.getsource(mod)
        self.assertNotIn("AttemptAnswer", source)
        self.assertNotIn("AssessmentAttempt", source)
