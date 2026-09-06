"""Tests for el selector de `rol` + `supervisor` en Crear/Editar Usuario
(SD#58, sub-item A2).

Cubre:
  - `RolSupervisorMixin.suggest_rol_for_job_profile()` — prellenado sugerido
    (puro, sin HTTP/JS) para cada uno de los 7 códigos de `job_profile` que
    A1 mapea con confianza, y `None` para el resto (bucket "sin sugerencia":
    COORDINADOR_VIZ, CAPATAZ, "TODOS LOS CARGOS", CONTRATISTA, CONDUCTOR,
    sin perfil, código futuro desconocido).
  - `UserCreateForm`/`UserEditForm`: si `job_profile` cae en el bucket "sin
    sugerencia" y el cliente no envía `rol`, `clean()` exige elección
    explícita (`ValidationError` SOLO en el campo `rol`, no bloquea el
    resto del form). Si `job_profile` sí sugiere un rol con confianza y el
    cliente no envía `rol`, se aplica la sugerencia como respaldo
    server-side (no rompe integraciones/tests previos a A2).
  - `supervisor`: queryset limitado a `rol in (COORDINADOR, ADMINISTRADOR)`
    — excluye usuarios con `rol=EJECUTOR`.
  - `supervisor == self` (editar): el form propaga el error de `User.clean()`
    (A1) de forma clara en `form.errors['supervisor']`, sin lanzar excepción
    (no 500) — cubierto también a nivel de vista end-to-end.
  - `rol_suggestions_json`: mapeo `{job_profile_id: rol_sugerido|null}`
    correcto, keyed por PK (no por código) porque `job_profile` es una FK
    (ModelChoiceField renderiza `<option value=pk>`).
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.forms import UserCreateForm, UserEditForm
from apps.courses.models import JobProfileType

User = get_user_model()

# Los 7 códigos que A1 mapea con confianza -> rol sugerido esperado.
MAPPED_CODES = {
    "LINIERO": User.Rol.EJECUTOR,
    "TECNICO": User.Rol.EJECUTOR,
    "OPERADOR": User.Rol.EJECUTOR,
    "JEFE_CUADRILLA": User.Rol.COORDINADOR,
    "INGENIERO_RESIDENTE": User.Rol.COORDINADOR,
    "COORDINADOR_HSEQ": User.Rol.COORDINADOR,
    "ADMINISTRADOR": User.Rol.ADMINISTRADOR,
}

# Códigos reales de BD (evidencia F2) sin mapeo automático confiable.
UNMAPPED_CODES = [
    "COORDINADOR_VIZ",
    "CAPATAZ",
    "TODOS LOS CARGOS",
    "CONTRATISTA",
    "CONDUCTOR",
    "CODIGO_FUTURO_DESCONOCIDO",
]


class SuggestRolForJobProfileTests(TestCase):
    """`suggest_rol_for_job_profile()` — prellenado puro, sin HTTP/JS."""

    def setUp(self):
        self.profiles_by_code = {}
        for i, code in enumerate(list(MAPPED_CODES) + UNMAPPED_CODES, start=1):
            jp, _created = JobProfileType.objects.get_or_create(
                code=code, defaults={"name": code.title(), "order": i}
            )
            self.profiles_by_code[code] = jp

    def test_prellenado_correcto_para_cada_job_profile_mapeado(self):
        for code, expected_rol in MAPPED_CODES.items():
            with self.subTest(code=code):
                jp = self.profiles_by_code[code]
                self.assertEqual(UserCreateForm.suggest_rol_for_job_profile(jp), expected_rol)
                # Mismo comportamiento en UserEditForm (mixin compartido).
                self.assertEqual(UserEditForm.suggest_rol_for_job_profile(jp), expected_rol)

    def test_codigos_sin_mapeo_no_sugieren_nada(self):
        for code in UNMAPPED_CODES:
            with self.subTest(code=code):
                jp = self.profiles_by_code[code]
                self.assertIsNone(UserCreateForm.suggest_rol_for_job_profile(jp))

    def test_job_profile_none_no_sugiere_nada(self):
        self.assertIsNone(UserCreateForm.suggest_rol_for_job_profile(None))

    def test_rol_suggestions_json_keyed_por_pk_no_por_codigo(self):
        """`job_profile` es FK — el <option value> real es el PK, no el
        código (ambigüedad marcada por F2 en `ui_nueva_reconciliar`)."""
        import json

        form = UserCreateForm()
        mapping = json.loads(form.rol_suggestions_json)

        liniero = self.profiles_by_code["LINIERO"]
        capataz = self.profiles_by_code["CAPATAZ"]

        self.assertIn(str(liniero.pk), mapping)
        self.assertEqual(mapping[str(liniero.pk)], "EJECUTOR")
        self.assertIn(str(capataz.pk), mapping)
        self.assertIsNone(mapping[str(capataz.pk)])


class RolRequiereEleccionExplicitaFormTests(TestCase):
    """`clean()` de `UserCreateForm`/`UserEditForm`: bucket sin sugerencia +
    `rol` vacío -> error; bucket mapeado + `rol` vacío -> fallback server-side."""

    def setUp(self):
        self.jp_liniero, _ = JobProfileType.objects.get_or_create(
            code="LINIERO", defaults={"name": "Liniero", "order": 1}
        )
        self.jp_capataz, _ = JobProfileType.objects.get_or_create(
            code="CAPATAZ", defaults={"name": "Capataz", "order": 2}
        )

    def _create_post_data(self, job_profile, **overrides):
        data = {
            "email": "nuevo_a2@example.com",
            "first_name": "Nuevo",
            "last_name": "A2",
            "document_type": "CC",
            "document_number": "700000001",
            "phone": "",
            "job_position": "Cargo de prueba",
            "job_profile": job_profile.pk if job_profile else "",
            "employment_type": "direct",
            "hire_date": "2025-01-01",
            "status": "active",
        }
        data.update(overrides)
        return data

    def test_bucket_sin_sugerencia_y_rol_vacio_es_error_solo_en_rol(self):
        data = self._create_post_data(self.jp_capataz)  # sin "rol" en el POST
        form = UserCreateForm(data)

        self.assertFalse(form.is_valid())
        self.assertIn("rol", form.errors)
        # No bloquea el resto del form: el resto de los campos válidos no
        # deberían tener error.
        self.assertNotIn("first_name", form.errors)
        self.assertNotIn("job_position", form.errors)

    def test_bucket_sin_sugerencia_con_rol_explicito_es_valido(self):
        data = self._create_post_data(self.jp_capataz, rol="COORDINADOR")
        form = UserCreateForm(data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.rol, "COORDINADOR")

    def test_bucket_mapeado_y_rol_vacio_aplica_sugerencia_server_side(self):
        """Respaldo server-side: si el cliente no envía `rol` (JS
        deshabilitado, o un caller que no lo conoce) pero `job_profile`
        tiene una sugerencia confiable, se aplica esa sugerencia — no
        rompe compatibilidad con callers previos a A2."""
        data = self._create_post_data(self.jp_liniero)  # sin "rol"
        form = UserCreateForm(data)

        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.rol, "EJECUTOR")

    def test_edit_form_bucket_sin_sugerencia_y_rol_vacio_es_error(self):
        user = User.objects.create_user(
            email="editar_a2@example.com",
            password="x",
            first_name="Editar",
            last_name="A2",
            document_type="CC",
            document_number="700000002",
            job_position="Capataz",
            job_profile=self.jp_capataz,
            hire_date=date(2024, 1, 1),
            rol="EJECUTOR",
        )
        data = {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "document_type": user.document_type,
            "document_number": user.document_number,
            "phone": "",
            "job_position": user.job_position,
            "job_profile": self.jp_capataz.pk,
            "rol": "",  # el admin lo borra explícitamente
            "employment_type": "direct",
            "hire_date": "2024-01-01",
            "status": "active",
            "is_active": True,
            "is_staff": False,
        }
        form = UserEditForm(data, instance=user)
        self.assertFalse(form.is_valid())
        self.assertIn("rol", form.errors)


class SupervisorQuerysetTests(TestCase):
    """`supervisor` queryset limitado a `rol in (COORDINADOR, ADMINISTRADOR)`."""

    def setUp(self):
        self.ejecutor = User.objects.create_user(
            email="ejecutor_a2@example.com",
            password="x",
            first_name="Ejecutor",
            last_name="Uno",
            document_type="CC",
            document_number="700000010",
            job_position="Liniero",
            hire_date=date(2024, 1, 1),
            rol="EJECUTOR",
        )
        self.coordinador = User.objects.create_user(
            email="coordinador_a2@example.com",
            password="x",
            first_name="Coordinador",
            last_name="Uno",
            document_type="CC",
            document_number="700000011",
            job_position="Jefe de Cuadrilla",
            hire_date=date(2024, 1, 1),
            rol="COORDINADOR",
        )
        self.administrador = User.objects.create_user(
            email="admin_a2@example.com",
            password="x",
            first_name="Admin",
            last_name="Uno",
            document_type="CC",
            document_number="700000012",
            job_position="Administrador",
            hire_date=date(2024, 1, 1),
            rol="ADMINISTRADOR",
        )

    def test_supervisor_queryset_excluye_ejecutor(self):
        form = UserCreateForm()
        queryset_ids = set(form.fields["supervisor"].queryset.values_list("pk", flat=True))

        self.assertNotIn(self.ejecutor.pk, queryset_ids)
        self.assertIn(self.coordinador.pk, queryset_ids)
        self.assertIn(self.administrador.pk, queryset_ids)

    def test_supervisor_queryset_edit_form_tambien_excluye_ejecutor(self):
        form = UserEditForm(instance=self.ejecutor)
        queryset_ids = set(form.fields["supervisor"].queryset.values_list("pk", flat=True))
        self.assertIn(self.coordinador.pk, queryset_ids)
        self.assertIn(self.administrador.pk, queryset_ids)


class SupervisorSelfReferenceFormTests(TestCase):
    """El form propaga con claridad (no 500) el error de `User.clean()`
    (A1) cuando `supervisor == self`."""

    def setUp(self):
        self.jp_coord, _ = JobProfileType.objects.get_or_create(
            code="COORDINADOR_HSEQ", defaults={"name": "Coordinador HSEQ", "order": 3}
        )
        self.coordinador = User.objects.create_user(
            email="self_sup_a2@example.com",
            password="x",
            first_name="Auto",
            last_name="Referencia",
            document_type="CC",
            document_number="700000020",
            job_position="Coordinador HSEQ",
            job_profile=self.jp_coord,
            hire_date=date(2024, 1, 1),
            rol="COORDINADOR",
        )

    def _edit_post_data(self, **overrides):
        data = {
            "email": self.coordinador.email,
            "first_name": self.coordinador.first_name,
            "last_name": self.coordinador.last_name,
            "document_type": self.coordinador.document_type,
            "document_number": self.coordinador.document_number,
            "phone": "",
            "job_position": self.coordinador.job_position,
            "job_profile": self.jp_coord.pk,
            "rol": "COORDINADOR",
            "supervisor": self.coordinador.pk,
            "employment_type": "direct",
            "hire_date": "2024-01-01",
            "status": "active",
            "is_active": True,
            "is_staff": False,
        }
        data.update(overrides)
        return data

    def test_form_rechaza_supervisor_igual_a_si_mismo_sin_excepcion(self):
        data = self._edit_post_data()
        form = UserEditForm(data, instance=self.coordinador)

        # No debe lanzar excepción (no 500) — `is_valid()` debe resolver a
        # False con un mensaje claro en el campo `supervisor`.
        is_valid = form.is_valid()

        self.assertFalse(is_valid)
        self.assertIn("supervisor", form.errors)
        self.assertIn("no puede ser supervisor de sí mismo", form.errors["supervisor"][0])

    def test_form_permite_supervisor_distinto(self):
        otro_coordinador = User.objects.create_user(
            email="otro_coord_a2@example.com",
            password="x",
            first_name="Otro",
            last_name="Coordinador",
            document_type="CC",
            document_number="700000021",
            job_position="Coordinador HSEQ",
            hire_date=date(2024, 1, 1),
            rol="COORDINADOR",
        )
        data = self._edit_post_data(supervisor=otro_coordinador.pk)
        form = UserEditForm(data, instance=self.coordinador)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        updated = form.save()
        self.assertEqual(updated.supervisor_id, otro_coordinador.pk)


class UserEditViewSupervisorSelfReferenceViewTests(TestCase):
    """End-to-end (vista real, no solo form): supervisor==self no produce
    un 500 — la página se re-renderiza con el error, protocolo issues
    (\"no un 500\", instrucción explícita del dispatch de A2)."""

    def setUp(self):
        self.client = Client()
        self.jp_coord, _ = JobProfileType.objects.get_or_create(
            code="COORDINADOR_HSEQ", defaults={"name": "Coordinador HSEQ", "order": 3}
        )
        self.admin = User.objects.create_user(
            email="view_admin_a2@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="Vista",
            document_type="CC",
            document_number="700000030",
            hire_date=date(2024, 1, 1),
            is_staff=True,
            job_position="Administrador",
            rol="ADMINISTRADOR",
        )
        self.coordinador = User.objects.create_user(
            email="view_coord_a2@example.com",
            password="x",
            first_name="Coord",
            last_name="Vista",
            document_type="CC",
            document_number="700000031",
            job_position="Coordinador HSEQ",
            job_profile=self.jp_coord,
            hire_date=date(2024, 1, 1),
            rol="COORDINADOR",
        )
        self.client.login(username="700000030", password="adminpass123")

    def test_post_supervisor_self_no_500_re_renderiza_con_error(self):
        url = reverse("accounts:user_edit", kwargs={"user_id": self.coordinador.pk})
        data = {
            "email": self.coordinador.email,
            "first_name": self.coordinador.first_name,
            "last_name": self.coordinador.last_name,
            "document_type": self.coordinador.document_type,
            "document_number": self.coordinador.document_number,
            "phone": "",
            "job_position": self.coordinador.job_position,
            "job_profile": self.jp_coord.pk,
            "rol": "COORDINADOR",
            "supervisor": self.coordinador.pk,
            "employment_type": "direct",
            "hire_date": "2024-01-01",
            "status": "active",
            "is_active": True,
            "is_staff": False,
        }
        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, 200)  # no 500, re-renderiza el form
        self.coordinador.refresh_from_db()
        self.assertIsNone(self.coordinador.supervisor_id)  # no se guardó el cambio inválido
        self.assertContains(response, "no puede ser supervisor de s")
