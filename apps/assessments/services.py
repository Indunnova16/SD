"""
Business logic services for assessments.
"""

import logging
import random
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.assessments.models import (
    Answer,
    Assessment,
    AssessmentAttempt,
    AttemptAnswer,
    Question,
)

logger = logging.getLogger(__name__)


class AssessmentService:
    """Service for assessment operations."""

    @staticmethod
    def get_questions_for_attempt(
        assessment: Assessment,
        shuffle: bool = None,
    ) -> list:
        """
        Get questions for an assessment attempt, optionally shuffled.
        """
        questions = list(assessment.questions.all())

        if shuffle is None:
            shuffle = assessment.shuffle_questions

        if shuffle:
            random.shuffle(questions)

        return questions

    @staticmethod
    def get_answers_for_question(
        question: Question,
        shuffle: bool = None,
    ) -> list:
        """
        Get answers for a question, optionally shuffled.
        """
        answers = list(question.answers.all())

        if shuffle is None:
            shuffle = question.assessment.shuffle_answers

        # Don't shuffle for true/false or ordering questions
        if question.question_type in [Question.Type.TRUE_FALSE, Question.Type.ORDERING]:
            return answers

        if shuffle:
            random.shuffle(answers)

        return answers

    @staticmethod
    def can_start_attempt(user, assessment: Assessment) -> dict:
        """
        Check if user can start a new attempt.
        """
        result = {
            "can_start": True,
            "reason": None,
            "attempts_remaining": None,
            "last_attempt": None,
        }

        # Check if assessment is published
        if assessment.status != Assessment.Status.PUBLISHED:
            result["can_start"] = False
            result["reason"] = "La evaluación no está publicada"
            return result

        # Check if has questions
        if assessment.questions.count() == 0:
            result["can_start"] = False
            result["reason"] = "La evaluación no tiene preguntas"
            return result

        # Check existing attempts
        attempts = AssessmentAttempt.objects.filter(
            user=user,
            assessment=assessment,
        )

        # Check for in-progress attempt
        in_progress = attempts.filter(status=AssessmentAttempt.Status.IN_PROGRESS).first()
        if in_progress:
            result["can_start"] = False
            result["reason"] = "Ya tienes un intento en progreso"
            result["last_attempt"] = in_progress
            return result

        # Check max attempts (0 = unlimited)
        if assessment.max_attempts > 0:
            completed_attempts = attempts.exclude(
                status=AssessmentAttempt.Status.IN_PROGRESS
            ).count()

            if completed_attempts >= assessment.max_attempts:
                result["can_start"] = False
                result["reason"] = f"Has alcanzado el máximo de {assessment.max_attempts} intentos"
                result["attempts_remaining"] = 0
            else:
                result["attempts_remaining"] = assessment.max_attempts - completed_attempts

        # Get last attempt info
        result["last_attempt"] = attempts.order_by("-started_at").first()

        return result

    @staticmethod
    @transaction.atomic
    def start_attempt(
        user,
        assessment: Assessment,
        ip_address: str = None,
        user_agent: str = "",
    ) -> AssessmentAttempt:
        """
        Start a new assessment attempt.
        """
        # Check if can start
        check = AssessmentService.can_start_attempt(user, assessment)
        if not check["can_start"]:
            raise ValueError(check["reason"])

        # Calculate attempt number
        existing_count = AssessmentAttempt.objects.filter(
            user=user,
            assessment=assessment,
        ).count()

        attempt = AssessmentAttempt.objects.create(
            user=user,
            assessment=assessment,
            attempt_number=existing_count + 1,
            status=AssessmentAttempt.Status.IN_PROGRESS,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return attempt

    @staticmethod
    @transaction.atomic
    def submit_answer(
        attempt: AssessmentAttempt,
        question: Question,
        selected_answer_ids: list = None,
        text_answer: str = None,
    ) -> AttemptAnswer:
        """
        Submit an answer for a question in an attempt.
        """
        if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
            raise ValueError("Este intento ya no está en progreso")

        # Check time limit
        if attempt.assessment.time_limit:
            elapsed = (timezone.now() - attempt.started_at).total_seconds() / 60
            if elapsed > attempt.assessment.time_limit:
                attempt.status = AssessmentAttempt.Status.EXPIRED
                attempt.save()
                raise ValueError("El tiempo ha expirado")

        # Get or create attempt answer
        attempt_answer, created = AttemptAnswer.objects.get_or_create(
            attempt=attempt,
            question=question,
        )

        # Set text answer if provided
        if text_answer is not None:
            attempt_answer.text_answer = text_answer

        attempt_answer.save()

        # Set selected answers if provided
        if selected_answer_ids is not None:
            answers = Answer.objects.filter(
                id__in=selected_answer_ids,
                question=question,
            )
            attempt_answer.selected_answers.set(answers)

        # Auto-grade for objective questions
        if question.question_type in [
            Question.Type.SINGLE_CHOICE,
            Question.Type.MULTIPLE_CHOICE,
            Question.Type.TRUE_FALSE,
            Question.Type.MATCHING,
        ]:
            AssessmentService._grade_objective_answer(attempt_answer)

        return attempt_answer

    @staticmethod
    def _grade_objective_answer(attempt_answer: AttemptAnswer) -> None:
        """
        Grade an objective (auto-gradable) answer.
        """
        import json as json_module

        question = attempt_answer.question

        if question.question_type == Question.Type.MATCHING:
            # Matching: compare user pairs against correct pairs from metadata
            correct_pairs = question.metadata.get("match_pairs", [])
            correct_map = {
                p["left"].strip().lower(): p["right"].strip().lower() for p in correct_pairs
            }

            try:
                user_pairs = (
                    json_module.loads(attempt_answer.text_answer)
                    if attempt_answer.text_answer
                    else []
                )
            except (json_module.JSONDecodeError, TypeError):
                user_pairs = []

            user_map = {p["left"].strip().lower(): p["right"].strip().lower() for p in user_pairs}
            attempt_answer.is_correct = correct_map == user_map
        else:
            correct_answers = set(
                question.answers.filter(is_correct=True).values_list("id", flat=True)
            )
            selected_answers = set(attempt_answer.selected_answers.values_list("id", flat=True))

            if question.question_type in (
                Question.Type.SINGLE_CHOICE,
                Question.Type.MULTIPLE_CHOICE,
                Question.Type.TRUE_FALSE,
            ):
                attempt_answer.is_correct = correct_answers == selected_answers

        # Award points
        if attempt_answer.is_correct:
            attempt_answer.points_awarded = question.points
        else:
            attempt_answer.points_awarded = Decimal("0.00")

        attempt_answer.save()

    @staticmethod
    @transaction.atomic
    def submit_attempt(attempt: AssessmentAttempt) -> AssessmentAttempt:
        """
        Submit an assessment attempt for grading.
        """
        if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
            raise ValueError("Este intento ya no está en progreso")

        # Calculate time spent
        elapsed = (timezone.now() - attempt.started_at).total_seconds()
        attempt.time_spent = int(elapsed)
        attempt.submitted_at = timezone.now()
        attempt.status = AssessmentAttempt.Status.SUBMITTED

        # Check if all answers can be auto-graded
        all_auto_graded = True
        for question in attempt.assessment.questions.all():
            if question.question_type in [
                Question.Type.SHORT_ANSWER,
                Question.Type.ESSAY,
                Question.Type.ORDERING,
            ]:
                all_auto_graded = False
                break

        if all_auto_graded:
            AssessmentService.grade_attempt(attempt)

        attempt.save()
        return attempt

    @staticmethod
    @transaction.atomic
    def grade_attempt(
        attempt: AssessmentAttempt,
        grader=None,
    ) -> AssessmentAttempt:
        """
        Grade an assessment attempt.
        """
        total_points = attempt.assessment.total_points

        total_points = Decimal(str(total_points))

        if total_points == 0:
            attempt.score = Decimal("0.00")
            attempt.points_earned = Decimal("0.00")
            attempt.passed = False
        else:
            # Sum up points from all answers
            points_earned = Decimal("0")
            for attempt_answer in attempt.attempt_answers.all():
                if attempt_answer.points_awarded is not None:
                    points_earned += Decimal(str(attempt_answer.points_awarded))

            attempt.points_earned = points_earned.quantize(Decimal("0.01"))
            attempt.score = ((points_earned / total_points) * 100).quantize(Decimal("0.01"))
            attempt.passed = attempt.score >= attempt.assessment.passing_score

        attempt.status = AssessmentAttempt.Status.GRADED
        attempt.graded_at = timezone.now()
        if grader:
            attempt.graded_by = grader

        attempt.save()
        return attempt

    @staticmethod
    def grade_essay_answer(
        attempt_answer: AttemptAnswer,
        points: Decimal,
        feedback: str = "",
        grader=None,
    ) -> AttemptAnswer:
        """
        Grade a subjective (essay/short answer) response.
        """
        max_points = attempt_answer.question.points
        points = Decimal(str(points))

        if points > max_points:
            raise ValueError(f"Los puntos no pueden exceder {max_points}")

        if points < 0:
            raise ValueError("Los puntos no pueden ser negativos")

        attempt_answer.points_awarded = points
        attempt_answer.is_correct = points == max_points
        attempt_answer.feedback = feedback
        attempt_answer.save()

        # Check if all answers are graded and update attempt
        attempt = attempt_answer.attempt
        all_graded = True
        for ans in attempt.attempt_answers.all():
            if ans.points_awarded is None:
                all_graded = False
                break

        if all_graded:
            AssessmentService.grade_attempt(attempt, grader)

        return attempt_answer

    @staticmethod
    def get_attempt_results(attempt: AssessmentAttempt) -> dict:
        """
        Get detailed results for a completed attempt.
        """
        if attempt.status not in [
            AssessmentAttempt.Status.GRADED,
            AssessmentAttempt.Status.SUBMITTED,
        ]:
            raise ValueError("El intento aún está en progreso")

        assessment = attempt.assessment
        questions_results = []

        # Prefetch attempt answers with selected_answers to avoid N+1 queries
        attempt_answers = attempt.attempt_answers.select_related("question").prefetch_related(
            "selected_answers"
        )
        # Create dictionary for O(1) lookup by question_id
        answers_by_question = {aa.question_id: aa for aa in attempt_answers}

        # Prefetch questions with their answers to avoid N+1 queries
        questions = assessment.questions.prefetch_related("answers").all()

        for question in questions:
            attempt_answer = answers_by_question.get(question.id)

            result = {
                "question_id": question.id,
                "question_text": question.text,
                "question_type": question.question_type,
                "points_possible": question.points,
                "points_awarded": float(attempt_answer.points_awarded)
                if attempt_answer and attempt_answer.points_awarded
                else 0,
                "is_correct": attempt_answer.is_correct if attempt_answer else None,
            }

            # Add user's answer
            if attempt_answer:
                if question.question_type in [
                    Question.Type.SINGLE_CHOICE,
                    Question.Type.MULTIPLE_CHOICE,
                    Question.Type.TRUE_FALSE,
                ]:
                    # Use prefetched selected_answers
                    result["selected_answers"] = [
                        sa.id for sa in attempt_answer.selected_answers.all()
                    ]
                else:
                    result["text_answer"] = attempt_answer.text_answer

                result["feedback"] = attempt_answer.feedback

            # Add correct answers if enabled
            if assessment.show_correct_answers:
                # Use prefetched answers
                result["correct_answers"] = [a.id for a in question.answers.all() if a.is_correct]
                result["explanation"] = question.explanation

            questions_results.append(result)

        return {
            "attempt_id": attempt.id,
            "assessment_title": assessment.title,
            "status": attempt.status,
            "score": float(attempt.score) if attempt.score else 0,
            "passed": attempt.passed,
            "passing_score": assessment.passing_score,
            "points_earned": attempt.points_earned,
            "total_points": assessment.total_points,
            "time_spent": attempt.time_spent,
            "time_limit": assessment.time_limit,
            "started_at": attempt.started_at.isoformat(),
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "questions": questions_results,
        }

    @staticmethod
    def get_assessment_statistics(assessment: Assessment) -> dict:
        """
        Get statistics for an assessment.
        """
        attempts = AssessmentAttempt.objects.filter(
            assessment=assessment,
            status=AssessmentAttempt.Status.GRADED,
        )

        if not attempts.exists():
            return {
                "total_attempts": 0,
                "average_score": 0,
                "pass_rate": 0,
                "highest_score": 0,
                "lowest_score": 0,
                "average_time": 0,
            }

        from django.db.models import Avg, Max, Min

        stats = attempts.aggregate(
            avg_score=Avg("score"),
            max_score=Max("score"),
            min_score=Min("score"),
            avg_time=Avg("time_spent"),
        )

        total = attempts.count()
        passed = attempts.filter(passed=True).count()

        return {
            "total_attempts": total,
            "average_score": float(stats["avg_score"] or 0),
            "pass_rate": (passed / total) * 100 if total > 0 else 0,
            "highest_score": float(stats["max_score"] or 0),
            "lowest_score": float(stats["min_score"] or 0),
            "average_time": int(stats["avg_time"] or 0),
        }

    @staticmethod
    def get_question_statistics(question: Question) -> dict:
        """
        Get statistics for a specific question.
        """
        attempt_answers = AttemptAnswer.objects.filter(
            question=question,
            attempt__status=AssessmentAttempt.Status.GRADED,
        )

        total = attempt_answers.count()
        if total == 0:
            return {
                "total_answers": 0,
                "correct_rate": 0,
                "answer_distribution": {},
            }

        correct = attempt_answers.filter(is_correct=True).count()

        # Answer distribution for choice questions
        distribution = {}
        if question.question_type in [
            Question.Type.SINGLE_CHOICE,
            Question.Type.MULTIPLE_CHOICE,
            Question.Type.TRUE_FALSE,
        ]:
            for answer in question.answers.all():
                count = attempt_answers.filter(selected_answers=answer).count()
                distribution[str(answer.id)] = {
                    "text": answer.text[:50],
                    "count": count,
                    "percentage": (count / total) * 100 if total > 0 else 0,
                    "is_correct": answer.is_correct,
                }

        return {
            "total_answers": total,
            "correct_rate": (correct / total) * 100 if total > 0 else 0,
            "answer_distribution": distribution,
        }

    @staticmethod
    @transaction.atomic
    def auto_grade_attempt(attempt: AssessmentAttempt) -> AssessmentAttempt:
        """
        Auto-grade objective questions in an assessment attempt.

        This method grades all auto-gradable questions (single choice, multiple choice,
        true/false) and calculates the score. For attempts that contain only auto-gradable
        questions, it also marks the attempt as graded.

        Args:
            attempt: The AssessmentAttempt instance to grade.

        Returns:
            The updated AssessmentAttempt instance.
        """
        total_points = Decimal("0")
        earned_points = Decimal("0")
        all_gradeable = True

        for attempt_answer in attempt.attempt_answers.all():
            question = attempt_answer.question

            # Check if question can be auto-graded
            if question.question_type in [
                Question.Type.SINGLE_CHOICE,
                Question.Type.MULTIPLE_CHOICE,
                Question.Type.TRUE_FALSE,
                Question.Type.MATCHING,
            ]:
                if question.question_type == Question.Type.MATCHING:
                    # Use the unified grading method for matching
                    AssessmentService._grade_objective_answer(attempt_answer)
                    is_correct = attempt_answer.is_correct
                    points_awarded = Decimal(str(attempt_answer.points_awarded or 0))
                else:
                    # Get correct answers
                    correct_answers = set(
                        question.answers.filter(is_correct=True).values_list("id", flat=True)
                    )
                    selected_answers = set(
                        attempt_answer.selected_answers.values_list("id", flat=True)
                    )

                    is_correct = correct_answers == selected_answers
                    points_awarded = question.points if is_correct else Decimal("0.00")

                    attempt_answer.is_correct = is_correct
                    attempt_answer.points_awarded = points_awarded
                    attempt_answer.save()

                total_points += question.points
                earned_points += points_awarded
            else:
                # Essay, short answer need manual grading
                all_gradeable = False
                total_points += question.points

        # Include unanswered questions in total
        answered_questions = attempt.attempt_answers.values_list("question_id", flat=True)
        unanswered = attempt.assessment.questions.exclude(id__in=answered_questions)

        for question in unanswered:
            total_points += question.points
            if question.question_type in [
                Question.Type.SINGLE_CHOICE,
                Question.Type.MULTIPLE_CHOICE,
                Question.Type.TRUE_FALSE,
                Question.Type.MATCHING,
            ]:
                # Create empty answer marked as wrong
                AttemptAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    is_correct=False,
                    points_awarded=Decimal("0.00"),
                )

        attempt.points_earned = earned_points.quantize(Decimal("0.01"))

        if total_points > 0:
            attempt.score = ((earned_points / total_points) * 100).quantize(Decimal("0.01"))
            attempt.passed = attempt.score >= attempt.assessment.passing_score
        else:
            attempt.score = Decimal("0.00")
            attempt.passed = False

        if all_gradeable:
            attempt.status = AssessmentAttempt.Status.GRADED
            attempt.graded_at = timezone.now()
        elif attempt.status == AssessmentAttempt.Status.SUBMITTED:
            # Subjetivas (essay/short_answer) requieren calificacion manual.
            # Logueamos para que el admin pueda detectar y completar la calificacion.
            logger.info(
                "Attempt %s requires manual grading (essay/short_answer questions present)",
                attempt.id,
            )

        attempt.save()
        return attempt

    @staticmethod
    def calculate_score(attempt: AssessmentAttempt) -> AssessmentAttempt:
        """
        Recalculate the score for an attempt based on awarded points.

        This method is typically used after manually grading essay or short answer
        questions to recalculate the total score.

        Args:
            attempt: The AssessmentAttempt instance to recalculate.

        Returns:
            The updated AssessmentAttempt instance.
        """
        total_points = Decimal(str(attempt.assessment.total_points))
        earned_points = sum(
            (
                Decimal(str(aa.points_awarded))
                for aa in attempt.attempt_answers.all()
                if aa.points_awarded is not None
            ),
            Decimal("0"),
        )

        attempt.points_earned = earned_points.quantize(Decimal("0.01"))

        if total_points > 0:
            attempt.score = ((earned_points / total_points) * 100).quantize(Decimal("0.01"))
            attempt.passed = attempt.score >= attempt.assessment.passing_score
        else:
            attempt.score = Decimal("0.00")
            attempt.passed = False

        attempt.save()
        return attempt


class QuestionBankService:
    """Service for managing question banks."""

    @staticmethod
    @transaction.atomic
    def duplicate_question(
        question: Question,
        target_assessment: Assessment = None,
    ) -> Question:
        """
        Duplicate a question to the same or different assessment.
        """
        target = target_assessment or question.assessment

        # Create new question
        new_question = Question.objects.create(
            assessment=target,
            question_type=question.question_type,
            text=question.text,
            explanation=question.explanation,
            points=question.points,
            order=target.questions.count() + 1,
            metadata=question.metadata,
        )

        # Duplicate answers
        for answer in question.answers.all():
            Answer.objects.create(
                question=new_question,
                text=answer.text,
                is_correct=answer.is_correct,
                order=answer.order,
                feedback=answer.feedback,
            )

        return new_question

    @staticmethod
    @transaction.atomic
    def import_questions_from_assessment(
        source_assessment: Assessment,
        target_assessment: Assessment,
        question_ids: list = None,
    ) -> list:
        """
        Import questions from one assessment to another.
        """
        if question_ids:
            questions = source_assessment.questions.filter(id__in=question_ids)
        else:
            questions = source_assessment.questions.all()

        imported = []
        for question in questions:
            new_question = QuestionBankService.duplicate_question(question, target_assessment)
            imported.append(new_question)

        return imported

    @staticmethod
    def validate_question(question: Question) -> dict:
        """
        Validate a question has proper setup.
        """
        errors = []
        warnings = []

        # Check text
        if not question.text.strip():
            errors.append("La pregunta no tiene texto")

        # Check answers for choice questions
        if question.question_type in [
            Question.Type.SINGLE_CHOICE,
            Question.Type.MULTIPLE_CHOICE,
            Question.Type.TRUE_FALSE,
        ]:
            answers = question.answers.all()

            if answers.count() < 2:
                errors.append("La pregunta necesita al menos 2 respuestas")

            correct_count = answers.filter(is_correct=True).count()

            if correct_count == 0:
                errors.append("La pregunta no tiene respuesta correcta")

            if question.question_type == Question.Type.SINGLE_CHOICE and correct_count > 1:
                errors.append("Pregunta de selección única tiene múltiples respuestas correctas")

            if question.question_type == Question.Type.TRUE_FALSE:
                if answers.count() != 2:
                    errors.append("Pregunta verdadero/falso debe tener exactamente 2 respuestas")
                if correct_count != 1:
                    errors.append(
                        "Pregunta verdadero/falso debe tener exactamente 1 respuesta correcta"
                    )

        # Check points
        if question.points <= 0:
            warnings.append("La pregunta tiene 0 puntos")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def validate_assessment(assessment: Assessment) -> dict:
        """
        Validate an entire assessment.
        """
        errors = []
        warnings = []
        question_issues = []

        # Check basic info
        if not assessment.title.strip():
            errors.append("La evaluación no tiene título")

        # Check questions
        questions = assessment.questions.all()
        if questions.count() == 0:
            errors.append("La evaluación no tiene preguntas")
        else:
            for question in questions:
                validation = QuestionBankService.validate_question(question)
                if not validation["is_valid"] or validation["warnings"]:
                    question_issues.append(
                        {
                            "question_id": question.id,
                            "question_order": question.order,
                            "errors": validation["errors"],
                            "warnings": validation["warnings"],
                        }
                    )

        # Check passing score
        if assessment.passing_score > 100:
            errors.append("El puntaje mínimo no puede ser mayor a 100%")
        elif assessment.passing_score < 0:
            errors.append("El puntaje mínimo no puede ser negativo")

        # Check time limit
        if assessment.time_limit and assessment.time_limit < 1:
            warnings.append("El tiempo límite es muy corto")

        return {
            "is_valid": len(errors) == 0 and all(len(q["errors"]) == 0 for q in question_issues),
            "errors": errors,
            "warnings": warnings,
            "question_issues": question_issues,
        }
