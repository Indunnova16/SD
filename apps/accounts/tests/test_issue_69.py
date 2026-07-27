"""Tests for SD#69 — branding: logo genérico + paleta azul -> logo real de
Salomón Durán S.A.S. + rojo corporativo (#e4020f, medido por análisis de
píxeles del logo real, MD5 confirmado idéntico al adjunto del issue).

Cubre las 4 superficies navegables/generables del fix:

1. navbar.html (dashboard, base/base.html) — <img data-logo="sd-sas-real">
   reemplaza el <svg> genérico + "SD LMS".
2. Paleta Tailwind 'primary' + variables OKLCH --p/--pc en base/base.html
   (bloque repetido byte-a-byte en accounts/base_auth.html, cubre también
   login/reset password) — azul (#3b82f6/#2563eb) -> rojo (#e4020f).
3. accounts/user_profile_pdf.html (fuente HTML antes de xhtml2pdf.pisa) —
   #2563eb -> #e4020f, badges de status semánticos intactos.
4. accounts/emails/password_reset.html (html_message del email de reset,
   nunca servido como página HTTP) — #3b82f6 -> #e4020f.

certificate_template.html (ya en #E50019) y dashboard/gamificación quedan
fuera de scope explícito — no se tocan ni se testean aquí.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

# Hex de marca vieja (azul) que NO debe sobrevivir en ninguna de las 4
# superficies del fix, y el nuevo hex rojo medido del logo real.
OLD_BLUE_TAILWIND = "#3b82f6"
OLD_BLUE_TAILWIND_600 = "#2563eb"
NEW_RED = "#e4020f"


class NavbarLogoRealTests(TestCase):
    """navbar.html debe mostrar el logo real, no el <svg> genérico."""

    def setUp(self):
        self.client = Client()
        self.dashboard_url = reverse("accounts:dashboard")
        self.user = User.objects.create_user(
            email="navtest_sd69@example.com",
            password="testpassword123",
            first_name="Nav",
            last_name="Test",
            document_type="CC",
            document_number="69696901",
            hire_date=date(2024, 1, 1),
        )

    def test_dashboard_navbar_shows_real_logo(self):
        """Escenario del cliente: el navbar de la app autenticada debe usar
        el logo real de Salomón Durán S.A.S., con el atributo exacto que el
        journey de smoke ya asume (data-logo="sd-sas-real")."""
        self.client.login(username="69696901", password="testpassword123")
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-logo="sd-sas-real"')
        self.assertContains(response, "images/logo_sd_sas.png")

    def test_dashboard_navbar_no_longer_shows_generic_svg_or_sd_lms_text(self):
        """El <svg> genérico (huella única del path 'M12 3L1 9l4') y el
        texto 'SD LMS' del navbar ya no deben aparecer — reemplazados por
        el logo real."""
        self.client.login(username="69696901", password="testpassword123")
        response = self.client.get(self.dashboard_url)
        content = response.content.decode()
        self.assertNotIn("M12 3L1 9l4", content)
        self.assertNotIn(">SD LMS<", content)


class PrimaryColorPaletteTests(TestCase):
    """base/base.html (app autenticada) y accounts/base_auth.html
    (login/reset password) deben usar la paleta roja, no azul."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="palettetest_sd69@example.com",
            password="testpassword123",
            first_name="Palette",
            last_name="Test",
            document_type="CC",
            document_number="69696902",
            hire_date=date(2024, 1, 1),
        )

    def test_authenticated_dashboard_uses_red_not_blue(self):
        """base/base.html: la paleta Tailwind 'primary' y las variables
        OKLCH --p/--pc deben estar en rojo (#e4020f), no en el azul viejo."""
        self.client.login(username="69696902", password="testpassword123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(NEW_RED, content)
        self.assertNotIn(OLD_BLUE_TAILWIND, content)
        self.assertNotIn(OLD_BLUE_TAILWIND_600, content)
        # El hue OKLCH azul viejo (275.75) tampoco debe sobrevivir.
        self.assertNotIn("275.75", content)

    def test_login_page_uses_red_not_blue(self):
        """accounts/base_auth.html: el bloque de color repetido (login,
        reset password) es un duplicado byte-a-byte del de base.html — si
        solo se edita uno, /accounts/login/ queda azul. No requiere login."""
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(NEW_RED, content)
        self.assertNotIn(OLD_BLUE_TAILWIND, content)
        self.assertNotIn(OLD_BLUE_TAILWIND_600, content)
        self.assertNotIn("275.75", content)


class UserProfilePdfColorTests(TestCase):
    """accounts/user_profile_pdf.html — fuente HTML previa a la conversión
    xhtml2pdf.pisa (el PDF binario resultante no es assertable por color de
    forma determinística, per diagnóstico F2; se testea la fuente HTML
    exacta que la vista pasa a pisa.CreatePDF)."""

    def setUp(self):
        self.user_obj = User.objects.create_user(
            email="pdftest_sd69@example.com",
            password="testpassword123",
            first_name="Pdf",
            last_name="Test",
            document_type="CC",
            document_number="69696903",
            hire_date=date(2024, 1, 1),
        )

    def _render_pdf_source(self):
        context = {
            "user_obj": self.user_obj,
            "enrollments": [],
            "completion_records": [],
            "total_enrollments": 0,
            "completed_count": 0,
            "in_progress_count": 0,
            "pending_count": 0,
            "generated_at": timezone.now(),
            "request_user": self.user_obj,
        }
        return render_to_string("accounts/user_profile_pdf.html", context)

    def test_pdf_source_uses_red_not_blue(self):
        html_string = self._render_pdf_source()
        self.assertIn(NEW_RED, html_string)
        self.assertNotIn(OLD_BLUE_TAILWIND_600, html_string)

    def test_pdf_status_badges_remain_semantic_untouched(self):
        """Los badges de status (verde/rojo/azul/ámbar) son semánticos por
        estado, no de marca — deben seguir intactos tras el fix."""
        html_string = self._render_pdf_source()
        self.assertIn(".badge-active { background-color: #d1fae5;", html_string)
        self.assertIn(".badge-in_progress { background-color: #dbeafe;", html_string)


class PasswordResetEmailColorTests(TestCase):
    """accounts/emails/password_reset.html — html_message del email de
    reset, nunca servido como página HTTP (no navegable), validado vía
    django.core.mail.outbox tras disparar el flujo real de la vista."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="emailtest_sd69@example.com",
            password="testpassword123",
            first_name="Email",
            last_name="Test",
            document_type="CC",
            document_number="69696904",
            hire_date=date(2024, 1, 1),
        )
        self.password_reset_url = reverse("accounts:password_reset")

    def test_password_reset_email_html_uses_red_not_blue(self):
        response = self.client.post(self.password_reset_url, {"email": self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        # html_message se adjunta como alternative text/html en send_mail().
        self.assertEqual(len(sent.alternatives), 1)
        html_body, mimetype = sent.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn(NEW_RED, html_body)
        self.assertNotIn(OLD_BLUE_TAILWIND, html_body)
