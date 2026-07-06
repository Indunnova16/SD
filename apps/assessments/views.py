"""
Web views for assessments app.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import Rol, user_has_rol

from .models import Answer, Assessment, AssessmentAttempt, AttemptAnswer, Question
from .services import AssessmentService


def _target_profiles_contains(field_prefix, profile_code):
    """Q object para `<field_prefix>__contains=[profile_code]`, con fallback
    SQLite (issue #58, sub-item A6) — ver docstring gemelo en
    `apps.courses.views._target_profiles_contains`. El lookup `contains` de
    `JSONField` no esta soportado en SQLite (`config/settings/test.py`)."""
    db_engine = settings.DATABASES["default"]["ENGINE"]
    if "postgresql" in db_engine:
        return Q(**{f"{field_prefix}__contains": [profile_code]})
    return Q(**{f"{field_prefix}__icontains": profile_code})


@login_required
def assessment_list(request):
    """List available assessments."""
    assessments = Assessment.objects.filter(status=Assessment.Status.PUBLISHED).select_related(
        "course", "created_by"
    )

    # RBAC — filtrado por rol (issue #58, sub-item A6): Ejecutor (o rol sin
    # asignar) ve solo evaluaciones cuyo curso (directo via `course`, o
    # heredado via `lesson.module.course`) esté dirigido a su `job_profile`
    # (via `target_profiles`), + evaluaciones sin curso targeteado
    # (standalone, o curso/ruta genérica sin perfiles asignados — visibles a
    # todos). Coordinador/Administrador ven todas las evaluaciones.
    if not user_has_rol(request.user, Rol.COORDINADOR, Rol.ADMINISTRADOR):
        profile_code = request.user.job_profile.code if request.user.job_profile else None
        generic = (
            Q(course__isnull=True, lesson__isnull=True)
            | Q(course__isnull=False, course__target_profiles=[])
            | Q(lesson__isnull=False, lesson__module__course__target_profiles=[])
        )
        if profile_code:
            assessments = assessments.filter(
                generic
                | _target_profiles_contains("course__target_profiles", profile_code)
                | _target_profiles_contains("lesson__module__course__target_profiles", profile_code)
            )
        else:
            assessments = assessments.filter(generic)

    # Filter by course
    course_id = request.GET.get("course")
    if course_id:
        assessments = assessments.filter(course_id=course_id)

    # Filter by type
    assessment_type = request.GET.get("type")
    if assessment_type:
        assessments = assessments.filter(assessment_type=assessment_type)

    context = {
        "assessments": assessments,
        "current_type": assessment_type,
        "assessment_types": Assessment.Type.choices,
    }
    return render(request, "assessments/assessment_list.html", context)


@login_required
def assessment_detail(request, assessment_id):
    """View assessment details."""
    assessment = get_object_or_404(
        Assessment.objects.select_related("course", "created_by"),
        pk=assessment_id,
    )

    # Get user's attempts
    user_attempts = AssessmentAttempt.objects.filter(
        user=request.user,
        assessment=assessment,
    ).order_by("-started_at")

    # Check if can start new attempt
    can_start = True
    if assessment.max_attempts > 0:
        if user_attempts.count() >= assessment.max_attempts:
            can_start = False

    # Check for in-progress attempt
    in_progress = user_attempts.filter(status=AssessmentAttempt.Status.IN_PROGRESS).first()

    context = {
        "assessment": assessment,
        "user_attempts": user_attempts,
        "can_start": can_start,
        "in_progress": in_progress,
        "best_attempt": user_attempts.filter(status=AssessmentAttempt.Status.GRADED)
        .order_by("-score")
        .first(),
    }
    return render(request, "assessments/assessment_detail.html", context)


@login_required
def start_attempt(request, assessment_id):
    """Start a new assessment attempt."""
    assessment = get_object_or_404(
        Assessment,
        pk=assessment_id,
        status=Assessment.Status.PUBLISHED,
    )

    # Check max attempts
    if assessment.max_attempts > 0:
        existing_count = AssessmentAttempt.objects.filter(
            user=request.user,
            assessment=assessment,
        ).count()

        if existing_count >= assessment.max_attempts:
            messages.error(request, "Has alcanzado el número máximo de intentos.")
            return redirect("assessments:detail", assessment_id=assessment_id)

    # Check for existing in-progress attempt
    in_progress = AssessmentAttempt.objects.filter(
        user=request.user,
        assessment=assessment,
        status=AssessmentAttempt.Status.IN_PROGRESS,
    ).first()

    if in_progress:
        return redirect("assessments:take", attempt_id=in_progress.id)

    # Calculate attempt number
    attempt_number = (
        AssessmentAttempt.objects.filter(
            user=request.user,
            assessment=assessment,
        ).count()
        + 1
    )

    # Create new attempt
    attempt = AssessmentAttempt.objects.create(
        user=request.user,
        assessment=assessment,
        attempt_number=attempt_number,
        ip_address=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.headers.get("user-agent", ""),
    )

    return redirect("assessments:take", attempt_id=attempt.id)


@login_required
def take_assessment(request, attempt_id):
    """Take an assessment."""
    attempt = get_object_or_404(
        AssessmentAttempt.objects.select_related("assessment"),
        pk=attempt_id,
        user=request.user,
    )

    if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
        return redirect("assessments:result", attempt_id=attempt_id)

    assessment = attempt.assessment
    questions = assessment.questions.prefetch_related("answers").order_by("order")

    # Get user's current answers
    answered = {
        aa.question_id: {
            "selected": list(aa.selected_answers.values_list("id", flat=True)),
            "text": aa.text_answer,
        }
        for aa in attempt.attempt_answers.prefetch_related("selected_answers")
    }

    context = {
        "attempt": attempt,
        "assessment": assessment,
        "questions": questions,
        "answered": answered,
        "time_limit": assessment.time_limit,
    }
    return render(request, "assessments/take_assessment.html", context)


@login_required
@require_POST
def save_answer(request, attempt_id):
    """Save a single answer (AJAX)."""
    attempt = get_object_or_404(
        AssessmentAttempt,
        pk=attempt_id,
        user=request.user,
        status=AssessmentAttempt.Status.IN_PROGRESS,
    )

    question_id = request.POST.get("question_id")
    if not question_id:
        return JsonResponse({"error": "question_id requerido"}, status=400)

    try:
        question = Question.objects.get(
            pk=question_id,
            assessment=attempt.assessment,
        )
    except Question.DoesNotExist:
        return JsonResponse({"error": "Pregunta no válida"}, status=400)

    # Leer respuesta segun tipo de pregunta — el template envia
    # name="question_<id>" para radios/checkboxes, name="text_answer_<id>"
    # para textareas, y name="matching_<id>" para el hidden de matching.
    selected_ids = request.POST.getlist(f"question_{question_id}")
    text_answer = request.POST.get(f"text_answer_{question_id}", "")
    matching_data = request.POST.get(f"matching_{question_id}", "")

    # Compatibilidad legacy con el nombre 'selected_answers' (si algun caller
    # externo / API DRF lo enviara con ese nombre).
    if not selected_ids:
        selected_ids = request.POST.getlist("selected_answers")
    if not text_answer:
        text_answer = request.POST.get("text_answer", "")
    if not matching_data:
        matching_data = request.POST.get("matching_data", "")

    # Create or update answer
    attempt_answer, _created = AttemptAnswer.objects.get_or_create(
        attempt=attempt,
        question=question,
    )

    if matching_data:
        attempt_answer.text_answer = matching_data
    elif text_answer:
        attempt_answer.text_answer = text_answer

    attempt_answer.save()

    # Set selected answers — siempre para tipos choice/true_false (permite
    # limpiar seleccion cuando el usuario deselecciona todos los checkboxes).
    if selected_ids or question.question_type in (
        Question.Type.SINGLE_CHOICE,
        Question.Type.MULTIPLE_CHOICE,
        Question.Type.TRUE_FALSE,
    ):
        attempt_answer.selected_answers.set(
            Answer.objects.filter(pk__in=selected_ids, question=question)
        )

    return JsonResponse({"status": "saved"})


@login_required
@require_POST
def submit_attempt(request, attempt_id):
    """Submit an assessment attempt."""
    attempt = get_object_or_404(
        AssessmentAttempt,
        pk=attempt_id,
        user=request.user,
        status=AssessmentAttempt.Status.IN_PROGRESS,
    )

    import json as json_module

    # Save any remaining answers
    processed_questions = set()
    for key, _value in request.POST.items():
        if key.startswith("question_"):
            question_id = key.replace("question_", "")
            if question_id in processed_questions:
                continue
            processed_questions.add(question_id)
            selected_ids = request.POST.getlist(key)

            try:
                question = Question.objects.get(
                    pk=question_id,
                    assessment=attempt.assessment,
                )

                attempt_answer, created = AttemptAnswer.objects.get_or_create(
                    attempt=attempt,
                    question=question,
                )

                if selected_ids:
                    attempt_answer.selected_answers.set(
                        Answer.objects.filter(pk__in=selected_ids, question=question)
                    )
            except Question.DoesNotExist:
                continue

        elif key.startswith("text_answer_"):
            question_id = key.replace("text_answer_", "")
            text_val = request.POST.get(key, "")
            try:
                question = Question.objects.get(
                    pk=question_id,
                    assessment=attempt.assessment,
                )
                attempt_answer, created = AttemptAnswer.objects.get_or_create(
                    attempt=attempt,
                    question=question,
                )
                attempt_answer.text_answer = text_val
                attempt_answer.save()
            except Question.DoesNotExist:
                continue

        elif key.startswith("matching_"):
            # matching_{question_id} contains JSON with user's matching pairs
            question_id = key.replace("matching_", "")
            matching_json = request.POST.get(key, "[]")
            try:
                question = Question.objects.get(
                    pk=question_id,
                    assessment=attempt.assessment,
                )
                attempt_answer, created = AttemptAnswer.objects.get_or_create(
                    attempt=attempt,
                    question=question,
                )
                attempt_answer.text_answer = matching_json
                attempt_answer.save()
            except (Question.DoesNotExist, json_module.JSONDecodeError):
                continue

    # Validate completeness
    total_questions = attempt.assessment.questions.count()
    answered_questions = attempt.attempt_answers.count()

    if answered_questions < total_questions:
        unanswered = total_questions - answered_questions
        messages.warning(
            request,
            f"Enviaste tu evaluación con {unanswered} pregunta(s) sin responder.",
        )
        if not attempt.metadata:
            attempt.metadata = {}
        attempt.metadata["unanswered_count"] = unanswered

    # Update attempt
    time_spent = int(request.POST.get("time_spent", 0))
    attempt.time_spent = time_spent
    attempt.submitted_at = timezone.now()
    attempt.status = AssessmentAttempt.Status.SUBMITTED
    attempt.save()

    # Auto-grade using the service
    AssessmentService.auto_grade_attempt(attempt)

    messages.success(request, "Evaluación enviada correctamente.")
    return redirect("assessments:result", attempt_id=attempt_id)


@login_required
def attempt_result(request, attempt_id):
    """View attempt result."""
    attempt = get_object_or_404(
        AssessmentAttempt.objects.select_related("assessment"),
        pk=attempt_id,
        user=request.user,
    )

    if attempt.status == AssessmentAttempt.Status.IN_PROGRESS:
        return redirect("assessments:take", attempt_id=attempt_id)

    assessment = attempt.assessment

    # Get questions with answers
    questions = assessment.questions.prefetch_related("answers").order_by("order")

    # Get user's answers
    user_answers = {
        aa.question_id: aa for aa in attempt.attempt_answers.prefetch_related("selected_answers")
    }

    context = {
        "attempt": attempt,
        "assessment": assessment,
        "questions": questions,
        "user_answers": user_answers,
        "show_correct": assessment.show_correct_answers,
    }
    return render(request, "assessments/attempt_result.html", context)


@login_required
def my_attempts(request):
    """View user's assessment attempts."""
    attempts = (
        AssessmentAttempt.objects.filter(user=request.user)
        .select_related("assessment")
        .order_by("-started_at")
    )

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        attempts = attempts.filter(status=status_filter)

    context = {
        "attempts": attempts,
        "current_status": status_filter,
        "statuses": AssessmentAttempt.Status.choices,
    }
    return render(request, "assessments/my_attempts.html", context)
