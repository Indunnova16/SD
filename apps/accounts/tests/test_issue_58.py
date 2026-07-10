"""Tests for issue #58 (reproceso) — la contraseña generada por
`PasswordService.generate_password()` nunca se exponía al crear un usuario
(ni individual vía `UserCreateForm`/`user_create`, ni por carga masiva vía
`BulkUploadService.create_users_from_rows`/`bulk_upload`), a diferencia de
`admin_reset_password` que SÍ la muestra.

Causa raíz confirmada por F2 (BD prod + logs Cloud Run, NO fue lockout de
django-axes): el usuario real avelasquez@indunnova.com (id=17, document_number
'1017233', nombre 'ANDREA JARAMILLO') fue creado el 2026-07-07T13:09:20Z con
password determinístico '1017233AND' que ninguna pantalla mostró — 17s
después su intento de login falló (failures_since_start=1, muy por debajo del
límite de axes=10), y nadie pudo comunicarle la contraseña real porque nunca
se vio en ninguna parte de la UI.

Fix quirúrgico (4 archivos):
  1. apps/accounts/forms.py::UserCreateForm.save() — adjunta
     `user.generated_password` (atributo transiente, NO campo de modelo).
  2. apps/accounts/views.py::user_create — extiende el mensaje de éxito con
     la contraseña inicial.
  3. apps/accounts/services.py::BulkUploadService.create_users_from_rows —
     adjunta igual `generated_password` antes de `created.append(user)`.
  4. templates/accounts/bulk_upload.html — la columna "Contraseña inicial"
     ahora renderiza `user.generated_password` (el valor REAL persistido)
     en vez de recomputar `{{ first_name|upper|slice:":3" }}` inline, cómputo
     que no aplicaba el padding con 'X' de nombres <3 letras
     (`PasswordService.generate_password`) y podía mostrar una contraseña
     que NO coincidía con la realmente guardada.

Este suite es exclusivo de este issue (RUN con 3 issues del mismo repo:
SD#54, SD#58, SD#59) — no se apendea a `tests.py`/otros módulos compartidos.
"""

import io
import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.forms import UserCreateForm
from apps.accounts.permissions import Rol
from apps.accounts.services import BulkUploadService, PasswordService
from apps.courses.models import JobProfileType

User = get_user_model()

_SEQ = itertools.count(1)


def _make_admin(**overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"admin_i58_{n}@example.com",
        "password": "testpass123",
        "first_name": f"Admin{n}",
        "last_name": "I58",
        "document_type": "CC",
        "document_number": f"90{n:07d}",
        "job_position": "Admin",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": Rol.ADMINISTRADOR,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _bulk_row(row_num=2, **overrides):
    """Fila mínima válida de bulk upload (dict como lo produce `parse_excel`),
    mismo helper que `test_issue_58_a3.py` para no divergir de la convención
    ya establecida en el módulo hermano."""
    data = {
        "_row_num": row_num,
        "nombre": "Nuevo",
        "apellido": "Usuario",
        "numero_documento": "600000001",
        "tipo_documento": "CC",
        "correo": "",
        "telefono": "",
        "cargo": "Cargo de prueba",
        "perfil_ocupacional": "LINIERO",
        "tipo_vinculacion": "directo",
        "fecha_ingreso": date(2026, 1, 1),
        "estado": "activo",
    }
    data.update(overrides)
    return data


class UserCreateFormExposesGeneratedPasswordTests(TestCase):
    """Fix #1: `UserCreateForm.save()` adjunta `generated_password` — sin
    esto, `user_create` (fix #2) no tenía forma de saber qué contraseña
    mostrarle al admin."""

    def setUp(self):
        self.profile, _ = JobProfileType.objects.get_or_create(
            code="TECNICO", defaults={"name": "Técnico", "is_active": True}
        )

    def test_save_attaches_generated_password_matching_service_formula(self):
        """Dato legacy real del incidente (id=17): document_number='1017233',
        first_name='Andrea' -> password determinístico '1017233AND', el
        MISMO que quedó realmente guardado en prod el 2026-07-07."""
        post_data = {
            "email": "nuevo_i58@example.com",
            "first_name": "Andrea",
            "last_name": "Jaramillo",
            "document_type": "CC",
            "document_number": "1017233",
            "phone": "",
            "job_position": "Coordinador",
            "job_profile": self.profile.pk,
            "employment_type": "direct",
            "hire_date": "2026-07-07",
            "status": "active",
            "rol": "COORDINADOR",
        }
        form = UserCreateForm(post_data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()

        expected = PasswordService.generate_password("1017233", "Andrea")
        self.assertEqual(expected, "1017233AND")
        self.assertEqual(getattr(user, "generated_password", None), expected)
        # Regresión funcional real: la contraseña expuesta debe ser la que
        # de verdad autentica (no una reconstrucción aproximada).
        self.assertTrue(user.check_password(expected))

    def test_generated_password_not_a_model_field(self):
        """Atributo transiente — no debe persistir como columna de BD (no
        aparece en `_meta.get_fields()`), solo vive en memoria del request."""
        field_names = {f.name for f in User._meta.get_fields()}
        self.assertNotIn("generated_password", field_names)


class UserCreateViewShowsGeneratedPasswordTests(TestCase):
    """Fix #2: `user_create` extiende el mensaje de éxito con la contraseña
    inicial — antes solo decía 'creado exitosamente', sin decir cómo
    loguearse (la causa raíz confirmada del rebote de #58)."""

    def setUp(self):
        self.client = Client()
        self.admin = _make_admin()
        self.profile, _ = JobProfileType.objects.get_or_create(
            code="TECNICO", defaults={"name": "Técnico", "is_active": True}
        )

    def test_success_message_incluye_contrasena_inicial(self):
        self.client.force_login(self.admin)
        post_data = {
            "email": "coord_i58@example.com",
            "first_name": "Andrea",
            "last_name": "Jaramillo",
            "document_type": "CC",
            "document_number": "1017233999",
            "phone": "",
            "job_position": "Coordinador",
            "job_profile": self.profile.pk,
            "employment_type": "direct",
            "hire_date": "2026-07-07",
            "status": "active",
            "rol": "COORDINADOR",
        }
        response = self.client.post(reverse("accounts:user_create"), post_data)
        self.assertEqual(response.status_code, 302)

        created = User.objects.get(document_number="1017233999")
        expected_password = PasswordService.generate_password("1017233999", "Andrea")

        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("Contraseña inicial" in m and expected_password in m for m in msgs),
            f"Esperaba mensaje con 'Contraseña inicial: {expected_password}', obtuve: {msgs}",
        )
        # Regresión funcional real: la contraseña mostrada es la que
        # efectivamente permite loguearse (no una string cosmética suelta).
        self.assertTrue(created.check_password(expected_password))

    def test_ejecutor_no_accede_a_user_create(self):
        """Regresión: A4 (RBAC) sigue gateando esta vista solo a
        ADMINISTRADOR — el fix de este issue no debe aflojar ese gate."""
        ejecutor = User.objects.create_user(
            email="ejecutor_i58@example.com",
            password="x",
            first_name="Eje",
            last_name="Cutor",
            document_type="CC",
            document_number="800000001",
            job_position="Liniero",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            rol=Rol.EJECUTOR,
        )
        self.client.force_login(ejecutor)
        response = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:dashboard"))


class BulkUploadServiceExposesGeneratedPasswordTests(TestCase):
    """Fix #3: `BulkUploadService.create_users_from_rows` adjunta
    `generated_password` a cada usuario creado antes de `created.append`."""

    def setUp(self):
        self.jp, _ = JobProfileType.objects.get_or_create(
            code="LINIERO", defaults={"name": "Liniero", "order": 1}
        )

    def test_created_users_carry_generated_password_attribute(self):
        row = _bulk_row(nombre="Ana", numero_documento="700000001")
        created, errors = BulkUploadService.create_users_from_rows([row])

        self.assertEqual(errors, [])
        self.assertEqual(len(created), 1)
        expected = PasswordService.generate_password("700000001", "Ana")
        self.assertEqual(created[0].generated_password, expected)
        self.assertTrue(created[0].check_password(expected))

    def test_generated_password_padding_short_name_two_letters(self):
        """Nombre de 2 letras -> `PasswordService.generate_password` rellena
        con 'X' ('...ALX'). Antes del fix, la plantilla recomputaba
        `{{ first_name|upper|slice:":3" }}` en el HTML en vez de usar el
        atributo real -> hubiera mostrado '...AL' (sin la X), una contraseña
        que NO coincide con la realmente guardada. Este test prueba que el
        atributo expuesto por el servicio es siempre el password REAL."""
        row = _bulk_row(nombre="Al", numero_documento="700000002")
        created, errors = BulkUploadService.create_users_from_rows([row])

        self.assertEqual(errors, [])
        expected = PasswordService.generate_password("700000002", "Al")
        self.assertEqual(expected, "700000002ALX")
        self.assertEqual(created[0].generated_password, expected)
        self.assertTrue(created[0].check_password(expected))


class BulkUploadViewRendersGeneratedPasswordTests(TestCase):
    """Fix #4: `templates/accounts/bulk_upload.html` renderiza
    `user.generated_password` en vez del cómputo inline sin padding."""

    def setUp(self):
        self.client = Client()
        self.admin = _make_admin()
        self.jp, _ = JobProfileType.objects.get_or_create(
            code="LINIERO", defaults={"name": "Liniero", "order": 1}
        )

    def _build_workbook(self, headers, rows):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()

    def test_resultado_muestra_password_real_con_padding_no_aproximado(self):
        """Caso discriminante: nombre 'Al' (2 letras). El cómputo VIEJO del
        template (`{{ first_name|upper|slice:":3" }}`, sin padding) hubiera
        mostrado '700000003AL'; el fix muestra el valor REAL
        '700000003ALX' (con la 'X' de relleno que sí aplica
        `PasswordService.generate_password`)."""
        self.client.force_login(self.admin)
        content = self._build_workbook(
            ["nombre", "apellido", "numero_documento", "perfil_ocupacional"],
            [["Al", "Perez", "700000003", "liniero"]],
        )
        upload = SimpleUploadedFile(
            "plantilla.xlsx",
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response = self.client.post(reverse("accounts:bulk_upload"), {"file": upload})
        self.assertEqual(response.status_code, 200)

        expected_password = PasswordService.generate_password("700000003", "Al")
        self.assertEqual(expected_password, "700000003ALX")

        html = response.content.decode()
        self.assertIn(f"<code>{expected_password}</code>", html)
        # La versión vieja (sin 'X' de padding) NO debe aparecer como celda propia.
        self.assertNotIn("<code>700000003AL</code>", html)

        created_user = User.objects.get(document_number="700000003")
        self.assertTrue(created_user.check_password(expected_password))
