"""Tests for `User.rol` + `User.supervisor` + backfill de datos (SD#58, A1).

Cubre:
  - Choices válidas del campo `rol` (EJECUTOR/COORDINADOR/ADMINISTRADOR);
    cualquier otro valor debe fallar `full_clean()`.
  - `clean()` rechaza `supervisor == self` (auto-referencia).
  - El helper puro `resolve_rol()` (usado por la migración de datos 0016)
    mapea correctamente los 12 códigos reales de `job_profile_types`
    detectados en BD por F2 (incluido NULL) al bucket esperado, aplicando la
    decisión de Miguel para A1: códigos sin mapeo automático confiable
    (CAPATAZ, "TODOS LOS CARGOS", CONTRATISTA, CONDUCTOR, COORDINADOR_VIZ,
    NULL) caen a EJECUTOR (rol más restrictivo) — NO a `None` — en vez de
    adivinar un rol elevado. `is_staff`/`is_superuser` tienen precedencia y
    backfillean a ADMINISTRADOR con confianza incluso sin `job_profile`.
  - Integración: `backfill_rol()` (la función que corre dentro de la
    migración 0016) aplicada sobre usuarios "legacy" reales — creados con
    `rol=None`, como quedará cualquier fila existente en producción justo
    después de aplicar el schema (0015) y antes del backfill (0016) — deja a
    TODOS con un valor concreto, ninguno en `None`.
"""

import importlib
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.courses.models import JobProfileType

User = get_user_model()

# El nombre del módulo empieza con dígitos ("0016_...") — no es un identificador
# Python válido, así que no se puede usar `from ... import resolve_rol` (error
# de sintaxis). Se importa dinámicamente, igual que hace el loader de Django.
_backfill_module = importlib.import_module(
    "apps.accounts.migrations.0016_backfill_user_rol"
)
resolve_rol = _backfill_module.resolve_rol
backfill_rol = _backfill_module.backfill_rol
DEFAULT_SAFE_ROL = _backfill_module.DEFAULT_SAFE_ROL


class UserRolChoicesTests(TestCase):
    """Validación de las choices del campo `rol`."""

    def _make_user(self, **overrides):
        defaults = {
            "email": f"rol_choices_{overrides.get('document_number', '1')}@example.com",
            "password": "testpassword123",
            "first_name": "Rol",
            "last_name": "Test",
            "document_type": "CC",
            "document_number": overrides.pop("document_number", "800000001"),
            "job_position": "Ejecutor",
            "job_profile": None,
            "hire_date": date(2024, 1, 1),
        }
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    def test_valid_choices_pass_full_clean(self):
        for rol_value in (
            User.Rol.EJECUTOR,
            User.Rol.COORDINADOR,
            User.Rol.ADMINISTRADOR,
        ):
            with self.subTest(rol=rol_value):
                user = self._make_user(
                    document_number=f"80000000{rol_value[0]}", rol=rol_value
                )
                user.full_clean()  # no debe lanzar

    def test_invalid_choice_raises_validation_error(self):
        user = self._make_user(document_number="800000099")
        user.rol = "SUPERADMIN_INVENTADO"
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_rol_nullable_por_defecto(self):
        """Un usuario nuevo sin `rol` explícito no falla — nulo = pendiente
        de asignación (comportamiento pre-A2, donde el selector fuerza la
        elección para casos sin sugerencia)."""
        user = self._make_user(document_number="800000098")
        self.assertIsNone(user.rol)


class UserSupervisorSelfReferenceTests(TestCase):
    """`clean()` rechaza que un usuario sea supervisor de sí mismo."""

    def _make_user(self, document_number, **overrides):
        defaults = {
            "email": f"supervisor_{document_number}@example.com",
            "password": "testpassword123",
            "first_name": "Supervisor",
            "last_name": "Test",
            "document_type": "CC",
            "document_number": document_number,
            "job_position": "Coordinador",
            "job_profile": None,
            "hire_date": date(2024, 1, 1),
        }
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    def test_clean_rejects_supervisor_equals_self(self):
        user = self._make_user("800000010")
        user.supervisor = user
        with self.assertRaises(ValidationError) as ctx:
            user.clean()
        self.assertIn("supervisor", ctx.exception.message_dict)

    def test_clean_allows_supervisor_distinct_user(self):
        coordinador = self._make_user("800000011")
        ejecutor = self._make_user("800000012")
        ejecutor.supervisor = coordinador
        ejecutor.clean()  # no debe lanzar
        ejecutor.save()
        ejecutor.refresh_from_db()
        self.assertEqual(ejecutor.supervisor_id, coordinador.pk)

    def test_clean_allows_supervisor_none_on_new_unsaved_user(self):
        """Un usuario nuevo (sin pk todavía) con `supervisor` sin asignar no
        debe fallar `clean()` — la comparación `pk == supervisor_id` solo
        aplica a instancias ya persistidas."""
        user = User(
            email="new_unsaved@example.com",
            first_name="Nuevo",
            last_name="Test",
            document_type="CC",
            document_number="800000013",
            job_position="Ejecutor",
            hire_date=date(2024, 1, 1),
        )
        user.clean()  # no debe lanzar


class ResolveRolMappingTests(TestCase):
    """`resolve_rol()` — mapeo de los 12 códigos reales de `job_profile_types`
    (evidencia F2, conteo real en BD dev: LINIERO=5, "TODOS LOS CARGOS"=2,
    ADMINISTRADOR=1, COORDINADOR_HSEQ=1, NULL=1) + is_staff/is_superuser.
    """

    def test_ejecutor_codes_map_confident(self):
        for code in ("LINIERO", "TECNICO", "OPERADOR"):
            with self.subTest(code=code):
                rol, confident = resolve_rol(code)
                self.assertEqual(rol, "EJECUTOR")
                self.assertTrue(confident)

    def test_coordinador_codes_map_confident(self):
        for code in ("JEFE_CUADRILLA", "INGENIERO_RESIDENTE", "COORDINADOR_HSEQ"):
            with self.subTest(code=code):
                rol, confident = resolve_rol(code)
                self.assertEqual(rol, "COORDINADOR")
                self.assertTrue(confident)

    def test_administrador_code_maps_confident(self):
        rol, confident = resolve_rol("ADMINISTRADOR")
        self.assertEqual(rol, "ADMINISTRADOR")
        self.assertTrue(confident)

    def test_codigos_sin_mapeo_caen_a_default_seguro_no_confiado(self):
        """CAPATAZ, TODOS LOS CARGOS, CONTRATISTA, CONDUCTOR, COORDINADOR_VIZ
        y NULL: sin sugerencia automática confiable — decisión de Miguel
        para A1 es defaultear a EJECUTOR (no adivinar un rol elevado, no
        dejar en None), marcado `confident=False` para el reporte."""
        for code in (
            "CAPATAZ",
            "TODOS LOS CARGOS",
            "CONTRATISTA",
            "CONDUCTOR",
            "COORDINADOR_VIZ",
            None,
            "CODIGO_FUTURO_DESCONOCIDO",
        ):
            with self.subTest(code=code):
                rol, confident = resolve_rol(code)
                self.assertEqual(rol, DEFAULT_SAFE_ROL)
                self.assertFalse(confident)

    def test_is_staff_gana_sobre_job_profile_ambiguo(self):
        """Un usuario is_staff=True con job_profile ambiguo (o sin
        job_profile) se backfillea a ADMINISTRADOR con confianza — cubre
        superusers creados sin `job_profile` explícito."""
        rol, confident = resolve_rol(None, is_staff=True)
        self.assertEqual(rol, "ADMINISTRADOR")
        self.assertTrue(confident)

    def test_is_superuser_gana_sobre_job_profile_operativo(self):
        rol, confident = resolve_rol("LINIERO", is_superuser=True)
        self.assertEqual(rol, "ADMINISTRADOR")
        self.assertTrue(confident)


class BackfillIntegrationTests(TestCase):
    """Integración: `backfill_rol()` sobre usuarios "legacy" reales (creados
    con `rol=None`, tal como quedará cualquier fila existente en producción
    justo después de aplicar 0015 y antes de 0016). Composición calcada del
    conteo real de BD dev que F2 reportó (10 usuarios: LINIERO=5, "TODOS LOS
    CARGOS"=2, ADMINISTRADOR=1, COORDINADOR_HSEQ=1, NULL=1), más un
    superuser sin `job_profile` para cubrir ese caso.
    """

    def setUp(self):
        # Los 4 códigos que la BD dev tiene pero NINGUNA migración siembra
        # (se crearon directo en la tabla dinámica `job_profile_types`,
        # evidencia F2) — se recrean acá para simular ese estado real.
        self.jp_capataz = JobProfileType.objects.create(
            code="CAPATAZ", name="Capataz", order=20
        )
        self.jp_todos = JobProfileType.objects.create(
            code="TODOS LOS CARGOS", name="Todos los Cargos", order=21
        )
        self.jp_contratista = JobProfileType.objects.create(
            code="CONTRATISTA", name="Contratista", order=22
        )
        self.jp_conductor = JobProfileType.objects.create(
            code="CONDUCTOR", name="Conductor", order=23
        )
        # Códigos ya sembrados por migraciones previas (0008/0013).
        self.jp_liniero = JobProfileType.objects.get(code="LINIERO")
        self.jp_admin = JobProfileType.objects.get(code="ADMINISTRADOR")
        self.jp_coord_hseq = JobProfileType.objects.get(code="COORDINADOR_HSEQ")

    def _legacy_user(self, document_number, job_profile, **overrides):
        """Usuario "legacy": existe en BD con `rol=None` (estado previo al
        backfill) — no fixture nueva del test, sino la fila real que
        `backfill_rol()` debe procesar."""
        defaults = {
            "email": f"legacy_{document_number}@example.com",
            "password": "testpassword123",
            "first_name": "Legacy",
            "last_name": "User",
            "document_type": "CC",
            "document_number": document_number,
            "job_position": "N/A",
            "job_profile": job_profile,
            "hire_date": date(2023, 1, 1),
        }
        defaults.update(overrides)
        user = User.objects.create_user(**defaults)
        # create_user no setea rol -> ya queda None por default del campo;
        # lo re-afirmamos explícito para dejar clara la precondición "legacy".
        user.rol = None
        user.save(update_fields=["rol"])
        return user

    def test_backfill_deja_todos_los_usuarios_con_rol_concreto(self):
        liniero_1 = self._legacy_user("900000001", self.jp_liniero)
        liniero_2 = self._legacy_user("900000002", self.jp_liniero)
        todos_1 = self._legacy_user("900000003", self.jp_todos)
        todos_2 = self._legacy_user("900000004", self.jp_todos)
        admin_user = self._legacy_user("900000005", self.jp_admin)
        coord_hseq = self._legacy_user("900000006", self.jp_coord_hseq)
        sin_perfil = self._legacy_user("900000007", None)
        capataz = self._legacy_user("900000008", self.jp_capataz)
        contratista = self._legacy_user("900000009", self.jp_contratista)
        conductor = self._legacy_user("900000010", self.jp_conductor)
        # Superuser sin job_profile (ej. createsuperuser) — no debe caer al
        # default seguro, aunque su job_profile sea None.
        superuser = self._legacy_user(
            "900000011", None, is_superuser=True, is_staff=True
        )

        from django.apps import apps as real_apps

        backfill_rol(real_apps, None)

        for user, expected_rol in [
            (liniero_1, "EJECUTOR"),
            (liniero_2, "EJECUTOR"),
            (admin_user, "ADMINISTRADOR"),
            (coord_hseq, "COORDINADOR"),
            (superuser, "ADMINISTRADOR"),
        ]:
            user.refresh_from_db()
            with self.subTest(user=user.document_number):
                self.assertEqual(user.rol, expected_rol)

        # Sin mapeo confiable -> default seguro (EJECUTOR), NUNCA None.
        for user in (todos_1, todos_2, sin_perfil, capataz, contratista, conductor):
            user.refresh_from_db()
            with self.subTest(user=user.document_number):
                self.assertEqual(user.rol, "EJECUTOR")
                self.assertIsNotNone(user.rol)

    def test_backfill_es_deterministico_sobreescribe_valor_previo(self):
        """Regresión: si un usuario YA tiene `rol` asignado explícitamente
        (ej. corrida repetida de la migración, o asignación manual previa),
        `backfill_rol()` puede sobreescribirlo según el mapeo — se documenta
        el comportamiento esperado: la migración es idempotente respecto al
        mapeo determinístico (mismo input -> mismo output), no preserva un
        override manual. Esto es aceptable porque 0016 corre una sola vez en
        el deploy real, nunca contra datos ya operando con rol manual."""
        user = self._legacy_user("900000020", self.jp_liniero)
        user.rol = "ADMINISTRADOR"  # override manual simulado
        user.save(update_fields=["rol"])

        from django.apps import apps as real_apps

        backfill_rol(real_apps, None)

        user.refresh_from_db()
        self.assertEqual(user.rol, "EJECUTOR")
