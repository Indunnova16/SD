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
from decimal import Decimal
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
            rol=User.Rol.ADMINISTRADOR,
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


# ==========================================================================
# ROUND 3 (bounce=2, this run) — EDITING an EXISTING question.
#
# Client report (2026-07-02): after Round 2 fixed CREATING new quiz
# questions (see BuilderAddQuizLessonIssue38Tests above), EDITING a
# question that already exists still does not persist "Puntos" nor a
# newly-added answer/option.
#
# Real root cause (confirmed by F2 via 2 live Playwright reproductions
# against prod): templates/courses/partials/builder/question_item.html's
# `<template x-if="editing">` never called `htmx.process($el)` after
# Alpine cloned it into the DOM (unlike its sibling
# `lesson_item.html:150`, which does). Because the cloned
# `<form hx-post=... hx-target=... hx-swap=...>` (question_form.html) has
# no explicit `method`/`action` fallback, htmx never registered it, so
# clicking "Guardar" fell back to the browser's *native* GET submit and
# `builder_edit_question` (this view) was **never invoked at all** — the
# database stayed 100% intact both times.
#
# IMPORTANT: this is a pure frontend wiring bug (Alpine not triggering
# htmx.process on the clone). A Django test client POST never exercises
# real browser JS, so it CANNOT reproduce/catch the actual bug — the fix
# (`x-init="$nextTick(() => htmx.process($el))"` in question_item.html)
# is only proven by the E2E Playwright journey at
# $RUN_DIR/journeys/SD_38.yaml (m38_legacy_question_points_persist /
# m38_new_question_add_option_persist), which reproduced the bug live
# against prod (RED) before the fix.
#
# What THIS test class covers instead: it pins builder_edit_question's
# server-side persistence contract (POST -> Points + Answers updated in
# DB) against a question that already existed before the POST (mirrors
# the real prod row id=28 used in F2's reproduction), as a safety net —
# if this backend logic itself ever regresses, CI catches it even though
# it is not what broke for the client this time.
# ==========================================================================


class BuilderEditExistingQuestionIssue38Tests(TestCase):
    """Pin builder_edit_question's persistence contract for an EXISTING
    (pre-created, i.e. "legacy-like") question — the flow the client
    reported broken. Does NOT cover the real (frontend/htmx) root cause;
    see class docstring above."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_sd38_edit@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD38Edit",
            document_number="38000002",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD38 Edit",
            slug="cat-sd38-edit",
            description="cat",
            color="#00AA00",
        )
        self.course = Course.objects.create(
            code="COURSE-SD38-2",
            title="Curso SD38 Edit",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        self.module = Module.objects.create(
            course=self.course, title="Modulo SD38 Edit", description="m", order=1
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Evaluacion SD38 edit",
            description="leccion",
            lesson_type=Lesson.Type.QUIZ,
            order=0,
        )
        self.assessment = Assessment.objects.create(
            title="Evaluacion SD38 edit",
            assessment_type="quiz",
            passing_score=80,
            max_attempts=3,
            course=self.course,
            lesson=self.lesson,
            created_by=self.staff,
            status="published",
        )
        # A question that already existed BEFORE this test's POST — mirrors
        # the real prod row (legacy question id=28) F2 used to reproduce
        # the client's bug, not a same-request fixture.
        self.question = Question.objects.create(
            assessment=self.assessment,
            question_type="single_choice",
            text="QA_M38_edit pregunta preexistente",
            explanation="si",
            points=10,
            order=0,
        )
        Answer.objects.create(
            question=self.question, text="Opcion A", is_correct=True, order=0
        )
        Answer.objects.create(
            question=self.question, text="Opcion B", is_correct=False, order=1
        )

        self.url = reverse(
            "courses:builder_edit_question",
            kwargs={
                "course_id": self.course.id,
                "assessment_id": self.assessment.id,
                "question_id": self.question.id,
            },
        )
        self.client.force_login(self.staff)

    def test_edit_persists_points_change_on_existing_question(self):
        """POST to builder_edit_question with a new Points value must persist
        it on the pre-existing question (client's exact complaint: "Puntos
        no persiste, vuelve al valor anterior")."""
        resp = self.client.post(
            self.url,
            data={
                "question_type": "single_choice",
                "text": self.question.text,
                "explanation": "QA_E2E_M38_legacy_explicacion_nueva",
                "points": "15",
                "answer_text": ["Opcion A", "Opcion B"],
                "correct_answer": ["0"],
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.question.refresh_from_db()
        self.assertEqual(self.question.points, Decimal("15.00"))
        self.assertEqual(self.question.explanation, "QA_E2E_M38_legacy_explicacion_nueva")

    def test_edit_persists_newly_added_option_on_existing_question(self):
        """POST adding a 3rd answer option to a pre-existing question must
        create it in the DB (client's other complaint: "opcion nueva no
        persiste")."""
        resp = self.client.post(
            self.url,
            data={
                "question_type": "single_choice",
                "text": self.question.text,
                "explanation": self.question.explanation,
                "points": str(self.question.points),
                "answer_text": ["Opcion A", "Opcion B", "QA_E2E_M38_opcionC"],
                "correct_answer": ["0"],
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        answers = list(Answer.objects.filter(question=self.question).order_by("order"))
        self.assertEqual(len(answers), 3)
        self.assertEqual(answers[2].text, "QA_E2E_M38_opcionC")
        self.assertTrue(
            Answer.objects.filter(question=self.question, text="QA_E2E_M38_opcionC").exists()
        )

    def test_edit_does_not_affect_unrelated_question(self):
        """Editing one existing question must not disturb a sibling question
        in the same assessment (isolation / no cross-contamination)."""
        other_question = Question.objects.create(
            assessment=self.assessment,
            question_type="short_answer",
            text="QA_M38_edit otra pregunta",
            explanation="",
            points=5,
            order=1,
        )
        self.client.post(
            self.url,
            data={
                "question_type": "single_choice",
                "text": self.question.text,
                "explanation": self.question.explanation,
                "points": "20",
                "answer_text": ["Opcion A"],
                "correct_answer": ["0"],
            },
            HTTP_HX_REQUEST="true",
        )
        other_question.refresh_from_db()
        self.assertEqual(other_question.points, Decimal("5.00"))
        self.assertEqual(other_question.text, "QA_M38_edit otra pregunta")
