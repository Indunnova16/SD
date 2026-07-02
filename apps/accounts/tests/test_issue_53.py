"""Tests for SD#53 — el partial HTMX de login (login_form.html) quedó
referenciando el campo legacy `form.email`, removido del LoginForm en 3181fc2
(migración a autenticación dual con `form.username`). Django resuelve
form.email silenciosamente como vacío, así que tras cualquier POST fallido el
swap de #login-form-container dejaba el input, el placeholder
('Número de cédula o correo@ejemplo.com') y el help_text ('Personal
operativo: número de cédula. Personal profesional: correo electrónico.')
completamente ausentes — solo sobrevivía la etiqueta 'Correo electrónico'.

Fix: ambos templates (login.html y partials/login_form.html) ahora incluyen
el mismo partial compartido `partials/_username_field.html`, así no pueden
volver a divergir.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class LoginFormPartialUsernameFieldTests(TestCase):
    """Reproduce el escenario exacto del cliente: login fallido vía HTMX debe
    seguir mostrando el campo de usuario completo, no solo la etiqueta."""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("accounts:login")
        # Usuario legacy pre-existente, análogo al dato real contra el que se
        # reprodujo el bug (no solo una fixture nueva del test).
        self.user = User.objects.create_user(
            email="legacy_sd53@example.com",
            password="correctpassword123",
            first_name="Legacy",
            last_name="User",
            document_type="CC",
            document_number="99887766",
            hire_date=date(2024, 1, 1),
        )

    def _post_invalid_login(self, htmx=False):
        headers = {"HTTP_HX-Request": "true"} if htmx else {}
        return self.client.post(
            self.login_url,
            {"username": "99887766", "password": "wrongpassword"},
            **headers,
        )

    def test_initial_get_shows_username_field(self):
        """Control: la carga inicial (GET, login.html) siempre mostró el
        input/placeholder/help_text correctos."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, "Número de cédula o correo@ejemplo.com")
        self.assertContains(
            response,
            "Personal operativo: número de cédula. Personal profesional: correo electrónico.",
        )

    def test_non_htmx_failed_login_shows_username_field(self):
        """Fallback no-HTMX (login.html) ya funcionaba antes del fix — no
        debe regresionar."""
        response = self._post_invalid_login(htmx=False)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, "Número de cédula o correo@ejemplo.com")
        self.assertContains(
            response,
            "Personal operativo: número de cédula. Personal profesional: correo electrónico.",
        )

    def test_htmx_failed_login_reproduces_client_report_before_fix(self):
        """Escenario reportado por el cliente: POST fallido vía HTMX
        (login_view() renderiza partials/login_form.html cuando
        request.htmx). Antes del fix, este response NO contenía
        name="username" ni el placeholder/help_text — solo la etiqueta
        'Correo electrónico'. Con el fix (partial compartido
        _username_field.html), debe mostrar el mismo campo que el GET
        inicial."""
        response = self._post_invalid_login(htmx=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/login_form.html")
        self.assertContains(response, "Credenciales inválidas")
        # El bug real: el input, placeholder y help_text del campo username
        # desaparecían por completo tras el POST fallido.
        self.assertContains(response, 'name="username"')
        self.assertContains(response, "Número de cédula o correo@ejemplo.com")
        self.assertContains(
            response,
            "Personal operativo: número de cédula. Personal profesional: correo electrónico.",
        )
        # El campo legacy inexistente no debe volver a aparecer.
        self.assertNotContains(response, 'name="email"')
        self.assertNotContains(response, "id_email")

    def test_htmx_and_non_htmx_render_same_username_field_markup(self):
        """Paridad exacta: ambos caminos ahora comparten el mismo include, así
        que ya no pueden divergir de nuevo como pasó con form.email vs
        form.username en SD#53."""
        htmx_response = self._post_invalid_login(htmx=True)
        non_htmx_response = self._post_invalid_login(htmx=False)

        def extract_username_block(content: str) -> str:
            start = content.index('for="id_username"')
            end = content.index("</div>", content.index("label-text-alt text-gray-500", start))
            return content[start:end]

        htmx_block = extract_username_block(htmx_response.content.decode())
        non_htmx_block = extract_username_block(non_htmx_response.content.decode())
        self.assertEqual(htmx_block, non_htmx_block)
