"""
Tests for issue #58 sub-item A7 — filtrado de datos de Certificados por rol
de acceso (RBAC, ver `apps/accounts/permissions.py` A4 y `User.rol`/
`User.supervisor` A1):

  - Ejecutor: solo sus propios certificados (`my_certificates`, sin cambio
    de comportamiento default).
  - Coordinador: además puede pedir `?scope=equipo` — certificados de los
    usuarios que reportan a él vía `User.supervisor` FK (`related_name=
    'equipo'`). NO ve el equipo de otro Coordinador.
  - Administrador: además puede pedir `?scope=todos` — todos los
    certificados del sistema, incluidos los de usuarios "legacy" (creados
    antes del backfill de `rol`, con `rol=None`).
  - `certificate_detail` / `certificate_download`: el bypass de ownership
    ahora también permite a un Coordinador ver/descargar el certificado de
    un miembro de su equipo (antes de A7 solo Administrador podía saltarse
    ownership).

Un scope no autorizado (ej. Ejecutor pidiendo `?scope=equipo`, o
Coordinador pidiendo `?scope=todos`) SIEMPRE degrada a `mio` — nunca se
sirve un scope de mayor alcance del que el `rol` autoriza, para no abrir
una fuga de datos por manipulación del query param.
"""

import itertools
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.models import Certificate
from apps.courses.models import Course

_SEQ = itertools.count(1)


def _make_user(*, rol=None, supervisor=None, is_staff=False, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a7_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A7",
        "document_type": "CC",
        "document_number": f"71{n:07d}",
        "job_position": "Técnico",
        "job_profile": None,
        "hire_date": date(2022, 1, 1),
        "is_staff": is_staff,
        "rol": rol,
        "supervisor": supervisor,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class _A7BaseTestCase(TestCase):
    """Fixture compartida: 1 curso + 2 equipos (Coordinador→2 Ejecutores
    cada uno) + 1 Administrador + 1 usuario "legacy" (rol=None, is_staff=True,
    simula un registro que existía antes del backfill de A1/A4) — cada uno
    con exactamente 1 certificado propio."""

    @classmethod
    def setUpTestData(cls):
        cls.administrador = _make_user(
            rol=User.Rol.ADMINISTRADOR, is_staff=True, first_name="Admin"
        )

        cls.course = Course.objects.create(
            code="A7-CERT-001",
            title="Curso RBAC A7",
            created_by=cls.administrador,
            status=Course.Status.PUBLISHED,
            validity_months=12,
        )
        cls.coordinador1 = _make_user(rol=User.Rol.COORDINADOR, first_name="CoordUno")
        cls.coordinador2 = _make_user(rol=User.Rol.COORDINADOR, first_name="CoordDos")
        cls.ejecutor1 = _make_user(
            rol=User.Rol.EJECUTOR, supervisor=cls.coordinador1, first_name="EjecUno"
        )
        cls.ejecutor2 = _make_user(
            rol=User.Rol.EJECUTOR, supervisor=cls.coordinador1, first_name="EjecDos"
        )
        cls.ejecutor3 = _make_user(
            rol=User.Rol.EJECUTOR, supervisor=cls.coordinador2, first_name="EjecTres"
        )
        # "Legacy": is_staff=True heredado de job_profile==ADMINISTRADOR
        # histórico, pero el backfill de A1 aún no le asignó `rol` explícito
        # (bucket "sin sugerencia confiable" del PLAN) — dato real
        # pre-existente al feature, no un fixture artificial.
        cls.legacy_user = _make_user(rol=None, is_staff=True, first_name="Legacy")

        cls.cert_admin = cls._make_cert(cls.administrador, "ADMIN")
        cls.cert_coord1 = cls._make_cert(cls.coordinador1, "COORD1")
        cls.cert_e1 = cls._make_cert(cls.ejecutor1, "E1")
        cls.cert_e2 = cls._make_cert(cls.ejecutor2, "E2")
        cls.cert_e3 = cls._make_cert(cls.ejecutor3, "E3")
        cls.cert_legacy = cls._make_cert(cls.legacy_user, "LEGACY")

    @classmethod
    def _make_cert(cls, user, suffix):
        return Certificate.objects.create(
            user=user,
            course=cls.course,
            certificate_number=f"CERT-A7-{suffix}",
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
        )


class MyCertificatesScopeFilteringTests(_A7BaseTestCase):
    """`my_certificates` — filtrado por `scope` (propio/equipo/todos)."""

    # --- Ejecutor: propio, default y ante manipulación del query param ---

    def test_ejecutor_ve_solo_propio_por_default(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(reverse("certifications:my_certificates"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "mio")
        self.assertFalse(response.context["can_view_equipo"])
        self.assertEqual(list(response.context["certificates"]), [self.cert_e1])

    def test_ejecutor_scope_equipo_manipulado_cae_a_mio_sin_fuga(self):
        """Edge case: un Ejecutor pide ?scope=equipo por URL — no debe ver
        ni su "equipo" (no tiene, no es Coordinador) ni ningún otro dato."""
        self.client.force_login(self.ejecutor1)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "equipo"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "mio")
        self.assertEqual(list(response.context["certificates"]), [self.cert_e1])

    # --- Coordinador: equipo vía supervisor FK ---

    def test_coordinador_scope_equipo_ve_a_su_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "equipo"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "equipo")
        self.assertTrue(response.context["can_view_equipo"])
        certs = set(response.context["certificates"])
        self.assertEqual(certs, {self.cert_e1, self.cert_e2})

    def test_coordinador_no_ve_certificados_de_otro_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "equipo"}
        )

        certs = set(response.context["certificates"])
        self.assertNotIn(self.cert_e3, certs)  # equipo de coordinador2
        self.assertNotIn(self.cert_legacy, certs)
        self.assertNotIn(self.cert_admin, certs)
        self.assertNotIn(self.cert_coord1, certs)  # el propio no cuenta como "equipo"

    def test_coordinador_scope_todos_no_autorizado_cae_a_mio(self):
        """Edge case: un Coordinador pide ?scope=todos — no está autorizado
        (solo Administrador), degrada a `mio` (su propio certificado)."""
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "todos"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "mio")
        self.assertEqual(list(response.context["certificates"]), [self.cert_coord1])

    # --- Administrador: todos, incluido dato legacy ---

    def test_administrador_scope_todos_ve_todos_incluyendo_legacy(self):
        """Incluye el certificado de un usuario `rol=None` (legacy,
        pre-backfill) — el scope 'todos' no debe filtrar por `rol` del
        dueño, solo por el `rol` de quien lo pide."""
        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "todos"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "todos")
        self.assertTrue(response.context["can_view_todos"])
        certs = set(response.context["certificates"])
        self.assertEqual(
            certs,
            {
                self.cert_admin,
                self.cert_coord1,
                self.cert_e1,
                self.cert_e2,
                self.cert_e3,
                self.cert_legacy,
            },
        )

    def test_administrador_scope_equipo_ve_solo_su_supervision_directa(self):
        """Distinto de 'todos': un Administrador sin nadie a cargo
        (supervisor=administrador) ve la lista de equipo vacía."""
        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("certifications:my_certificates"), {"scope": "equipo"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "equipo")
        self.assertEqual(list(response.context["certificates"]), [])


class CertificateDetailAuthzTests(_A7BaseTestCase):
    """`certificate_detail` — bypass de ownership extendido a Coordinador
    de equipo (antes de A7 solo Administrador)."""

    def test_coordinador_ve_detalle_de_certificado_de_su_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:detail", args=[self.cert_e1.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_coordinador_bloqueado_en_detalle_de_otro_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:detail", args=[self.cert_e3.id])
        )
        self.assertEqual(response.status_code, 403)

    def test_administrador_ve_detalle_de_cualquier_certificado(self):
        self.client.force_login(self.administrador)
        response = self.client.get(
            reverse("certifications:detail", args=[self.cert_legacy.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_ejecutor_bloqueado_en_detalle_ajeno(self):
        self.client.force_login(self.ejecutor1)
        response = self.client.get(
            reverse("certifications:detail", args=[self.cert_e2.id])
        )
        self.assertEqual(response.status_code, 403)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CertificateDownloadAuthzTests(_A7BaseTestCase):
    """`certificate_download` — mismo criterio ownership/rol que
    `certificate_detail` (A7 lo extendió ahí también: dejar el botón
    "Descargar PDF" visible en el detalle de un Coordinador pero 403-eando
    la descarga real sería un hueco visible)."""

    # Minimal valid PDF (header + EOF).
    _PDF = b"%PDF-1.4\n%test a7\n" + b"x" * 200 + b"\n%%EOF\n"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for cert in (cls.cert_e1, cls.cert_e3):
            cert.certificate_file.save(
                f"{cert.certificate_number}.pdf",
                ContentFile(cls._PDF),
                save=True,
            )

    def test_coordinador_descarga_certificado_de_su_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:download", args=[self.cert_e1.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_coordinador_no_descarga_certificado_de_otro_equipo(self):
        self.client.force_login(self.coordinador1)
        response = self.client.get(
            reverse("certifications:download", args=[self.cert_e3.id])
        )
        self.assertEqual(response.status_code, 403)
