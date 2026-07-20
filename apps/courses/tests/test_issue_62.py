"""
Tests for SD#62 — Sprint A (Constructor de Cursos): "Duración" para
lecciones/módulos/cursos/rutas/certificados.

  A1: el bloque "Duración (minutos)" del form de ALTA de lección
      (lesson_form.html) no incluía 'quiz' en data-show-for/x-show — el
      campo quedaba oculto para lecciones tipo Evaluación aunque el modelo
      sí lo guarda. Fix: agregar 'quiz' a ambas listas.

  A2: LessonBuilderForm no exigía duration>0 -- el 84% de las lecciones en
      prod tienen duration=0. Fix: clean_duration() exige duration>0 para
      todo lesson_type EXCEPTO 'attendance' (usa scheduled_date, SD#57.1).
      HALLAZGO de F2 confirmado aquí: builder_edit_lesson, al re-renderizar
      lesson_item.html completo (hx-swap=outerHTML) tras un error, perdía
      el estado Alpine `editingLesson` (reseteado a false por el x-data
      fresco), dejando el <template x-if="editingLesson"> — que contiene el
      mensaje de error — fuera del DOM. Fix: inicializar `editingLesson`
      desde `lesson_form.errors` en el x-data raíz de lesson_item.html.

  A3: Module.duration_hours (nueva @property, análoga a Course.duration_
      hours) + badge en vivo en module_card.html/course_builder.html,
      refrescado sin reload vía un fragmento OOB (hx-swap-oob) que
      builder_add_lesson/builder_edit_lesson/builder_delete_lesson
      agregan a su respuesta HTMX.

  A4 (parcial, course_list/course_detail): unifica course_detail.html y
      course_list.html para usar `course.duration_hours` (ya existe y es
      correcto) en vez de `course.total_duration` (minutos crudos). El
      resto de A4 (LearningPath.duration_hours, certificados) tiene tests
      dedicados en apps/learning_paths/tests/test_issue_62.py y
      apps/certifications/tests/test_issue_62.py.

NOTA (detect_hot_files.py): apps/courses/tests.py es compartido entre
varios issues de este RUN — este archivo de test es POR-ISSUE
(test_issue_62.py), nunca se apendea a tests.py.
"""

from datetime import date

from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.forms import LessonBuilderForm
from apps.courses.models import Category, Course, Lesson, Module

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


# --------------------------------------------------------------------------
# A2 — duration obligatorio (>0) en el Constructor, excepto attendance.
# --------------------------------------------------------------------------
class LessonBuilderFormDurationRequiredTests(TestCase):
    """A2: LessonBuilderForm.clean_duration() exige duration>0 para todo
    lesson_type salvo 'attendance'."""

    def test_edge_video_duration_zero_rejected(self):
        form = LessonBuilderForm(
            data={"title": "Video de prueba", "lesson_type": Lesson.Type.VIDEO, "duration": "0"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("duration", form.errors)
        self.assertIn("duraci", form.errors["duration"][0].lower())

    def test_edge_quiz_duration_empty_rejected(self):
        form = LessonBuilderForm(
            data={"title": "Quiz de prueba", "lesson_type": Lesson.Type.QUIZ, "duration": ""}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("duration", form.errors)

    def test_happy_path_attendance_duration_zero_not_required(self):
        """No debe romper SD#57.1: attendance usa scheduled_date, no
        duration -- duration=0 (el valor por defecto del modelo) debe
        seguir siendo valido para este tipo."""
        form = LessonBuilderForm(
            data={
                "title": "Asistencia",
                "lesson_type": Lesson.Type.ATTENDANCE,
                "duration": "0",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_happy_path_video_duration_positive_accepted(self):
        form = LessonBuilderForm(
            data={"title": "Video ok", "lesson_type": Lesson.Type.VIDEO, "duration": "15"}
        )
        self.assertTrue(form.is_valid(), form.errors)


class BuilderEditLessonDurationRequiredViewTests(TestCase):
    """A2 (view level): editar una leccion legacy con duration=0 sin
    corregirla falla con un mensaje claro (no una excepcion 500), y el
    mensaje de error queda VISIBLE en el HTML devuelto (hallazgo de
    visibilidad Alpine documentado en el sub-item)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff_user()
        cls.course = _make_course(cls.staff)
        cls.module = Module.objects.create(
            course=cls.course, title="Modulo 1", description="m", order=0
        )
        # Leccion legacy real: duration=0, tal como el 84% de las lecciones
        # en prod (riesgo documentado en el PLAN de SD#62).
        cls.lesson = Lesson.objects.create(
            module=cls.module,
            title="Leccion legacy",
            description="",
            lesson_type=Lesson.Type.VIDEO,
            duration=0,
            order=0,
        )

    def setUp(self):
        self.client = Client()

    def test_edge_edit_legacy_lesson_duration_zero_fails_visibly_no_500(self):
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_edit_lesson",
            args=[self.course.id, self.module.id, self.lesson.id],
        )
        response = self.client.post(
            url,
            data={
                "title": self.lesson.title,
                "lesson_type": Lesson.Type.VIDEO,
                "duration": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # editingLesson debe inicializar en `true` cuando la respuesta trae
        # lesson_form.errors -- si no, el <template x-if="editingLesson">
        # (que contiene el mensaje de error) queda fuera del DOM tras el
        # hx-swap=outerHTML y el usuario no ve por que no guardo.
        self.assertIn("editingLesson: true", content)
        self.assertIn("alert-error", content)
        self.assertIn("duraci", content.lower())

    def test_happy_path_edit_lesson_with_positive_duration_succeeds(self):
        """Regresion: corregir la duracion legacy SI debe guardar bien
        (y volver a editingLesson: false, modo vista)."""
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_edit_lesson",
            args=[self.course.id, self.module.id, self.lesson.id],
        )
        response = self.client.post(
            url,
            data={
                "title": self.lesson.title,
                "lesson_type": Lesson.Type.VIDEO,
                "duration": "20",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.duration, 20)
        content = response.content.decode()
        self.assertIn("editingLesson: false", content)


# --------------------------------------------------------------------------
# A3 — Module.duration_hours + contador en vivo (OOB) en el builder.
# --------------------------------------------------------------------------
class ModuleDurationHoursTests(TestCase):
    """A3 (modelo): Module.duration_hours, analogo a Course.duration_hours
    (mismos valores/redondeo usados en apps/courses/tests/test_issue_43.py)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff_user()
        cls.course = _make_course(cls.staff)

    def test_happy_path_zero_lessons_is_zero(self):
        module = Module.objects.create(
            course=self.course, title="Vacio", description="", order=0
        )
        self.assertEqual(module.duration_hours, 0.0)

    def test_edge_sum_and_round_matches_course_duration_hours_logic(self):
        module = Module.objects.create(
            course=self.course, title="Con lecciones", description="", order=1
        )
        # 40 + 60 = 100 min -> 1.6666... -> redondea a 1.7 (mismo caso que
        # test_issue_43.py test_duration_hours_rounds_to_one_decimal).
        Lesson.objects.create(
            module=module, title="L1", lesson_type=Lesson.Type.VIDEO, duration=40, order=0
        )
        Lesson.objects.create(
            module=module, title="L2", lesson_type=Lesson.Type.VIDEO, duration=60, order=1
        )
        self.assertEqual(module.duration_hours, 1.7)


class BuilderDurationOobFragmentTests(TestCase):
    """A3 (vista): builder_add_lesson/builder_edit_lesson/
    builder_delete_lesson agregan un fragmento OOB (hx-swap-oob) que
    refresca los badges de horas del modulo y del curso."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff_user()
        cls.course = _make_course(cls.staff)
        cls.module = Module.objects.create(
            course=cls.course, title="Modulo 1", description="m", order=0
        )

    def setUp(self):
        self.client = Client()

    def test_happy_path_add_lesson_response_includes_updated_oob_totals(self):
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_add_lesson", args=[self.course.id, self.module.id]
        )
        response = self.client.post(
            url,
            data={
                "title": "Leccion 1",
                "lesson_type": Lesson.Type.VIDEO,
                "duration": "30",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'id="module-duration-{self.module.id}"', content)
        self.assertIn('id="course-duration-badge"', content)
        self.assertIn('hx-swap-oob="true"', content)
        # 30 min = 0.5 h -- LANGUAGE_CODE=es-co localiza el separador
        # decimal a coma (mismo patron que test_issue_43.py).
        self.assertIn("0,5 h", content)

    def test_edge_delete_lesson_response_includes_oob_totals_reflecting_removal(self):
        lesson_a = Lesson.objects.create(
            module=self.module,
            title="A borrar",
            lesson_type=Lesson.Type.VIDEO,
            duration=60,
            order=0,
        )
        self.client.force_login(self.staff)
        url = reverse(
            "courses:builder_delete_lesson",
            args=[self.course.id, self.module.id, lesson_a.id],
        )
        response = self.client.post(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'id="module-duration-{self.module.id}"', content)
        # El modulo quedo sin lecciones tras el borrado -> 0.0 h.
        self.assertIn("0,0 h", content)


# --------------------------------------------------------------------------
# A4 (parcial) — course_detail.html / course_list.html usan duration_hours.
# --------------------------------------------------------------------------
class CourseDetailListDurationHoursTests(TestCase):
    """A4: course_detail.html y course_list.html renderizan
    `course.duration_hours` (horas) en vez de `course.total_duration`
    (minutos crudos)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff_user()

    def setUp(self):
        self.client = Client()

    def test_happy_path_course_detail_shows_hours(self):
        course = _make_course(self.staff, status=Course.Status.PUBLISHED)
        module = Module.objects.create(
            course=course, title="M1", description="", order=0
        )
        Lesson.objects.create(
            module=module, title="L1", lesson_type=Lesson.Type.VIDEO, duration=90, order=0
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("courses:detail", args=[course.id]))

        self.assertEqual(response.status_code, 200)
        # 90 min = 1.5 h; LANGUAGE_CODE=es-co localiza a coma. La fila
        # "Duracion total" del sidebar ahora usa duration_hours -- NOTA:
        # el listado de lecciones sigue mostrando "{{ lesson.duration }}
        # min" por lección individual (course_detail.html:166), fuera de
        # alcance de A4 (esa es la duracion de la leccion, no el total).
        self.assertContains(response, "1,5 h")

    def test_edge_course_list_zero_duration_course_does_not_crash(self):
        """Curso publicado sin lecciones (duration_hours=0.0) no debe
        romper course_list.html."""
        _make_course(self.staff, status=Course.Status.PUBLISHED)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("courses:list"))

        self.assertEqual(response.status_code, 200)
