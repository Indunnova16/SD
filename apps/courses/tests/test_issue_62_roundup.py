"""
Tests for SD#62 — `round_up_to_half(hours)` (apps/courses/utils.py).

The client requires duration_hours (Course/Module/LearningPath) to ALWAYS
round UP to the nearest 0.5 multiple — never a standard round(). This test
exercises the pure function directly, independent of the 3 model
call-sites (which are covered by test_issue_43.py, test_issue_62.py and
apps/learning_paths/tests/test_issue_62.py).
"""

from django.test import TestCase

from apps.courses.utils import round_up_to_half


class RoundUpToHalfTests(TestCase):
    def test_zero_stays_zero(self):
        self.assertEqual(round_up_to_half(0), 0.0)

    def test_small_fraction_rounds_up_to_half(self):
        # 0.1 -> ceil(0.2)/2 = 1/2 = 0.5
        self.assertEqual(round_up_to_half(0.1), 0.5)

    def test_third_rounds_up_to_half(self):
        # 0.3 -> ceil(0.6)/2 = 1/2 = 0.5 (mirrors 18 min = 0.3h, prod course id=63)
        self.assertEqual(round_up_to_half(0.3), 0.5)

    def test_above_one_rounds_up_to_next_half(self):
        # 1.1 -> ceil(2.2)/2 = 3/2 = 1.5
        self.assertEqual(round_up_to_half(1.1), 1.5)

    def test_two_thirds_rounds_up_to_next_half(self):
        # 1.6 -> ceil(3.2)/2 = 4/2 = 2.0 (mirrors 100 min = 1.6666...h)
        self.assertEqual(round_up_to_half(1.6), 2.0)

    def test_exact_half_multiple_is_unchanged(self):
        # 2.0 is already an exact 0.5 multiple -> stays 2.0, no over-rounding
        self.assertEqual(round_up_to_half(2.0), 2.0)
