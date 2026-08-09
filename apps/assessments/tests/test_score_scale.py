"""Tests for escala 0-5 de passing_score/score (SD#121, A1).

Sub-item A1 del sprint (`SD/SPRINTS/PLAN_2026-08-09_calificacion_0_5.md`):
`Assessment.passing_score` y `AssessmentAttempt.score` migran de escala 0-100
(porcentaje) a escala 0-5. Este archivo cubre SOLO el validator nuevo
(`validate_0_5_scale`) y el nuevo default/rango de `Assessment.passing_score`.
Los literales hardcodeados en otros archivos de test (80/80.00) son A9/A10,
fuera de scope acá.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.core.validators import validate_0_5_scale

_SEQ_ITER = iter(range(9_500_000, 9_999_999))


def _make_user(**overrides):
    n = next(_SEQ_ITER)
    defaults = {
        "email": f"a1_score_scale_user_{n}@test.com",
        "password": "testpass123",
        "first_name": "A1",
        "last_name": "ScoreScale",
        "document_type": "CC",
        "document_number": str(n),
        "job_position": "Tech",
        "hire_date": date(2024, 1, 1),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class ValidateZeroToFiveScaleTests(TestCase):
    """`validate_0_5_scale` — validador standalone (sin BD)."""

    def test_rechaza_valor_negativo(self):
        with self.assertRaises(ValidationError):
            validate_0_5_scale(-0.01)

    def test_rechaza_valor_mayor_a_cinco(self):
        with self.assertRaises(ValidationError):
            validate_0_5_scale(5.01)

    def test_acepta_cero(self):
        # No debe levantar ValidationError.
        validate_0_5_scale(0)

    def test_acepta_dos_punto_cinco(self):
        validate_0_5_scale(2.5)

    def test_acepta_cinco(self):
        validate_0_5_scale(5)


class AssessmentPassingScoreScaleTests(TestCase):
    """`Assessment.passing_score` — default y rango tras la migración a 0-5."""

    def setUp(self):
        self.creator = _make_user()

    def test_default_passing_score_es_tres_punto_cinco(self):
        assessment = Assessment.objects.create(
            title="Evaluación default score",
            created_by=self.creator,
        )
        self.assertEqual(assessment.passing_score, Decimal("3.50"))

    def test_passing_score_mayor_a_cinco_falla_full_clean(self):
        assessment = Assessment(
            title="Evaluación score inválido alto",
            created_by=self.creator,
            passing_score=Decimal("5.01"),
        )
        with self.assertRaises(ValidationError):
            assessment.full_clean()

    def test_passing_score_negativo_falla_full_clean(self):
        assessment = Assessment(
            title="Evaluación score inválido negativo",
            created_by=self.creator,
            passing_score=Decimal("-0.01"),
        )
        with self.assertRaises(ValidationError):
            assessment.full_clean()

    def test_passing_score_en_rango_valido_pasa_full_clean(self):
        assessment = Assessment(
            title="Evaluación score válido",
            created_by=self.creator,
            passing_score=Decimal("3.50"),
        )
        # No debe levantar ValidationError.
        assessment.full_clean()
