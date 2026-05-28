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
            passing_score=70,
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
        self.assertEqual(submitted.score, 100)
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

        self.assertEqual(results["score"], 100)
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
        self.assertEqual(stats["average_score"], 100)
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
        user_pairs = json.dumps(
            [{"left": "A", "right": "1"}, {"left": "B", "right": "2"}]
        )
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
        user_pairs = json.dumps(
            [{"left": "A", "right": "2"}, {"left": "B", "right": "1"}]
        )
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
