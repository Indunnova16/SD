"""Tests for SD#50 — bulk upload: header alias, per-row IntegrityError isolation,
password uppercase convention.

Regression suite for the 3 sub-items confirmed in the F2 diagnosis:
- B1: BulkUploadService.parse_excel now accepts 'Cédula'/'documento' as aliases
  for 'numero_documento' (the natural header used across the rest of the UI —
  login, labels, ExportService), on top of the existing 'numero_documento'
  header already used by the official template served in prod.
- B2: create_users_from_rows wraps each row in `with transaction.atomic()`
  (nested savepoint) and catches `IntegrityError` specifically, so (a) a DB
  integrity error on one row doesn't leak Postgres' raw error text to the
  user, and (b) does not poison row creation for the rows that follow it in
  the same file.
- Mejora: PasswordService.generate_password uses UPPERCASE for the 3-letter
  name suffix (was lowercase), matching the convention documented in the
  template and shown on the bulk_upload results page.
"""

import io
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.services import BulkUploadService, PasswordService
from apps.courses.models import JobProfileType

User = get_user_model()


class PasswordServiceUppercaseTests(TestCase):
    """Mejora: la contraseña generada usa MAYÚSCULA, no minúscula (SD#50)."""

    def test_generate_password_uses_uppercase_name_part(self):
        password = PasswordService.generate_password("1234567890", "Carlos")
        self.assertEqual(password, "1234567890CAR")

    def test_generate_password_pads_short_name_with_uppercase_x(self):
        password = PasswordService.generate_password("111", "Al")
        self.assertEqual(password, "111ALX")

    def test_generate_password_default_when_no_name(self):
        password = PasswordService.generate_password("222", "")
        self.assertEqual(password, "222USR")


class ParseExcelHeaderAliasTests(TestCase):
    """B1: 'Cédula'/'documento' deben aceptarse como alias de 'numero_documento'
    (SD#50) — sin romper el header canónico ya usado por la plantilla oficial."""

    def _build_workbook(self, headers, row):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_accepts_cedula_header_alias(self):
        file = self._build_workbook(
            ["nombre", "apellido", "Cédula"],
            ["Ana", "Gómez", "9990001"],
        )
        rows, errors = BulkUploadService.parse_excel(file)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["numero_documento"], "9990001")

    def test_accepts_documento_header_alias(self):
        file = self._build_workbook(
            ["nombre", "apellido", "documento"],
            ["Luis", "Pérez", "9990002"],
        )
        rows, errors = BulkUploadService.parse_excel(file)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["numero_documento"], "9990002")

    def test_still_accepts_canonical_numero_documento_header(self):
        """No regression: la plantilla oficial servida en prod usa 'numero_documento'."""
        file = self._build_workbook(
            ["nombre", "apellido", "numero_documento"],
            ["Marta", "Ruiz", "9990003"],
        )
        rows, errors = BulkUploadService.parse_excel(file)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["numero_documento"], "9990003")

    def test_rejects_file_missing_required_columns(self):
        file = self._build_workbook(["nombre", "apellido"], ["Sin", "Documento"])
        rows, errors = BulkUploadService.parse_excel(file)
        self.assertEqual(rows, [])
        self.assertTrue(any("numero_documento" in e for e in errors))


class CreateUsersFromRowsIntegrityErrorTests(TestCase):
    """B2: IntegrityError específico + savepoint por fila (SD#50).

    Reproduce el mecanismo citado por el cliente en el issue ('duplicate key
    value violates unique constraint "users_pkey"') vía mock de User.save, sin
    depender de la sincronía puntual de users_id_seq en prod (confirmada HOY en
    sync — ver F2, por lo que no es reproducible pasivamente contra la BD real).
    """

    def setUp(self):
        # Data migrations ya seedean LINIERO (0008_seed_job_profile_types); usar
        # get_or_create por si el entorno de test lo trae o no.
        self.profile, _ = JobProfileType.objects.get_or_create(
            code="LINIERO",
            defaults={"name": "Liniero", "is_active": True},
        )
        # Usuario legacy pre-existente (análogo al qa_claude id=7 citado en el
        # issue), para probar el pre-check de duplicados contra un registro que
        # ya existía ANTES de este fix, no solo contra fixtures nuevas del test.
        self.legacy_user = User.objects.create_user(
            email="legacy_sd50@example.com",
            password="x",
            first_name="Legacy",
            last_name="User",
            document_type="CC",
            document_number="LEGACY-SD50",
            job_position="Liniero",
            job_profile=self.profile,
            employment_type="direct",
            hire_date=date(2024, 1, 1),
        )

    def test_integrity_error_does_not_expose_raw_db_message(self):
        """El mensaje mostrado al usuario NO debe citar el texto crudo de Postgres
        (antes: `except Exception as e: ... f'Error al crear usuario: {e}'`)."""
        rows = [
            {
                "_row_num": 2,
                "nombre": "Fila",
                "apellido": "ConError",
                "numero_documento": "9990010",
            },
        ]

        def raise_integrity_error(self, *args, **kwargs):
            raise IntegrityError(
                'duplicate key value violates unique constraint "users_pkey"\n'
                "DETAIL:  Key (id)=(7) already exists."
            )

        with patch.object(User, "save", raise_integrity_error):
            created, errors = BulkUploadService.create_users_from_rows(rows)

        self.assertEqual(created, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Fila 2", errors[0])
        self.assertNotIn("users_pkey", errors[0])
        self.assertNotIn("duplicate key", errors[0])

    def test_integrity_error_on_one_row_does_not_poison_following_rows(self):
        """Un IntegrityError en la fila N no debe impedir crear la fila N+1 —
        savepoint por fila vía `with transaction.atomic()` (antes: un solo
        `@transaction.atomic` global sin savepoint por fila envenenaba el resto)."""
        rows = [
            {
                "_row_num": 2,
                "nombre": "Falla",
                "apellido": "Uno",
                "numero_documento": "9990011",
            },
            {
                "_row_num": 3,
                "nombre": "Exito",
                "apellido": "Dos",
                "numero_documento": "9990012",
            },
        ]
        original_save = User.save

        def flaky_save(self, *args, **kwargs):
            if self.document_number == "9990011":
                raise IntegrityError("duplicate key value violates unique constraint")
            return original_save(self, *args, **kwargs)

        with patch.object(User, "save", flaky_save):
            created, errors = BulkUploadService.create_users_from_rows(rows)

        self.assertEqual(len(errors), 1)
        self.assertIn("Fila 2", errors[0])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].document_number, "9990012")
        # Confirmar en BD (no solo en el valor de retorno) que la fila 3 sí
        # quedó persistida pese al error de la fila 2.
        self.assertTrue(User.objects.filter(document_number="9990012").exists())

    def test_duplicate_document_number_against_preexisting_legacy_user(self):
        """El pre-check de duplicados sigue funcionando contra un usuario legacy
        creado ANTES de este fix (dato pre-existente, no solo fixture nueva)."""
        rows = [
            {
                "_row_num": 2,
                "nombre": "Legacy",
                "apellido": "Duplicado",
                "numero_documento": "LEGACY-SD50",
            },
        ]
        created, errors = BulkUploadService.create_users_from_rows(rows)
        self.assertEqual(created, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Ya existe un usuario con documento", errors[0])
