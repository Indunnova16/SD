"""
Tests for the custom staff admin panel of CertificateTemplate (B2 — SD#44).

Covers:
- Access control (staff_required) on all 5 views.
- CRUD: list / create (GET+POST valid/invalid) / edit (POST updates fields).
- Preview returns rendered HTML.
- HTMX toggle flips is_active and returns the row partial.
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.certifications.models import CertificateTemplate


class _BaseAdminViewsTests(TestCase):
    """Shared setUp: staff + non-staff user, one existing template."""

    def setUp(self):
        CertificateTemplate.objects.all().delete()

        self.staff = User.objects.create_user(
            email="staff-admin-tpl@example.com",
            password="testpass123",
            first_name="Staff",
            last_name="User",
            document_number="10000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
            rol=User.Rol.ADMINISTRADOR,
        )
        self.non_staff = User.objects.create_user(
            email="non-staff-tpl@example.com",
            password="testpass123",
            first_name="Regular",
            last_name="User",
            document_number="10000002",
            job_position="Estudiante",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=False,
        )
        self.template = CertificateTemplate.objects.create(
            name="Plantilla Demo",
            description="Plantilla para tests",
            template_file=SimpleUploadedFile(
                "plantilla_demo.html",
                b"<html><body>CERTIFICADO - {{ user_name }}</body></html>",
                content_type="text/html",
            ),
            signer_name="Directora HSEQ",
            signer_title="Directora",
            is_active=True,
        )


class TemplateListAccessTests(_BaseAdminViewsTests):
    def test_template_list_requires_staff(self):
        """Non-staff users get redirected to login."""
        self.client.force_login(self.non_staff)
        url = reverse("certifications:template_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_template_list_anonymous_redirected(self):
        """Anonymous users get redirected to login."""
        url = reverse("certifications:template_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_template_list_staff_ok(self):
        """Staff sees the list with existing templates."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plantilla Demo")


class TemplateCreateTests(_BaseAdminViewsTests):
    def test_template_create_get(self):
        """GET renders the empty form for staff."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # The form should be present (input for name field)
        self.assertContains(response, 'name="name"')

    def test_template_create_post_valid(self):
        """POST with valid data creates a new template and redirects to edit."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_create")
        initial_count = CertificateTemplate.objects.count()
        response = self.client.post(
            url,
            data={
                "name": "Plantilla Nueva",
                "description": "Creada en test",
                "template_file": SimpleUploadedFile(
                    "plantilla_nueva.html", b"<html></html>", content_type="text/html"
                ),
                "signer_name": "Firma X",
                "signer_title": "Cargo Y",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            CertificateTemplate.objects.count(),
            initial_count + 1,
        )
        new = CertificateTemplate.objects.get(name="Plantilla Nueva")
        self.assertRedirects(
            response,
            reverse("certifications:template_edit", args=[new.pk]),
        )

    def test_template_create_post_invalid(self):
        """POST without required `name` re-renders the form with errors."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_create")
        initial_count = CertificateTemplate.objects.count()
        response = self.client.post(
            url,
            data={
                "name": "",  # required → invalid
                "description": "sin nombre",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CertificateTemplate.objects.count(), initial_count)
        # form should have errors on name
        self.assertContains(response, 'name="name"')


class TemplateEditTests(_BaseAdminViewsTests):
    def test_template_edit_requires_staff(self):
        self.client.force_login(self.non_staff)
        url = reverse("certifications:template_edit", args=[self.template.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_template_edit_get_renders_form_with_instance(self):
        self.client.force_login(self.staff)
        url = reverse("certifications:template_edit", args=[self.template.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plantilla Demo")

    def test_template_edit_updates_fields(self):
        """POST update changes the instance."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_edit", args=[self.template.pk])
        response = self.client.post(
            url,
            data={
                "name": "Plantilla Demo Actualizada",
                "description": self.template.description,
                "signer_name": "Otro firmante",
                "signer_title": "Otro cargo",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.template.refresh_from_db()
        self.assertEqual(self.template.name, "Plantilla Demo Actualizada")
        self.assertEqual(self.template.signer_name, "Otro firmante")


class TemplatePreviewTests(_BaseAdminViewsTests):
    def test_template_preview_requires_staff(self):
        self.client.force_login(self.non_staff)
        url = reverse("certifications:template_preview", args=[self.template.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_template_preview_renders(self):
        """Preview returns 200 with HTML content."""
        self.client.force_login(self.staff)
        url = reverse("certifications:template_preview", args=[self.template.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should contain some text from the default template OR preview marker
        body = response.content.decode("utf-8")
        self.assertTrue(
            "CERTIFICADO" in body.upper()
            or "PREVIEW" in body.upper()
            or self.template.name in body,
            f"Preview output does not look like a certificate. Got: {body[:200]}",
        )


class TemplateToggleActiveTests(_BaseAdminViewsTests):
    def test_template_toggle_requires_staff(self):
        self.client.force_login(self.non_staff)
        url = reverse(
            "certifications:template_toggle_active",
            args=[self.template.pk],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_template_toggle_active_flips_value(self):
        """POST flips is_active and returns the row partial."""
        self.client.force_login(self.staff)
        original = self.template.is_active
        url = reverse(
            "certifications:template_toggle_active",
            args=[self.template.pk],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.template.refresh_from_db()
        self.assertEqual(self.template.is_active, not original)
        # Hit again → flips back
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.template.refresh_from_db()
        self.assertEqual(self.template.is_active, original)

    def test_template_toggle_get_not_allowed(self):
        """GET on toggle endpoint should be 405."""
        self.client.force_login(self.staff)
        url = reverse(
            "certifications:template_toggle_active",
            args=[self.template.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
