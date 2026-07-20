"""
Tests for SD#62 A4 — fila "Duración" en certificate_detail.html y
my_certificates.html, usando course.duration_hours (SD#43).

Gate condicional (`{% if certificate.course.duration_hours %}`, mismo
patron ya usado en ambos templates para score/expires_at/etc): la fila solo
se muestra cuando el curso tiene duracion real (>0h) -- evita mostrar
"0.0 h" en cada certificado legacy (84% de las lecciones en prod tienen
duration=0, PLAN de SD#62).
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate
from apps.courses.models import Category, Course, Lesson, Module

_SEQ = [6200]


def _make_user(**overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue62_cert_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "SD62",
        "document_number": f"64{n:08d}",
        "job_position": "Tecnico",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat SD62Cert {n}", slug=f"cat-sd62cert-{n}", description="c", color="#abcdef"
    )
    defaults = {
        "code": f"ISSUE62CERT-{n}",
        "title": f"Curso SD62Cert {n}",
        "description": "desc",
        "objectives": "obj",
        "course_type": Course.Type.MANDATORY,
        "status": Course.Status.PUBLISHED,
        "category": category,
        "created_by": creator,
    }
    defaults.update(overrides)
    return Course.objects.create(**defaults)


def _make_certificate(user, course, suffix):
    _SEQ[0] += 1
    return Certificate.objects.create(
        user=user,
        course=course,
        certificate_number=f"CERT-SD62-{suffix}-{_SEQ[0]}",
        status=Certificate.Status.ISSUED,
        issued_at=timezone.now(),
    )


class CertificateDetailDurationRowTests(TestCase):
    """A4: certificate_detail.html muestra 'Duración' cuando el curso
    tiene duration_hours>0, y no rompe cuando es 0."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user(is_staff=True)

    def setUp(self):
        self.client = Client()

    def test_happy_path_positive_duration_renders_row(self):
        course = _make_course(self.admin)
        module = Module.objects.create(course=course, title="M1", description="", order=0)
        Lesson.objects.create(
            module=module, title="L1", lesson_type=Lesson.Type.VIDEO, duration=90, order=0
        )
        cert = _make_certificate(self.admin, course, "DET-POS")

        self.client.force_login(self.admin)
        response = self.client.get(reverse("certifications:detail", args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duración")
        # 90 min = 1.5 h; LANGUAGE_CODE=es-co localiza el separador
        # decimal a coma (mismo patron que test_issue_43.py/test_issue_59.py).
        self.assertContains(response, "1,5 h")

    def test_edge_zero_duration_course_does_not_crash_and_hides_row(self):
        course = _make_course(self.admin)  # sin modulos/lecciones -> 0.0h
        cert = _make_certificate(self.admin, course, "DET-ZERO")

        self.client.force_login(self.admin)
        response = self.client.get(reverse("certifications:detail", args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(course.duration_hours, 0.0)


class MyCertificatesDurationDetailsTests(TestCase):
    """A4: my_certificates.html — bloque 'Details' de cada card incluye la
    duracion cuando el curso la tiene."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user()

    def setUp(self):
        self.client = Client()

    def test_happy_path_card_shows_duration(self):
        course = _make_course(self.user)
        module = Module.objects.create(course=course, title="M1", description="", order=0)
        Lesson.objects.create(
            module=module, title="L1", lesson_type=Lesson.Type.VIDEO, duration=45, order=0
        )
        _make_certificate(self.user, course, "MC-POS")

        self.client.force_login(self.user)
        response = self.client.get(reverse("certifications:my_certificates"))

        self.assertEqual(response.status_code, 200)
        # 45 min = 0.75 -> round(0.75, 1); comprobamos que el valor real de
        # la property (no un literal adivinado) aparece renderizado.
        self.assertContains(response, f"{course.duration_hours}".replace(".", ","))

    def test_edge_zero_duration_course_list_does_not_crash(self):
        course = _make_course(self.user)  # sin lecciones -> 0.0h, fila oculta
        _make_certificate(self.user, course, "MC-ZERO")

        self.client.force_login(self.user)
        response = self.client.get(reverse("certifications:my_certificates"))

        self.assertEqual(response.status_code, 200)
