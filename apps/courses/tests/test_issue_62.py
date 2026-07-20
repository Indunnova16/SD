"""
Tests for SD#62 — Sprint A (Constructor de Cursos): "Duración" para
lecciones/módulos/cursos/rutas/certificados.

  A1: el bloque "Duración (minutos)" del form de ALTA de lección
      (lesson_form.html) no incluía 'quiz' en data-show-for/x-show — el
      campo quedaba oculto para lecciones tipo Evaluación aunque el modelo
      sí lo guarda. Fix: agregar 'quiz' a ambas listas.

NOTA (detect_hot_files.py): apps/courses/tests.py es compartido entre
varios issues de este RUN — este archivo de test es POR-ISSUE
(test_issue_62.py), nunca se apendea a tests.py.
"""

from datetime import date

from django.template.loader import render_to_string
from django.test import TestCase

from apps.accounts.models import User
from apps.courses.models import Category, Course, Module

_SEQ = [6200]


def _make_staff_user(**overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue62_staff_{n}@test.com",
        "password": "testpass123",
        "first_name": f"Staff{n}",
        "last_name": "SD62",
        "document_number": f"62{n:08d}",
        "job_position": "Admin",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": True,
        "rol": User.Rol.ADMINISTRADOR,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat SD62 {n}", slug=f"cat-sd62-{n}", description="c", color="#123456"
    )
    defaults = {
        "code": f"ISSUE62-{n}",
        "title": f"Curso SD62 {n}",
        "description": "desc",
        "objectives": "obj",
        "course_type": Course.Type.MANDATORY,
        "status": Course.Status.DRAFT,
        "category": category,
        "created_by": creator,
    }
    defaults.update(overrides)
    return Course.objects.create(**defaults)


# --------------------------------------------------------------------------
# A1 — Duracion visible para lecciones tipo Evaluacion (quiz) en el form de
# alta.
# --------------------------------------------------------------------------
class LessonFormQuizDurationVisibilityTests(TestCase):
    """A1: lesson_form.html (is_new=True) debe incluir 'quiz' en el
    data-show-for/x-show del bloque Duracion, junto con los demas tipos que
    ya lo mostraban."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff_user()
        cls.course = _make_course(cls.staff)
        cls.module = Module.objects.create(
            course=cls.course, title="Modulo 1", description="m", order=0
        )

    def test_happy_path_quiz_included_in_duration_show_for(self):
        html = render_to_string(
            "courses/partials/builder/lesson_form.html",
            {"is_new": True, "course": self.course, "module": self.module},
        )
        # El bloque de Duracion debe listar 'quiz' tanto en el atributo
        # data-show-for (usado por JS legacy) como en el array x-show de
        # Alpine, junto con los demas tipos ya soportados.
        self.assertIn(
            'data-show-for="video,pdf,text,scorm,audio,interactive,presential,quiz"',
            html,
        )
        self.assertIn(
            "['video','pdf','text','scorm','audio','interactive','presential','quiz']"
            ".includes(lessonType)",
            html,
        )

    def test_edge_other_conditional_fields_untouched(self):
        """Regresion: el bloque Descripcion (otro conditional-field que SI
        debe seguir oculto para quiz) no debe haber sido tocado por error."""
        html = render_to_string(
            "courses/partials/builder/lesson_form.html",
            {"is_new": True, "course": self.course, "module": self.module},
        )
        self.assertIn(
            "['video','pdf','text','scorm','audio','interactive','presential']"
            ".includes(lessonType)",
            html,
        )
