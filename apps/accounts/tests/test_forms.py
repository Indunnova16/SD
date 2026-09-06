"""Tests for accounts forms — focus on hire_date persistence (SD#41).

Regression tests for the bug where editing a user via the admin form did not
persist changes because the HTML5 <input type="date"> was being rendered with
the es-co locale format ("15/01/2024") in its `value` attribute. The browser
silently ignores non-ISO values on type="date" inputs, so the datepicker
appeared empty; saving then sent hire_date="" → ValidationError → no changes
applied.

The fix overrides the hire_date field on both UserCreateForm and UserEditForm
to force ISO ("%Y-%m-%d") on render AND parse, decoupling the widget from the
active locale.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms import UserCreateForm, UserEditForm
from apps.courses.models import JobProfileType

User = get_user_model()


class UserEditFormHireDateTests(TestCase):
    """Regression tests for SD#41 — hire_date no persistía al editar."""

    def setUp(self):
        # Data migrations may have already seeded LINIERO; use get_or_create.
        self.profile, _ = JobProfileType.objects.get_or_create(
            code="LINIERO",
            defaults={"name": "Liniero", "is_active": True},
        )
        self.user = User.objects.create_user(
            email="test_sd41@example.com",
            password="x",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345_sd41",
            job_position="Liniero",
            job_profile=self.profile,
            employment_type="direct",
            hire_date=date(2024, 1, 15),
            status="active",
        )

    def test_form_initial_renders_hire_date_as_iso(self):
        """The widget must render value='2024-01-15' (ISO), not '15/01/2024'.

        Without the fix, Django would render the value using the first format
        of the active locale's DATE_INPUT_FORMATS (es-co → '%d/%m/%Y'), which
        the browser rejects for <input type="date">.
        """
        form = UserEditForm(instance=self.user)
        rendered = str(form["hire_date"])
        self.assertIn(
            'value="2024-01-15"',
            rendered,
            f"Esperaba value ISO YYYY-MM-DD, obtuve: {rendered}",
        )
        # Negative assertion: must NOT contain es-co localized format.
        self.assertNotIn('value="15/01/2024"', rendered)

    def test_form_accepts_iso_post_and_updates_hire_date(self):
        """POST con hire_date='2025-03-20' debe persistir la nueva fecha."""
        new_date = "2025-03-20"
        post_data = {
            "email": self.user.email or "",
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "document_type": self.user.document_type,
            "document_number": self.user.document_number,
            "phone": self.user.phone or "",
            "job_position": self.user.job_position,
            "job_profile": self.profile.pk,
            "employment_type": self.user.employment_type,
            "hire_date": new_date,
            "status": self.user.status,
            "is_active": self.user.is_active,
            "is_staff": self.user.is_staff,
        }
        form = UserEditForm(post_data, instance=self.user)
        self.assertTrue(form.is_valid(), f"Form inválido: {form.errors.as_json()}")
        updated = form.save()
        updated.refresh_from_db()
        self.assertEqual(
            updated.hire_date,
            date(2025, 3, 20),
            f"hire_date no se actualizó: {updated.hire_date}",
        )

    def test_form_keeps_existing_hire_date_when_only_other_field_changes(self):
        """Editar solo first_name no debe perder hire_date.

        Este es el caso visible al usuario: cambia el nombre, no toca el
        datepicker. Tras el fix, el browser re-emite el value ISO original
        en el POST, así que el form valida y persiste el cambio sin perder
        la fecha original.
        """
        original = self.user.hire_date
        post_data = {
            "email": self.user.email or "",
            "first_name": "Nombre Modificado",  # único cambio real
            "last_name": self.user.last_name,
            "document_type": self.user.document_type,
            "document_number": self.user.document_number,
            "phone": self.user.phone or "",
            "job_position": self.user.job_position,
            "job_profile": self.profile.pk,
            "employment_type": self.user.employment_type,
            # Browser re-emite el value tal como lo renderizó (ISO tras el fix).
            "hire_date": original.strftime("%Y-%m-%d"),
            "status": self.user.status,
            "is_active": self.user.is_active,
            "is_staff": self.user.is_staff,
        }
        form = UserEditForm(post_data, instance=self.user)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        updated = form.save()
        updated.refresh_from_db()
        self.assertEqual(updated.hire_date, original)
        self.assertEqual(updated.first_name, "Nombre Modificado")


class UserCreateFormHireDateTests(TestCase):
    """Mismo fix aplicado en UserCreateForm — defensa simétrica."""

    def test_create_form_accepts_iso_hire_date(self):
        """Crear usuario con hire_date ISO debe persistir la fecha correcta."""
        profile, _ = JobProfileType.objects.get_or_create(
            code="TECNICO",
            defaults={"name": "Técnico", "is_active": True},
        )
        post_data = {
            "email": "new_sd41@example.com",
            "first_name": "Nuevo",
            "last_name": "Usuario",
            "document_type": "CC",
            "document_number": "99999_sd41",
            "phone": "",
            "job_position": "Técnico",
            "job_profile": profile.pk,
            "employment_type": "direct",
            "hire_date": "2025-06-01",
            "status": "active",
        }
        form = UserCreateForm(post_data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        self.assertEqual(user.hire_date, date(2025, 6, 1))
