"""
Tests for SD#59 -- REPROCESO (bounce, categoria FIX_NO_FUNCIONO), gap A:
logo del CertificateTemplate por defecto.

Migration 0004 (commit ae06f22, 2026-07-10) sembro 1 CertificateTemplate
activo pero con el adjunto EQUIVOCADO del cliente: att_01.png (una captura
COMPLETA de un certificado, con chrome de navegador, MD5
fda0eb21a8e7bb8737b82fe44389f03b), en vez del logo real de la empresa
(icono de torre electrica + texto "SD S.A.S. Salomon Duran", att_04/05,
MD5 9148226dea74ef3fea2d7044e7d381a8). El comentario de cierre 2026-07-10
afirmo por error que ese MD5 (fda0eb2...) era "el logo real" -- ambas
imagenes estaban adjuntas al mismo comentario del cliente y nunca se
compararon visualmente.

Confirmado en la ronda de F2 de este sprint con evidencia mas fuerte: la
imagen REALMENTE EMBEBIDA en un certificado YA EMITIDO en prod (id=51),
extraida con `pdfimages`, coincide pixel a pixel con el mockup, no con el
logo real.

Esta suite prueba la migracion 0005 (RunPython) DIRECTAMENTE contra una
fila que replica el estado EXACTO que existe en prod desde el 2026-07-10
(name="Plantilla oficial S.D. S.A.S.", is_active=True, logo apuntando al
asset roto sd_sas_logo.png) -- dato "legacy" que existia ANTES de este fix,
no un fixture nuevo inventado por este test.
"""

import importlib
import os

from django.apps import apps as real_apps
from django.core.files.base import ContentFile
from django.test import TestCase

from apps.certifications.models import CertificateTemplate

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations", "assets")
_BROKEN_ASSET_PATH = os.path.join(_ASSETS_DIR, "sd_sas_logo.png")
_REAL_ASSET_PATH = os.path.join(_ASSETS_DIR, "sd_sas_logo_v2_real.png")

TEMPLATE_NAME = "Plantilla oficial S.D. S.A.S."


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class DefaultTemplateLogoFixMigrationTest(TestCase):
    """
    Corre la funcion RunPython de la migracion 0005 directamente contra
    una fila LEGACY (>= 1 registro pre-existente al cambio, no solo
    fixtures propias): una CertificateTemplate en el mismo estado exacto
    en que quedo sembrada en prod por la migracion 0004 el 2026-07-10 --
    is_active=True, logo apuntando al asset roto.
    """

    def setUp(self):
        migration_module = importlib.import_module(
            "apps.certifications.migrations.0005_fix_default_certificate_template_logo"
        )
        self.fix_template_logo = migration_module.fix_template_logo

        # Neutralizar cualquier fila sembrada por 0004+0005 al construir la
        # BD de test, para controlar el estado "legacy" de forma
        # deterministica en cada test (mismo patron que
        # test_issue_59.CertificateGenerationUsesActiveTemplateLogoTest).
        CertificateTemplate.objects.all().delete()

        # LEGACY ROW: replica el estado real de prod (id=9) desde el
        # 2026-07-10 -- sembrada por 0004 con el adjunto equivocado.
        self.legacy_template = CertificateTemplate.objects.create(
            name=TEMPLATE_NAME,
            description="Plantilla por defecto sembrada por SD#59 (A2)",
            is_active=True,
        )
        self.legacy_template.logo.save(
            "sd_sas_logo.png",
            ContentFile(_read_bytes(_BROKEN_ASSET_PATH)),
            save=True,
        )

    def test_happy_path_fix_replaces_broken_logo_with_real_asset(self):
        """La fila legacy con el mockup queda apuntando al asset real tras
        correr la migracion, con un filename NUEVO y distinto al roto."""
        # Precondicion: efectivamente arranca en el estado roto.
        self.assertIn("sd_sas_logo", self.legacy_template.logo.name)
        self.assertNotIn("v2_real", self.legacy_template.logo.name)
        with self.legacy_template.logo.open("rb") as f:
            self.assertEqual(f.read(), _read_bytes(_BROKEN_ASSET_PATH))

        self.fix_template_logo(real_apps, None)

        self.legacy_template.refresh_from_db()
        self.assertIn("sd_sas_logo_v2_real", self.legacy_template.logo.name)
        with self.legacy_template.logo.open("rb") as f:
            fixed_content = f.read()
        self.assertEqual(fixed_content, _read_bytes(_REAL_ASSET_PATH))
        # Nunca debe quedar el contenido del mockup.
        self.assertNotEqual(fixed_content, _read_bytes(_BROKEN_ASSET_PATH))

    def test_idempotent_second_run_is_noop(self):
        """Correr la migracion 2 veces no rompe ni re-descarga el asset --
        el segundo `migrate` (re-deploy, retry) es un no-op seguro."""
        self.fix_template_logo(real_apps, None)
        self.legacy_template.refresh_from_db()
        first_logo_name = self.legacy_template.logo.name

        self.fix_template_logo(real_apps, None)
        self.legacy_template.refresh_from_db()

        self.assertEqual(self.legacy_template.logo.name, first_logo_name)
        self.assertIn("sd_sas_logo_v2_real", self.legacy_template.logo.name)

    def test_edge_no_active_template_does_not_crash(self):
        """Si no existe ninguna plantilla (env limpio / 0004 no corrio
        aun por alguna razon), la migracion no rompe `migrate`."""
        CertificateTemplate.objects.all().delete()

        # No debe lanzar excepcion.
        self.fix_template_logo(real_apps, None)

        self.assertEqual(CertificateTemplate.objects.count(), 0)

    def test_edge_fallback_to_active_template_when_name_diverges(self):
        """Defensive: si el nombre difiere del esperado pero hay una
        plantilla activa, la migracion la corrige igual (fallback por
        is_active=True)."""
        self.legacy_template.name = "Otro nombre cualquiera"
        self.legacy_template.save()

        self.fix_template_logo(real_apps, None)

        self.legacy_template.refresh_from_db()
        self.assertIn("sd_sas_logo_v2_real", self.legacy_template.logo.name)


class DefaultTemplateLogoPostMigrateStateTest(TestCase):
    """
    Confirma el efecto end-to-end: cuando Django construyo la BD de test
    corriendo TODAS las migraciones (incluida 0005, dependiente de 0004),
    la plantilla activa por defecto YA NO apunta al asset roto. Esto
    prueba que 0005 esta correctamente enganchada en la cadena de
    dependencias -- no solo que la funcion RunPython funciona aislada.
    """

    def test_seeded_active_template_does_not_use_broken_asset(self):
        template = CertificateTemplate.objects.filter(name=TEMPLATE_NAME, is_active=True).first()
        # Si 0004 no-opeo porque ya existia una plantilla activa de otro
        # origen, no hay nada que afirmar aqui -- pero en un entorno de
        # test limpio (nuestro caso) 0004 siempre siembra esta fila.
        if template is None:
            self.skipTest("no default template seeded in this test DB")

        self.assertTrue(template.logo)
        self.assertIn("sd_sas_logo_v2_real", template.logo.name)
        with template.logo.open("rb") as f:
            self.assertEqual(f.read(), _read_bytes(_REAL_ASSET_PATH))
