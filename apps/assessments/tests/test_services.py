"""
Tests for assessment services.
"""

import json
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import (
    Answer,
    Assessment,
    AssessmentAttempt,
    Question,
)
from apps.assessments.services import AssessmentService, QuestionBankService
from apps.courses.models import Course


class AssessmentServiceTest(TestCase):
    """Tests for AssessmentService."""

    def setUp(self):
        """Set up test data."""
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="123456789",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user@test.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="987654321",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )

        # Create course
        self.course = Course.objects.create(
            code="TEST-001",
            title="Test Course",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )

        # Create assessment
        self.assessment = Assessment.objects.create(
            title="Test Assessment",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=3.5,
            max_attempts=3,
            time_limit=30,
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )

        # Create questions
        self.q1 = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="What is 2+2?",
            points=10,
            order=1,
        )
        self.q1_a1 = Answer.objects.create(question=self.q1, text="3", is_correct=False, order=1)
        self.q1_a2 = Answer.objects.create(question=self.q1, text="4", is_correct=True, order=2)
        self.q1_a3 = Answer.objects.create(question=self.q1, text="5", is_correct=False, order=3)

        self.q2 = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.MULTIPLE_CHOICE,
            text="Select prime numbers",
            points=10,
            order=2,
        )
        self.q2_a1 = Answer.objects.create(question=self.q2, text="2", is_correct=True, order=1)
        self.q2_a2 = Answer.objects.create(question=self.q2, text="3", is_correct=True, order=2)
        self.q2_a3 = Answer.objects.create(question=self.q2, text="4", is_correct=False, order=3)

        self.q3 = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.TRUE_FALSE,
            text="The sky is blue",
            points=5,
            order=3,
        )
        self.q3_true = Answer.objects.create(
            question=self.q3, text="True", is_correct=True, order=1
        )
        self.q3_false = Answer.objects.create(
            question=self.q3, text="False", is_correct=False, order=2
        )

    def test_can_start_attempt(self):
        """Test checking if user can start an attempt."""
        result = AssessmentService.can_start_attempt(self.user, self.assessment)

        self.assertTrue(result["can_start"])
        self.assertIsNone(result["reason"])
        self.assertIsNone(result["last_attempt"])

    def test_cannot_start_unpublished(self):
        """Test cannot start unpublished assessment."""
        self.assessment.status = Assessment.Status.DRAFT
        self.assessment.save()

        result = AssessmentService.can_start_attempt(self.user, self.assessment)

        self.assertFalse(result["can_start"])
        self.assertEqual(result["reason"], "La evaluación no está publicada")

    def test_cannot_start_with_no_questions(self):
        """Test cannot start assessment with no questions."""
        empty_assessment = Assessment.objects.create(
            title="Empty Assessment",
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )

        result = AssessmentService.can_start_attempt(self.user, empty_assessment)

        self.assertFalse(result["can_start"])
        self.assertEqual(result["reason"], "La evaluación no tiene preguntas")

    def test_cannot_exceed_max_attempts(self):
        """Test cannot exceed maximum attempts."""
        # Create max attempts
        for i in range(3):
            attempt = AssessmentAttempt.objects.create(
                user=self.user,
                assessment=self.assessment,
                attempt_number=i + 1,
                status=AssessmentAttempt.Status.GRADED,
            )

        result = AssessmentService.can_start_attempt(self.user, self.assessment)

        self.assertFalse(result["can_start"])
        self.assertIn("máximo", result["reason"])

    def test_start_attempt(self):
        """Test starting an assessment attempt."""
        attempt = AssessmentService.start_attempt(
            user=self.user,
            assessment=self.assessment,
            ip_address="127.0.0.1",
        )

        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.assessment, self.assessment)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, AssessmentAttempt.Status.IN_PROGRESS)

    def test_start_second_attempt(self):
        """Test starting a second attempt."""
        # First attempt
        first = AssessmentService.start_attempt(self.user, self.assessment)
        AssessmentService.submit_attempt(first)

        # Second attempt
        second = AssessmentService.start_attempt(self.user, self.assessment)

        self.assertEqual(second.attempt_number, 2)

    def test_submit_single_choice_answer(self):
        """Test submitting a single choice answer."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=self.q1,
            selected_answer_ids=[self.q1_a2.id],  # Correct answer
        )

        self.assertIsNotNone(answer)
        self.assertTrue(answer.is_correct)
        self.assertEqual(answer.points_awarded, 10)

    def test_submit_wrong_answer(self):
        """Test submitting a wrong answer."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=self.q1,
            selected_answer_ids=[self.q1_a1.id],  # Wrong answer
        )

        self.assertFalse(answer.is_correct)
        self.assertEqual(answer.points_awarded, 0)

    def test_submit_multiple_choice_answer(self):
        """Test submitting multiple choice answer."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        # Correct: select both 2 and 3
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=self.q2,
            selected_answer_ids=[self.q2_a1.id, self.q2_a2.id],
        )

        self.assertTrue(answer.is_correct)
        self.assertEqual(answer.points_awarded, 10)

    def test_submit_partial_multiple_choice(self):
        """Test partial answer for multiple choice is wrong."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        # Only select one correct answer
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=self.q2,
            selected_answer_ids=[self.q2_a1.id],
        )

        # Partial is still wrong
        self.assertFalse(answer.is_correct)

    def test_submit_attempt(self):
        """Test submitting an attempt."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        # Submit all answers correctly
        AssessmentService.submit_answer(attempt, self.q1, [self.q1_a2.id])
        AssessmentService.submit_answer(attempt, self.q2, [self.q2_a1.id, self.q2_a2.id])
        AssessmentService.submit_answer(attempt, self.q3, [self.q3_true.id])

        submitted = AssessmentService.submit_attempt(attempt)

        self.assertEqual(submitted.status, AssessmentAttempt.Status.GRADED)
        self.assertEqual(submitted.score, 5)
        self.assertTrue(submitted.passed)

    def test_submit_attempt_fail(self):
        """Test failing an attempt."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)

        # Submit all wrong answers
        AssessmentService.submit_answer(attempt, self.q1, [self.q1_a1.id])
        AssessmentService.submit_answer(attempt, self.q2, [self.q2_a3.id])
        AssessmentService.submit_answer(attempt, self.q3, [self.q3_false.id])

        submitted = AssessmentService.submit_attempt(attempt)

        self.assertEqual(submitted.score, 0)
        self.assertFalse(submitted.passed)

    def test_get_attempt_results(self):
        """Test getting attempt results."""
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        AssessmentService.submit_answer(attempt, self.q1, [self.q1_a2.id])
        AssessmentService.submit_answer(attempt, self.q2, [self.q2_a1.id, self.q2_a2.id])
        AssessmentService.submit_answer(attempt, self.q3, [self.q3_true.id])
        AssessmentService.submit_attempt(attempt)

        results = AssessmentService.get_attempt_results(attempt)

        self.assertEqual(results["score"], 5)
        self.assertTrue(results["passed"])
        self.assertEqual(len(results["questions"]), 3)

    def test_get_assessment_statistics(self):
        """Test getting assessment statistics."""
        # Create some attempts
        for i in range(3):
            user = User.objects.create_user(
                email=f"user{i}@test.com",
                password="testpass123",
                first_name=f"User{i}",
                last_name="Test",
                document_number=f"10000000{i}",
                job_position="Technician",
                hire_date=date(2021, 1, 1),
            )
            attempt = AssessmentService.start_attempt(user, self.assessment)
            AssessmentService.submit_answer(attempt, self.q1, [self.q1_a2.id])
            AssessmentService.submit_answer(attempt, self.q2, [self.q2_a1.id, self.q2_a2.id])
            AssessmentService.submit_answer(attempt, self.q3, [self.q3_true.id])
            AssessmentService.submit_attempt(attempt)

        stats = AssessmentService.get_assessment_statistics(self.assessment)

        self.assertEqual(stats["total_attempts"], 3)
        self.assertEqual(stats["average_score"], 5)
        self.assertEqual(stats["pass_rate"], 100)

    def test_submit_short_answer_no_autograde(self):
        """Short answer questions are NOT auto-graded; remain pending manual grading."""
        q_short = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SHORT_ANSWER,
            text="Describe X",
            points=5,
            order=4,
        )
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=q_short,
            text_answer="Mi respuesta",
        )
        self.assertEqual(answer.text_answer, "Mi respuesta")
        self.assertIsNone(answer.is_correct)
        self.assertIsNone(answer.points_awarded)

    def test_submit_essay_no_autograde(self):
        """Essay questions are NOT auto-graded; remain pending manual grading."""
        q_essay = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.ESSAY,
            text="Explica",
            points=20,
            order=5,
        )
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=q_essay,
            text_answer="Mi ensayo largo",
        )
        self.assertEqual(answer.text_answer, "Mi ensayo largo")
        self.assertIsNone(answer.is_correct)
        self.assertIsNone(answer.points_awarded)

    def test_manual_grade_essay(self):
        """Essay can be manually graded via grade_essay_answer."""
        q_essay = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.ESSAY,
            text="Explica",
            points=20,
            order=5,
        )
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=q_essay,
            text_answer="Mi ensayo",
        )
        graded = AssessmentService.grade_essay_answer(
            answer,
            points=Decimal("15"),
            feedback="Buen trabajo",
            grader=self.admin,
        )
        self.assertEqual(graded.points_awarded, Decimal("15"))
        # 15 < 20 (max points), por lo tanto NO es full puntos => is_correct False
        self.assertFalse(graded.is_correct)

    def test_submit_matching_answer(self):
        """Matching questions grade against metadata pairs."""
        q_match = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.MATCHING,
            text="Empareja",
            points=10,
            order=6,
            metadata={
                "match_pairs": [
                    {"left": "A", "right": "1"},
                    {"left": "B", "right": "2"},
                ]
            },
        )
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        user_pairs = json.dumps([{"left": "A", "right": "1"}, {"left": "B", "right": "2"}])
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=q_match,
            text_answer=user_pairs,
        )
        self.assertTrue(answer.is_correct)
        self.assertEqual(answer.points_awarded, 10)

    def test_submit_matching_wrong(self):
        """Matching with wrong pairing is incorrect."""
        q_match = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.MATCHING,
            text="Empareja",
            points=10,
            order=6,
            metadata={
                "match_pairs": [
                    {"left": "A", "right": "1"},
                    {"left": "B", "right": "2"},
                ]
            },
        )
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        user_pairs = json.dumps([{"left": "A", "right": "2"}, {"left": "B", "right": "1"}])
        answer = AssessmentService.submit_answer(
            attempt=attempt,
            question=q_match,
            text_answer=user_pairs,
        )
        self.assertFalse(answer.is_correct)
        self.assertEqual(answer.points_awarded, 0)


class QuestionBankServiceTest(TestCase):
    """Tests for QuestionBankService."""

    def setUp(self):
        """Set up test data."""
        self.admin = User.objects.create_user(
            email="admin2@test.com",
            password="testpass123",
            first_name="Admin2",
            last_name="User",
            document_number="222222222",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
        )

        self.assessment = Assessment.objects.create(
            title="Test Assessment",
            status=Assessment.Status.DRAFT,
            created_by=self.admin,
        )

        self.question = Question.objects.create(
            assessment=self.assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text="Test question",
            points=10,
        )
        Answer.objects.create(question=self.question, text="A", is_correct=True)
        Answer.objects.create(question=self.question, text="B", is_correct=False)

    def test_duplicate_question(self):
        """Test duplicating a question."""
        new_question = QuestionBankService.duplicate_question(self.question)

        self.assertNotEqual(new_question.id, self.question.id)
        self.assertEqual(new_question.text, self.question.text)
        self.assertEqual(new_question.answers.count(), 2)

    def test_duplicate_to_different_assessment(self):
        """Test duplicating to different assessment."""
        other_assessment = Assessment.objects.create(
            title="Other Assessment",
            created_by=self.admin,
        )

        new_question = QuestionBankService.duplicate_question(self.question, other_assessment)

        self.assertEqual(new_question.assessment, other_assessment)

    def test_validate_question_valid(self):
        """Test validating a valid question."""
        result = QuestionBankService.validate_question(self.question)

        self.assertTrue(result["is_valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_question_no_correct_answer(self):
        """Test validation fails with no correct answer."""
        self.question.answers.all().update(is_correct=False)

        result = QuestionBankService.validate_question(self.question)

        self.assertFalse(result["is_valid"])
        self.assertIn("no tiene respuesta correcta", result["errors"][0])

    def test_validate_assessment(self):
        """Test validating an assessment."""
        result = QuestionBankService.validate_assessment(self.assessment)

        self.assertTrue(result["is_valid"])

    def test_validate_empty_assessment(self):
        """Test validation fails for empty assessment."""
        empty = Assessment.objects.create(
            title="Empty",
            created_by=self.admin,
        )

        result = QuestionBankService.validate_assessment(empty)

        self.assertFalse(result["is_valid"])
        self.assertIn("no tiene preguntas", result["errors"][0])

    def test_validate_assessment_rejects_passing_score_above_five(self):
        """Passing scores above the 0-5 scale are invalid."""
        self.assessment.passing_score = Decimal("5.01")

        result = QuestionBankService.validate_assessment(self.assessment)

        self.assertFalse(result["is_valid"])
        self.assertIn("mayor a 5", result["errors"][0])

    def test_validate_assessment_accepts_passing_score_at_scale_limit(self):
        """Passing scores at or below 5 remain valid."""
        self.assessment.passing_score = Decimal("5.00")

        result = QuestionBankService.validate_assessment(self.assessment)

        self.assertTrue(result["is_valid"])


class ScaleFiveScoringTest(TestCase):
    """Tests for individual score calculations on the 0-5 scale."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="scale5-admin@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="Scale",
            document_number="5000001",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="scale5-user@test.com",
            password="testpass123",
            first_name="Test",
            last_name="Scale",
            document_number="5000002",
            job_position="Technician",
            hire_date=date(2021, 1, 1),
        )
        self.course = Course.objects.create(
            code="SCALE-5",
            title="Scale Five Course",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.assessment = Assessment.objects.create(
            title="Scale Five Assessment",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=Decimal("2.50"),
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )
        self.questions = []
        self.correct_answers = []
        for order in (1, 2):
            question = Question.objects.create(
                assessment=self.assessment,
                question_type=Question.Type.SINGLE_CHOICE,
                text=f"Question {order}",
                points=Decimal("1.00"),
                order=order,
            )
            correct = Answer.objects.create(
                question=question,
                text="Correct",
                is_correct=True,
                order=1,
            )
            Answer.objects.create(question=question, text="Wrong", is_correct=False, order=2)
            self.questions.append(question)
            self.correct_answers.append(correct)

    def _attempt_with_answers(self, correct_count):
        attempt = AssessmentService.start_attempt(self.user, self.assessment)
        for index, question in enumerate(self.questions):
            selected = [self.correct_answers[index].id] if index < correct_count else []
            AssessmentService.submit_answer(attempt, question, selected_answer_ids=selected)
        return attempt

    def test_grade_attempt_perfect_score_is_five(self):
        """Two correct answers out of two produce 5.00."""
        attempt = self._attempt_with_answers(2)

        AssessmentService.grade_attempt(attempt)

        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("5.00"))

    def test_auto_grade_attempt_half_score_is_two_and_a_half(self):
        """One correct answer out of two produces 2.50."""
        attempt = self._attempt_with_answers(1)

        AssessmentService.auto_grade_attempt(attempt)

        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("2.50"))

    def test_calculate_score_half_score_is_two_and_a_half(self):
        """Recalculation uses the same 0-5 scale."""
        attempt = self._attempt_with_answers(1)

        AssessmentService.calculate_score(attempt)

        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("2.50"))


class DecimalScoringTest(TestCase):
    """Tests for decimal points / scoring support (issue #39).

    Covers: decimal points per question, score quantization to 2 dp,
    passing borderline, total_points=0 edge case, mixed grading, and a
    legacy-style integer-points assessment that must still grade correctly.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin39@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="3900001",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user39@test.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="3900002",
            job_position="Technician",
            hire_date=date(2021, 6, 15),
        )
        self.course = Course.objects.create(
            code="DEC-001",
            title="Decimal Course",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )

    def _assessment(self, passing_score):
        return Assessment.objects.create(
            title="Decimal Assessment",
            assessment_type=Assessment.Type.QUIZ,
            course=self.course,
            passing_score=passing_score,
            max_attempts=3,
            status=Assessment.Status.PUBLISHED,
            created_by=self.admin,
        )

    def _single_choice(self, assessment, points, order, correct_text="A"):
        q = Question.objects.create(
            assessment=assessment,
            question_type=Question.Type.SINGLE_CHOICE,
            text=f"Q{order}",
            points=points,
            order=order,
        )
        a_ok = Answer.objects.create(question=q, text=correct_text, is_correct=True, order=1)
        Answer.objects.create(question=q, text="B", is_correct=False, order=2)
        return q, a_ok

    def test_question_points_accept_decimal(self):
        """Question.points persists a decimal like 4.5."""
        a = self._assessment(Decimal("80.00"))
        q, _ = self._single_choice(a, Decimal("4.5"), 1)
        q.refresh_from_db()
        self.assertEqual(q.points, Decimal("4.50"))

    def test_total_points_is_decimal_sum(self):
        """total_points sums decimal points (4.5 + 3.8 = 8.3)."""
        a = self._assessment(Decimal("80.00"))
        self._single_choice(a, Decimal("4.5"), 1)
        self._single_choice(a, Decimal("3.8"), 2)
        self.assertEqual(a.total_points, Decimal("8.30"))

    def test_grade_attempt_decimal_score_quantized(self):
        """Score is computed from decimal points and quantized to 2 dp."""
        a = self._assessment(Decimal("3.75"))
        q1, a1_ok = self._single_choice(a, Decimal("4.5"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("3.8"), 2)  # noqa: F841
        attempt = AssessmentService.start_attempt(self.user, a)
        # Answer only q1 correctly -> 4.5 / 8.3 * 100 = 54.21...
        AssessmentService.submit_answer(attempt, q1, selected_answer_ids=[a1_ok.id])
        AssessmentService.submit_answer(attempt, q2, selected_answer_ids=[])
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.points_earned, Decimal("4.50"))
        self.assertEqual(attempt.score, Decimal("2.71"))
        self.assertEqual(attempt.score.as_tuple().exponent, -2)
        self.assertFalse(attempt.passed)

    def test_passing_borderline_equal(self):
        """A score exactly equal to passing_score (decimal) passes."""
        a = self._assessment(Decimal("2.50"))
        q1, a1_ok = self._single_choice(a, Decimal("5.0"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("5.0"), 2)
        attempt = AssessmentService.start_attempt(self.user, a)
        AssessmentService.submit_answer(attempt, q1, selected_answer_ids=[a1_ok.id])
        AssessmentService.submit_answer(attempt, q2, selected_answer_ids=[])
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("2.50"))
        self.assertTrue(attempt.passed)

    def test_passing_decimal_threshold(self):
        """A score just below a decimal passing threshold does not pass."""
        a = self._assessment(Decimal("3.80"))
        q1, a1_ok = self._single_choice(a, Decimal("75.0"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("25.0"), 2)
        attempt = AssessmentService.start_attempt(self.user, a)
        AssessmentService.submit_answer(attempt, q1, selected_answer_ids=[a1_ok.id])
        AssessmentService.submit_answer(attempt, q2, selected_answer_ids=[])
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        # 75 / 100 * 5 = 3.75 < 3.80 -> not passed.
        self.assertEqual(attempt.score, Decimal("3.75"))
        self.assertFalse(attempt.passed)

    def test_grade_attempt_total_points_zero(self):
        """Edge case: assessment with no points -> score 0, not passed."""
        a = self._assessment(Decimal("80.00"))
        q = Question.objects.create(
            assessment=a,
            question_type=Question.Type.SINGLE_CHOICE,
            text="zero",
            points=Decimal("0.00"),
            order=1,
        )
        Answer.objects.create(question=q, text="A", is_correct=True, order=1)
        Answer.objects.create(question=q, text="B", is_correct=False, order=2)
        attempt = AssessmentService.start_attempt(self.user, a)
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, Decimal("0.00"))
        self.assertEqual(attempt.points_earned, Decimal("0.00"))
        self.assertFalse(attempt.passed)

    def test_perfect_score_high_decimals(self):
        """A perfect attempt yields exactly 100.00 (no float drift)."""
        a = self._assessment(Decimal("4.50"))
        q1, a1_ok = self._single_choice(a, Decimal("33.33"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("33.33"), 2)
        q3, a3_ok = self._single_choice(a, Decimal("33.34"), 3)
        attempt = AssessmentService.start_attempt(self.user, a)
        for q, ok in [(q1, a1_ok), (q2, a2_ok), (q3, a3_ok)]:
            AssessmentService.submit_answer(attempt, q, selected_answer_ids=[ok.id])
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.points_earned, Decimal("100.00"))
        self.assertEqual(attempt.score, Decimal("5.00"))
        self.assertTrue(attempt.passed)

    def test_grade_essay_answer_decimal(self):
        """Essay grading accepts a partial decimal award."""
        a = self._assessment(Decimal("50.00"))
        essay = Question.objects.create(
            assessment=a,
            question_type=Question.Type.ESSAY,
            text="Explain",
            points=Decimal("10.00"),
            order=1,
        )
        attempt = AssessmentService.start_attempt(self.user, a)
        ans = AssessmentService.submit_answer(attempt, essay, text_answer="my answer")
        AssessmentService.grade_essay_answer(ans, Decimal("7.5"), grader=self.admin)
        ans.refresh_from_db()
        self.assertEqual(ans.points_awarded, Decimal("7.5"))
        self.assertFalse(ans.is_correct)  # 7.5 != 10.00 max

    def test_grade_essay_rejects_over_max(self):
        """Essay award above the question max is rejected."""
        a = self._assessment(Decimal("50.00"))
        essay = Question.objects.create(
            assessment=a,
            question_type=Question.Type.ESSAY,
            text="Explain",
            points=Decimal("5.00"),
            order=1,
        )
        attempt = AssessmentService.start_attempt(self.user, a)
        ans = AssessmentService.submit_answer(attempt, essay, text_answer="x")
        with self.assertRaises(ValueError):
            AssessmentService.grade_essay_answer(ans, Decimal("5.5"))

    def test_legacy_integer_points_still_grade(self):
        """Legacy-style integer points must still produce a correct decimal score."""
        a = self._assessment(Decimal("3.00"))
        # Integer-valued points (as legacy rows would have post-migration: 10.00, 5.00)
        q1, a1_ok = self._single_choice(a, Decimal("10.00"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("5.00"), 2)
        attempt = AssessmentService.start_attempt(self.user, a)
        AssessmentService.submit_answer(attempt, q1, selected_answer_ids=[a1_ok.id])
        AssessmentService.submit_answer(attempt, q2, selected_answer_ids=[])
        AssessmentService.grade_attempt(attempt)
        attempt.refresh_from_db()
        # 10 / 15 * 5 = 3.33 -> passed (>= 3.00)
        self.assertEqual(attempt.score, Decimal("3.33"))
        self.assertTrue(attempt.passed)

    def test_auto_grade_attempt_decimal(self):
        """auto_grade_attempt accumulates decimal points correctly."""
        a = self._assessment(Decimal("2.50"))
        q1, a1_ok = self._single_choice(a, Decimal("2.5"), 1)
        q2, a2_ok = self._single_choice(a, Decimal("2.5"), 2)
        attempt = AssessmentService.start_attempt(self.user, a)
        AssessmentService.submit_answer(attempt, q1, selected_answer_ids=[a1_ok.id])
        AssessmentService.submit_answer(attempt, q2, selected_answer_ids=[a2_ok.id])
        AssessmentService.auto_grade_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.points_earned, Decimal("5.00"))
        self.assertEqual(attempt.score, Decimal("5.00"))
        self.assertTrue(attempt.passed)
