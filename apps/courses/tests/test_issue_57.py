"""
Tests for SD#57 — 3 sub-items reported by the client on the course builder.

Reproduce-first reference: F2's scratch script (SPRINTS/RUN_2026-07-06_1104/
scratch_SD_57/test_repro_issue57_matching.py) confirmed the bug against a
sqlite-isolated DB BEFORE this fix. This file moves the reproduction into the
repo's test suite, now asserting the FIXED (post-#57) behavior.
"""

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.assessments.models import Assessment, AssessmentAttempt, Question
from apps.courses.models import Category, Course, Module

User = get_user_model()


class BuilderMatchingQuestionGradingIssue57Tests(TestCase):
    """SD#57.3 (PRIORITARIO): builder_add_lesson (Ruta B / quiz-inline) creaba
    preguntas de Emparejamiento sin poblar question.metadata['match_pairs'].
    AssessmentService._grade_objective_answer arma correct_map EXCLUSIVAMENTE
    desde metadata, asi que esas preguntas quedaban SIEMPRE incorrectas sin
    importar la respuesta del estudiante (cliente: /assessments/result/46/,
    att_01.png vs att_03.png -- respuesta identica a la parametrizada 1->1,
    2->2 marcada incorrecta, 0/10).

    Fix: builder_add_lesson ahora tambien escribe question.metadata tras crear
    los Answer (mismo patron que builder_add_question/builder_edit_question,
    Ruta A, que ya funcionaba)."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_sd57@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD57",
            document_number="57000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.student = User.objects.create_user(
            email="student_sd57@test.com",
            password="testpass123",
            first_name="Estudiante",
            last_name="SD57",
            document_number="57000002",
            job_position="Tecnico",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=False,
        )

        self.category = Category.objects.create(
            name="Cat SD57",
            slug="cat-sd57",
            description="cat",
            color="#0000AA",
        )
        self.course = Course.objects.create(
            code="COURSE-SD57-1",
            title="Curso SD57",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=self.category,
            created_by=self.staff,
        )
        self.module = Module.objects.create(
            course=self.course, title="Modulo SD57", description="m", order=1
        )

    def _create_matching_quiz_lesson_via_builder(self):
        """Ruta B -- camino exacto reportado por el cliente: builder de
        leccion, tipo Evaluacion (quiz), pregunta Emparejamiento inline, mismo
        payload que emite QuizBuilder.saveQuestion() (key 'pairs')."""
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_add_lesson",
            kwargs={"course_id": self.course.id, "module_id": self.module.id},
        )
        resp = self.client.post(
            url,
            data={
                "title": "QA_E2E_M57 leccion emparejamiento",
                "lesson_type": "quiz",
                "is_mandatory": "on",
                "duration": "0",
                "quiz_questions": json.dumps(
                    [
                        {
                            "type": "matching",
                            "text": "QA_E2E_M57 pregunta emparejamiento",
                            "points": 10,
                            "explanation": "",
                            "pairs": [
                                {"left": "1", "right": "1"},
                                {"left": "2", "right": "2"},
                            ],
                        }
                    ]
                ),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        assessment = Assessment.objects.get(
            lesson__module=self.module, lesson__title="QA_E2E_M57 leccion emparejamiento"
        )
        question = Question.objects.get(assessment=assessment)
        return assessment, question

    def test_builder_add_lesson_matching_question_metadata_is_populated(self):
        """FIX: la pregunta creada via Ruta B ahora queda con metadata
        poblado (match_pairs), igual que Ruta A (builder_add_question)."""
        _assessment, question = self._create_matching_quiz_lesson_via_builder()

        answers = list(question.answers.all().order_by("order"))
        self.assertEqual(len(answers), 2)
        self.assertEqual((answers[0].text, answers[0].feedback), ("1", "1"))
        self.assertEqual((answers[1].text, answers[1].feedback), ("2", "2"))

        question.refresh_from_db()
        self.assertEqual(
            question.metadata,
            {"match_pairs": [{"left": "1", "right": "1"}, {"left": "2", "right": "2"}]},
        )

    def test_student_answer_identical_to_parametrized_is_marked_correct(self):
        """FIX del bug reportado por el cliente (att_01.png/att_03.png):
        estudiante responde EXACTAMENTE igual al par parametrizado (1->1,
        2->2) y el sistema ahora lo marca CORRECTO."""
        assessment, question = self._create_matching_quiz_lesson_via_builder()

        self.client.logout()
        self.client.force_login(self.student)
        start_url = reverse("assessments:start", kwargs={"assessment_id": assessment.id})
        self.client.post(start_url)
        attempt = AssessmentAttempt.objects.get(user=self.student, assessment=assessment)

        submit_url = reverse("assessments:submit", kwargs={"attempt_id": attempt.id})
        matching_payload = json.dumps([{"left": "1", "right": "1"}, {"left": "2", "right": "2"}])
        self.client.post(
            submit_url,
            data={f"matching_{question.id}": matching_payload, "time_spent": "30"},
        )

        attempt.refresh_from_db()
        attempt_answer = attempt.attempt_answers.get(question=question)

        self.assertTrue(
            attempt_answer.is_correct,
            "El estudiante respondio exactamente lo parametrizado "
            f"({matching_payload}) y debe quedar marcado correcto -- "
            f"question.metadata={question.metadata!r} ya no esta vacio.",
        )
        self.assertEqual(attempt_answer.points_awarded, question.points)


class BuilderQuizAssessmentMaxAttemptsIssue57Tests(TestCase):
    """SD#57.2: evaluaciones sin limite de intentos. builder_add_lesson y
    builder_edit_lesson hardcodeaban max_attempts=3 al auto-crear el
    Assessment del quiz -- bypaseaban el default del modelo por completo.
    Ahora ambos call sites nacen con max_attempts=0 (ilimitado)."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_sd57b@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="SD57B",
            document_number="57000003",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.category = Category.objects.create(
            name="Cat SD57B",
            slug="cat-sd57b",
            description="cat",
            color="#00AA0A",
        )
        self.course = Course.objects.create(
            code="COURSE-SD57-2",
            title="Curso SD57B",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.PUBLISHED,
            category=self.category,
            created_by=self.staff,
        )
        self.module = Module.objects.create(
            course=self.course, title="Modulo SD57B", description="m", order=1
        )

    def test_builder_add_lesson_quiz_assessment_is_unlimited_attempts(self):
        """builder_add_lesson (Ruta B, quiz-inline): el Assessment
        auto-creado nace con max_attempts=0, no 3."""
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_add_lesson",
            kwargs={"course_id": self.course.id, "module_id": self.module.id},
        )
        resp = self.client.post(
            url,
            data={
                "title": "QA_E2E_M57B quiz nuevo",
                "lesson_type": "quiz",
                "is_mandatory": "on",
                "duration": "0",
                "quiz_questions": "[]",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        assessment = Assessment.objects.get(
            lesson__module=self.module, lesson__title="QA_E2E_M57B quiz nuevo"
        )
        self.assertEqual(assessment.max_attempts, 0)

    def test_builder_edit_lesson_autocreated_quiz_assessment_is_unlimited_attempts(self):
        """builder_edit_lesson: al editar una leccion quiz que aun NO tiene
        Assessment, el auto-creado tambien nace con max_attempts=0."""
        from apps.courses.models import Lesson

        lesson = Lesson.objects.create(
            module=self.module,
            title="QA_E2E_M57B leccion sin assessment",
            description="",
            lesson_type=Lesson.Type.QUIZ,
            order=0,
        )
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_edit_lesson",
            kwargs={"course_id": self.course.id, "module_id": self.module.id, "lesson_id": lesson.id},
        )
        resp = self.client.post(
            url,
            data={
                "title": lesson.title,
                "lesson_type": "quiz",
                "is_mandatory": "on",
                "duration": "0",
                "quiz_time_limit": "",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        assessment = Assessment.objects.get(lesson=lesson)
        self.assertEqual(assessment.max_attempts, 0)
