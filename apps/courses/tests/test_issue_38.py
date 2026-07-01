"""
Regression tests for issue SD#38 (reproceso — 3rd bounce, FIX_INCOMPLETO).

Client report: creating a NEW lesson of type "Evaluación" (quiz) with inline
questions (true_false / matching) from the course builder does not persist
the questions correctly:
  - true_false: the user's selection is ignored, "Verdadero" always ends up
    is_correct=True regardless of what was picked.
  - matching: 0 Answers are created no matter how many pairs the user enters.

Root cause (apps/courses/views.py::builder_add_lesson, confirmed by F2 via
static analysis + deterministic logic replay): the JSON emitted by
QuizBuilder.saveQuestion() (templates/courses/partials/builder/lesson_form.html)
uses keys `truefalse_correct` (a real JSON *boolean*, not a string) and `pairs`,
but the Python parser read `trueFalseCorrect` (compared against the *string*
"true") and `matchPairs`. Both `.get()` calls always fell back to their
defaults, so the bug was 100% silent (no exception, no validation error).

This file exercises builder_add_lesson with the EXACT payload shape emitted
by the JS (see SPRINTS/RUN_2026-07-01_0912/attachments/SD_38_repro_logic.json,
produced by F2's deterministic replay) to pin the fix and guard against the
documented gotcha: renaming the key WITHOUT fixing the type (str "true" vs
JSON bool) would invert the bug instead of fixing it.
"""

import json
from datetime import date
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, Question
from apps.courses.models import Category, Course, Lesson, Module


class BuilderAddQuizLessonIssue38Tests(TestCase):
    """Reproduce and pin the fix for SD#38 (builder_add_lesson quiz parsing)."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_sd38@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD38",
            document_number="38000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.category = Category.objects.create(
            name="Cat SD38",
            slug="cat-sd38",
            description="cat",
            color="#0000AA",
        )
        self.course = Course.objects.create(
            code="COURSE-SD38-1",
            title="Curso SD38",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        self.module = Module.objects.create(
            course=self.course, title="Modulo SD38", description="m", order=1
        )
        # Legacy pre-existing data: a quiz lesson + assessment that predate this
        # fix (mirrors the real prod row lesson id=98 'Evaluacion seguridad vial'
        # found by F2 — published, 0 questions). Creating a NEW quiz lesson must
        # not disturb it.
        self.legacy_lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion legacy SD38",
            description="leccion previa",
            lesson_type=Lesson.Type.QUIZ,
            order=0,
        )
        self.legacy_assessment = Assessment.objects.create(
            title="Evaluacion legacy SD38",
            assessment_type="quiz",
            passing_score=80,
            max_attempts=3,
            course=self.course,
            lesson=self.legacy_lesson,
            created_by=self.staff,
            status="published",
        )

        self.url = reverse(
            "courses:builder_add_lesson",
            kwargs={"course_id": self.course.id, "module_id": self.module.id},
        )
        self.client.force_login(self.staff)

    def _post_quiz(self, title, quiz_questions):
        return self.client.post(
            self.url,
            data={
                "title": title,
                "lesson_type": "quiz",
                "is_mandatory": "on",
                "duration": "0",
                "quiz_questions": json.dumps(quiz_questions),
            },
            HTTP_HX_REQUEST="true",
        )

    # ------------------------------------------------------------------
    # true_false — the exact bug: selection ignored, always "Verdadero".
    # ------------------------------------------------------------------

    def test_true_false_persists_false_selection(self):
        """User picks 'Falso' -> Answer('Falso').is_correct must be True.

        Before the fix, `qdata.get("trueFalseCorrect", "true") == "true"`
        NEVER matched (JS never sent that key), so `is_true` was always True
        regardless of the real selection.
        """
        resp = self._post_quiz(
            "QA_E2E_M38 leccion VF falso",
            [
                {
                    "type": "true_false",
                    "text": "QA_E2E_M38 pregunta VF",
                    "points": 1,
                    "explanation": "",
                    "truefalse_correct": False,
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion VF falso")
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)
        self.assertEqual(question.question_type, "true_false")

        verdadero = Answer.objects.get(question=question, text="Verdadero")
        falso = Answer.objects.get(question=question, text="Falso")
        self.assertFalse(verdadero.is_correct, "Verdadero no debe ser correcto (usuario eligio Falso)")
        self.assertTrue(falso.is_correct, "Falso debe quedar marcado como la respuesta correcta")

    def test_true_false_persists_true_selection(self):
        """User picks 'Verdadero' -> still works (guards against inverting the bug)."""
        resp = self._post_quiz(
            "QA_E2E_M38 leccion VF verdadero",
            [
                {
                    "type": "true_false",
                    "text": "QA_E2E_M38 pregunta VF 2",
                    "points": 1,
                    "explanation": "",
                    "truefalse_correct": True,
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion VF verdadero")
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)

        verdadero = Answer.objects.get(question=question, text="Verdadero")
        falso = Answer.objects.get(question=question, text="Falso")
        self.assertTrue(verdadero.is_correct)
        self.assertFalse(falso.is_correct)

    def test_true_false_default_when_key_missing(self):
        """If the JS ever omits the key, default stays 'Verdadero correcto'
        (matches pre-existing default behavior — only the source key/type change)."""
        resp = self._post_quiz(
            "QA_E2E_M38 leccion VF sin clave",
            [
                {
                    "type": "true_false",
                    "text": "QA_E2E_M38 pregunta VF sin clave",
                    "points": 1,
                    "explanation": "",
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion VF sin clave")
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)
        verdadero = Answer.objects.get(question=question, text="Verdadero")
        self.assertTrue(verdadero.is_correct)

    # ------------------------------------------------------------------
    # matching — the exact bug: 0 Answers created despite valid pairs.
    # ------------------------------------------------------------------

    def test_matching_persists_pairs(self):
        """2 pairs entered by the user -> 2 Answers created.

        Before the fix, `qdata.get("matchPairs", [])` always returned `[]`
        because the JS sends `pairs`, so 0 Answers were ever created.
        """
        resp = self._post_quiz(
            "QA_E2E_M38 leccion emparejamiento",
            [
                {
                    "type": "matching",
                    "text": "QA_E2E_M38 pregunta emparejamiento",
                    "points": 1,
                    "explanation": "",
                    "pairs": [
                        {"left": "Perro", "right": "Animal"},
                        {"left": "Rosa", "right": "Planta"},
                    ],
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion emparejamiento")
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)
        self.assertEqual(question.question_type, "matching")

        answers = list(Answer.objects.filter(question=question).order_by("order"))
        self.assertEqual(len(answers), 2)
        self.assertEqual(answers[0].text, "Perro")
        self.assertEqual(answers[0].feedback, "Animal")
        self.assertEqual(answers[1].text, "Rosa")
        self.assertEqual(answers[1].feedback, "Planta")

    def test_matching_empty_pairs_persists_zero_answers(self):
        """No pairs entered -> 0 Answers (not a bug — nothing to persist)."""
        resp = self._post_quiz(
            "QA_E2E_M38 leccion emparejamiento vacia",
            [
                {
                    "type": "matching",
                    "text": "QA_E2E_M38 pregunta emparejamiento vacia",
                    "points": 1,
                    "explanation": "",
                    "pairs": [],
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(
            module=self.module, title="QA_E2E_M38 leccion emparejamiento vacia"
        )
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)
        self.assertEqual(Answer.objects.filter(question=question).count(), 0)

    # ------------------------------------------------------------------
    # 'open' -> now maps to the valid Question.Type.SHORT_ANSWER choice.
    # ------------------------------------------------------------------

    def test_short_answer_question_type_is_a_valid_choice(self):
        """The JS dropdown used to emit type='open', which is NOT a valid
        Question.Type choice (silently persisted invalid data, since
        Question.objects.create() does not call full_clean()). It must now
        emit 'short_answer', a real choice already rendered by
        take_assessment.html."""
        resp = self._post_quiz(
            "QA_E2E_M38 leccion abierta",
            [
                {
                    "type": "short_answer",
                    "text": "QA_E2E_M38 pregunta abierta",
                    "points": 1,
                    "explanation": "",
                }
            ],
        )
        self.assertEqual(resp.status_code, 200)
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion abierta")
        assessment = Assessment.objects.get(lesson=lesson)
        question = Question.objects.get(assessment=assessment)
        self.assertEqual(question.question_type, "short_answer")
        self.assertIn(question.question_type, Question.Type.values)

    # ------------------------------------------------------------------
    # Error exposure — swallowed exceptions must surface in the HTMX swap.
    # ------------------------------------------------------------------

    def test_quiz_creation_error_is_exposed_in_htmx_swap(self):
        """If assessment/question creation raises, the error must be visible
        in the rendered partial (not silently swallowed via messages.error,
        which never renders inside an HTMX partial swap), and the failed
        assessment creation must not leave a partial/inconsistent state."""
        with patch(
            "apps.assessments.models.Assessment.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            resp = self._post_quiz(
                "QA_E2E_M38 leccion con error",
                [{"type": "true_false", "text": "x", "points": 1, "truefalse_correct": True}],
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Error al crear el quiz")

        # Lesson itself still persists (only the quiz sub-creation failed)...
        lesson = Lesson.objects.get(module=self.module, title="QA_E2E_M38 leccion con error")
        # ...but no Assessment/Question was left half-created (atomic rollback).
        self.assertFalse(Assessment.objects.filter(lesson=lesson).exists())

    # ------------------------------------------------------------------
    # Legacy data untouched.
    # ------------------------------------------------------------------

    def test_legacy_quiz_lesson_untouched_by_new_lesson_creation(self):
        """The pre-existing (legacy) quiz lesson/assessment from setUp must
        remain exactly as it was after a new quiz lesson is created alongside it."""
        self._post_quiz(
            "QA_E2E_M38 leccion nueva junto a legacy",
            [
                {
                    "type": "matching",
                    "text": "QA_E2E_M38 pregunta emparejamiento legacy check",
                    "points": 1,
                    "pairs": [{"left": "A", "right": "B"}],
                }
            ],
        )
        self.legacy_lesson.refresh_from_db()
        self.legacy_assessment.refresh_from_db()
        self.assertEqual(self.legacy_lesson.lesson_type, Lesson.Type.QUIZ)
        self.assertEqual(self.legacy_assessment.status, "published")
        self.assertEqual(Question.objects.filter(assessment=self.legacy_assessment).count(), 0)
        self.assertEqual(self.module.lessons.count(), 2)
