"""
Tests for SD#59 -- REPROCESO (bounce, categoria FIX_NO_FUNCIONO), gap B:
course_detail nunca mostraba un link de descarga del certificado.

F2 confirmo con un fetch en vivo de la URL EXACTA citada por el validador
(/courses/64/) que `templates/courses/partials/enrollment_status.html`
solo renderiza el texto "Curso completado" cuando
`enrollment.status == 'completed'` -- 0 ocurrencias de un <a> hacia
`certifications:download` en TODO el HTML fuente. La unica forma de
descargar el PDF era navegar manualmente a /certifications/
(my_certificates.html).

Fix: `apps/courses/views.py::course_detail` agrega al context el
Certificate ISSUED mas reciente para (request.user, course) (mismo
criterio que `certifications/signals.py`), y el partial
`enrollment_status.html` renderiza un link "Descargar certificado" hacia
`certifications:download` cuando existe. Si el curso esta completado pero
el certificado aun no fue emitido (status='pending', PDF renderizandose),
no rompe la vista -- muestra un aviso, igual patron que
`my_certificates.html` (SD#43).
"""

from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate
from apps.courses.models import Category, Course, Enrollment, Lesson, Module

_SEQ = [9000]


def _make_user(rol=None, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue59_dl_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "DL59",
        "document_number": f"7{n:08d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator):
    _SEQ[0] += 1
    n = _SEQ[0]
    category = Category.objects.create(
        name=f"Cat DL59 {n}", slug=f"cat-dl59-{n}", description="c", color="#123456"
    )
    course = Course.objects.create(
        code=f"ISSUE59-DL-{n}",
        title=f"Curso DL 59 {n}",
        description="desc",
        objectives="obj",
        course_type=Course.Type.MANDATORY,
        status=Course.Status.PUBLISHED,
        category=category,
        created_by=creator,
    )
    module = Module.objects.create(course=course, title="M1", description="d", order=0)
    Lesson.objects.create(
        module=module,
        title="L1",
        lesson_type=Lesson.Type.VIDEO,
        duration=10,
        order=0,
    )
    return course


def _make_certificate(user, course, status=Certificate.Status.ISSUED, issued_at=None):
    _SEQ[0] += 1
    n = _SEQ[0]
    return Certificate.objects.create(
        user=user,
        course=course,
        certificate_number=f"SD-DL59-{n:08d}",
        status=status,
        issued_at=issued_at,
        expires_at=(issued_at + timedelta(days=365)) if issued_at else None,
    )


class CourseDetailCertificateDownloadLinkTest(TestCase):
    """Gap B: course_detail debe mostrar el link de descarga cuando el
    curso esta completado Y hay un certificado ISSUED para ese (user,
    course) -- reproduce y valida el fix contra la URL exacta que citó
    el validador (course detail, no my_certificates)."""

    def setUp(self):
        self.client = Client()
        self.admin = _make_user(rol=User.Rol.ADMINISTRADOR, is_staff=True)
        self.course = _make_course(self.admin)
        self.url = reverse("courses:detail", args=[self.course.id])

    def test_happy_path_completed_with_issued_certificate_shows_download_link(self):
        """Usuario CUALQUIERA (no solo admin/superuser) con curso
        completado y certificado ya emitido ve el link de descarga en
        course_detail -- el gap B reportado por el cliente."""
        ejecutor = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=ejecutor,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        certificate = _make_certificate(ejecutor, self.course, issued_at=timezone.now())

        self.client.force_login(ejecutor)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        download_url = reverse("certifications:download", args=[certificate.id])
        self.assertContains(response, download_url)
        self.assertContains(response, "Descargar certificado")

    def test_happy_path_coordinador_role_also_sees_link(self):
        """Cubre 'todos los roles' del pedido original del cliente --
        no solo Ejecutor, tambien Coordinador ve su propio certificado."""
        coordinador = _make_user(rol=User.Rol.COORDINADOR)
        Enrollment.objects.create(
            user=coordinador,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        certificate = _make_certificate(coordinador, self.course, issued_at=timezone.now())

        self.client.force_login(coordinador)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        download_url = reverse("certifications:download", args=[certificate.id])
        self.assertContains(response, download_url)

    def test_legacy_certificate_issued_before_this_fix_still_shows_link(self):
        """Dato LEGACY (>= 1 registro pre-existente al cambio): un
        certificado ya emitido HACE TIEMPO (antes de este deploy, como el
        id=51 real de prod citado por F2) tambien debe verse reflejado en
        course_detail una vez aplicado el fix -- no solo certificados
        creados despues."""
        user = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        old_issued_at = timezone.now() - timedelta(days=30)
        legacy_certificate = _make_certificate(user, self.course, issued_at=old_issued_at)

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        download_url = reverse("certifications:download", args=[legacy_certificate.id])
        self.assertContains(response, download_url)

    def test_edge_completed_without_issued_certificate_yet_does_not_break_view(self):
        """Curso completado pero el certificado sigue 'pending' (PDF
        renderizandose, unos segundos tras completar) -- la vista NO debe
        romperse ni mostrar un link roto; mismo patron que
        my_certificates.html (SD#43)."""
        user = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        _make_certificate(user, self.course, status=Certificate.Status.PENDING, issued_at=None)

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Descargar certificado")
        self.assertContains(response, "Certificado en generación")

    def test_edge_completed_with_zero_certificates_does_not_break_view(self):
        """Completado pero sin NINGUN Certificate creado todavia (race de
        timing del signal) -- tampoco rompe, tampoco muestra link."""
        user = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Descargar certificado")

    def test_edge_not_completed_never_shows_link_or_pending_notice(self):
        """Curso en progreso (no completado): ni el link ni el aviso de
        'en generacion' deben aparecer -- comportamiento inalterado."""
        user = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=user,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            progress=40,
        )

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Descargar certificado")
        self.assertNotContains(response, "Certificado en generación")

    def test_edge_other_users_certificate_is_not_shown(self):
        """El certificado ISSUED de OTRO usuario en el mismo curso no se
        filtra al contexto de este usuario (scoping correcto por
        request.user, no solo por course)."""
        other_user = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=other_user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )
        other_certificate = _make_certificate(other_user, self.course, issued_at=timezone.now())

        viewer = _make_user(rol=User.Rol.EJECUTOR)
        Enrollment.objects.create(
            user=viewer,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )

        self.client.force_login(viewer)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        other_download_url = reverse("certifications:download", args=[other_certificate.id])
        self.assertNotContains(response, other_download_url)
        # El propio viewer no tiene certificado emitido -> aviso, no link.
        self.assertContains(response, "Certificado en generación")

    def test_edge_not_enrolled_view_unaffected(self):
        """Usuario NO inscrito: la rama de 'Inscribete' sigue intacta, sin
        tocar el contexto de certificado (issued_certificate queda None,
        pero enrollment tambien es None asi que ni se evalua)."""
        stranger = _make_user(rol=User.Rol.EJECUTOR)

        self.client.force_login(stranger)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inscríbete para acceder al contenido")
        self.assertNotContains(response, "Descargar certificado")
