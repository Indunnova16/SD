"""
ViewSets for assessments API.
"""

from decimal import Decimal

from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.assessments.models import (
    Answer,
    Assessment,
    AssessmentAttempt,
    AttemptAnswer,
    Question,
)
from apps.assessments.services import AssessmentService

from .serializers import (
    AnswerSerializer,
    AnswerWithCorrectSerializer,
    AssessmentAttemptListSerializer,
    AssessmentAttemptSerializer,
    AssessmentCreateSerializer,
    AssessmentListSerializer,
    AssessmentSerializer,
    AttemptAnswerSubmitSerializer,
    QuestionCreateSerializer,
    QuestionSerializer,
    QuestionWithAnswersSerializer,
    StartAttemptSerializer,
    SubmitAttemptSerializer,
)


class AssessmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing assessments."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Assessment.objects.select_related("course", "lesson", "created_by")

        # Filter by status
        assessment_status = self.request.query_params.get("status")
        if assessment_status:
            queryset = queryset.filter(status=assessment_status)

        # Filter by course
        course_id = self.request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        # Filter by type
        assessment_type = self.request.query_params.get("type")
        if assessment_type:
            queryset = queryset.filter(assessment_type=assessment_type)

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        # By default, non-staff see only published assessments
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                Q(status=Assessment.Status.PUBLISHED) | Q(created_by=self.request.user)
            )

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return AssessmentListSerializer
        if self.action == "create":
            return AssessmentCreateSerializer
        return AssessmentSerializer

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Publish an assessment."""
        assessment = self.get_object()

        if assessment.status == Assessment.Status.PUBLISHED:
            return Response(
                {"error": "La evaluación ya está publicada"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if assessment.questions.count() == 0:
            return Response(
                {"error": "La evaluación debe tener al menos una pregunta"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assessment.status = Assessment.Status.PUBLISHED
        assessment.save()

        return Response(AssessmentSerializer(assessment, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive an assessment."""
        assessment = self.get_object()
        assessment.status = Assessment.Status.ARCHIVED
        assessment.save()

        return Response(AssessmentSerializer(assessment, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get all questions for an assessment."""
        assessment = self.get_object()
        include_correct = request.query_params.get("include_correct", "false").lower() == "true"

        questions = assessment.questions.prefetch_related("answers").order_by("order")

        if include_correct and (request.user.is_staff or assessment.created_by == request.user):
            serializer = QuestionWithAnswersSerializer(questions, many=True)
        else:
            serializer = QuestionSerializer(questions, many=True)

        return Response(serializer.data)


class QuestionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing questions within an assessment."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        assessment_id = self.kwargs.get("assessment_pk")
        return (
            Question.objects.filter(assessment_id=assessment_id)
            .prefetch_related("answers")
            .order_by("order")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return QuestionCreateSerializer
        if self.action in ["retrieve", "update", "partial_update"]:
            return QuestionWithAnswersSerializer
        return QuestionSerializer

    def perform_create(self, serializer):
        assessment_id = self.kwargs.get("assessment_pk")
        assessment = get_object_or_404(Assessment, pk=assessment_id)

        # Get next order
        max_order = assessment.questions.aggregate(max_order=Max("order"))["max_order"] or 0
        serializer.save(assessment=assessment, order=max_order + 1)

    @action(detail=True, methods=["post"])
    def add_answer(self, request, assessment_pk=None, pk=None):
        """Add an answer to a question."""
        question = self.get_object()
        serializer = AnswerSerializer(data=request.data)

        if serializer.is_valid():
            # Get next order
            max_order = question.answers.aggregate(max_order=Max("order"))["max_order"] or 0
            serializer.save(question=question, order=max_order + 1)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AnswerViewSet(viewsets.ModelViewSet):
    """ViewSet for managing answers within a question."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AnswerWithCorrectSerializer

    def get_queryset(self):
        question_id = self.kwargs.get("question_pk")
        return Answer.objects.filter(question_id=question_id).order_by("order")

    def perform_create(self, serializer):
        question_id = self.kwargs.get("question_pk")
        question = get_object_or_404(Question, pk=question_id)

        # Get next order
        max_order = question.answers.aggregate(max_order=Max("order"))["max_order"] or 0
        serializer.save(question=question, order=max_order + 1)


class AssessmentAttemptViewSet(viewsets.ModelViewSet):
    """ViewSet for managing assessment attempts."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = AssessmentAttempt.objects.select_related("user", "assessment").prefetch_related(
            "attempt_answers"
        )

        # Filter by assessment
        assessment_id = self.request.query_params.get("assessment")
        if assessment_id:
            queryset = queryset.filter(assessment_id=assessment_id)

        # Filter by status
        attempt_status = self.request.query_params.get("status")
        if attempt_status:
            queryset = queryset.filter(status=attempt_status)

        # Non-staff users see only their own attempts
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        return queryset.order_by("-started_at")

    def get_serializer_class(self):
        if self.action == "list":
            return AssessmentAttemptListSerializer
        return AssessmentAttemptSerializer

    @action(detail=False, methods=["post"])
    def start(self, request):
        """Start a new assessment attempt."""
        serializer = StartAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assessment_id = serializer.validated_data["assessment_id"]
        assessment = get_object_or_404(
            Assessment, pk=assessment_id, status=Assessment.Status.PUBLISHED
        )

        # Check max attempts
        if assessment.max_attempts > 0:
            existing_attempts = AssessmentAttempt.objects.filter(
                user=request.user,
                assessment=assessment,
            ).count()

            if existing_attempts >= assessment.max_attempts:
                return Response(
                    {"error": "Has alcanzado el número máximo de intentos"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check for existing in-progress attempt
        in_progress = AssessmentAttempt.objects.filter(
            user=request.user,
            assessment=assessment,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        ).first()

        if in_progress:
            return Response(
                AssessmentAttemptSerializer(in_progress, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )

        # Calculate attempt number
        attempt_number = (
            AssessmentAttempt.objects.filter(
                user=request.user,
                assessment=assessment,
            ).count()
            + 1
        )

        # Get client info
        ip_address = request.META.get("REMOTE_ADDR", "")
        user_agent = request.headers.get("user-agent", "")

        # Create attempt
        attempt = AssessmentAttempt.objects.create(
            user=request.user,
            assessment=assessment,
            attempt_number=attempt_number,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return Response(
            AssessmentAttemptSerializer(attempt, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit an assessment attempt."""
        attempt = self.get_object()

        if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
            return Response(
                {"error": "Este intento ya ha sido enviado"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SubmitAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answers_data = serializer.validated_data["answers"]
        time_spent = serializer.validated_data.get("time_spent", 0)

        # Process answers
        for answer_data in answers_data:
            question_id = answer_data["question_id"]
            selected_answer_ids = answer_data.get("selected_answer_ids", [])
            text_answer = answer_data.get("text_answer", "")

            try:
                question = Question.objects.get(
                    pk=question_id,
                    assessment=attempt.assessment,
                )
            except Question.DoesNotExist:
                continue

            # Create or update attempt answer
            attempt_answer, created = AttemptAnswer.objects.get_or_create(
                attempt=attempt,
                question=question,
                defaults={"text_answer": text_answer},
            )

            if not created:
                attempt_answer.text_answer = text_answer
                attempt_answer.save()

            # Set selected answers
            if selected_answer_ids:
                attempt_answer.selected_answers.set(
                    Answer.objects.filter(
                        pk__in=selected_answer_ids,
                        question=question,
                    )
                )

        # Update attempt
        attempt.time_spent = time_spent
        attempt.submitted_at = timezone.now()
        attempt.status = AssessmentAttempt.Status.SUBMITTED
        attempt.save()

        # Auto-grade if possible using the service
        AssessmentService.auto_grade_attempt(attempt)

        return Response(AssessmentAttemptSerializer(attempt, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def save_answer(self, request, pk=None):
        """Save a single answer during the attempt."""
        attempt = self.get_object()

        if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
            return Response(
                {"error": "Este intento ya ha sido enviado"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AttemptAnswerSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question_id = serializer.validated_data["question_id"]
        selected_answer_ids = serializer.validated_data.get("selected_answer_ids", [])
        text_answer = serializer.validated_data.get("text_answer", "")

        try:
            question = Question.objects.get(
                pk=question_id,
                assessment=attempt.assessment,
            )
        except Question.DoesNotExist:
            return Response(
                {"error": "Pregunta no válida"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or update attempt answer
        attempt_answer, created = AttemptAnswer.objects.get_or_create(
            attempt=attempt,
            question=question,
            defaults={"text_answer": text_answer},
        )

        if not created:
            attempt_answer.text_answer = text_answer
            attempt_answer.save()

        # Set selected answers
        if selected_answer_ids:
            attempt_answer.selected_answers.set(
                Answer.objects.filter(
                    pk__in=selected_answer_ids,
                    question=question,
                )
            )

        return Response({"status": "saved"})

    @action(detail=True, methods=["post"])
    def grade(self, request, pk=None):
        """Manually grade an attempt (for essay questions)."""
        attempt = self.get_object()

        if not request.user.is_staff:
            return Response(
                {"error": "Solo personal autorizado puede calificar"},
                status=status.HTTP_403_FORBIDDEN,
            )

        grades = request.data.get("grades", [])

        for grade_data in grades:
            question_id = grade_data.get("question_id")
            points = grade_data.get("points", 0)
            feedback = grade_data.get("feedback", "")

            try:
                attempt_answer = AttemptAnswer.objects.get(
                    attempt=attempt,
                    question_id=question_id,
                )
                attempt_answer.points_awarded = Decimal(str(points))
                attempt_answer.feedback = feedback
                attempt_answer.is_correct = points > 0
                attempt_answer.save()
            except AttemptAnswer.DoesNotExist:
                continue

        # Recalculate scores using the service
        AssessmentService.calculate_score(attempt)

        attempt.graded_at = timezone.now()
        attempt.graded_by = request.user
        attempt.status = AssessmentAttempt.Status.GRADED
        attempt.save()

        return Response(AssessmentAttemptSerializer(attempt, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def my_attempts(self, request):
        """Get current user's attempts."""
        attempts = (
            AssessmentAttempt.objects.filter(user=request.user)
            .select_related("assessment")
            .order_by("-started_at")
        )

        serializer = AssessmentAttemptListSerializer(attempts, many=True)
        return Response(serializer.data)
