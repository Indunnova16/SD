from decimal import Decimal

from django.test import SimpleTestCase

from apps.courses.forms import AssessmentEditForm, QuickAssessmentForm


class PassingScoreRangeA5Tests(SimpleTestCase):
    def _quick_data(self, value):
        return {
            "title": "Evaluación",
            "assessment_type": "quiz",
            "passing_score": str(value),
            "max_attempts": "0",
        }

    def _edit_data(self, value):
        return {
            "title": "Evaluación",
            "description": "",
            "assessment_type": "quiz",
            "passing_score": str(value),
            "time_limit": "",
            "max_attempts": "0",
            "status": "draft",
        }

    def test_quick_form_accepts_3_50_and_rejects_outside_range(self):
        valid = QuickAssessmentForm(data=self._quick_data(Decimal("3.50")))
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data["passing_score"], Decimal("3.50"))
        for value in (Decimal("5.01"), Decimal("-0.01")):
            self.assertFalse(QuickAssessmentForm(data=self._quick_data(value)).is_valid())

    def test_edit_form_accepts_3_50_and_rejects_outside_range(self):
        valid = AssessmentEditForm(data=self._edit_data(Decimal("3.50")))
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data["passing_score"], Decimal("3.50"))
        for value in (Decimal("5.01"), Decimal("-0.01")):
            self.assertFalse(AssessmentEditForm(data=self._edit_data(value)).is_valid())
