"""Tests para SD#119 — "Ir al curso" no navega + contador junto a "Sistema".

El cliente reportó (body del issue, sin comentarios adicionales, imagenes
adjuntas leidas en F1):
  1. La campanita/menu "Sistema" ya funciona ("perfecto"), pero pide que el
     CONTADOR de no-leidas aparezca junto a "Sistema" en si (hoy solo se ve
     el badge de "Notificaciones" DENTRO del submenu, una vez abierto).
  2. En `/notifications/`, el boton "Ir al curso" de una notificacion no
     hace nada / muestra el toast global "Error en la solicitud. Por favor,
     intente nuevamente." (captura adjunta al issue).

Diagnostico F2: en `templates/notifications/partials/notification_items.html`
el `<a href="{{ notification.action_url }}">` (el boton "Ir al curso") tenia
ademas `hx-get="{% url 'notifications:mark-read' ... %}" hx-swap="none"`.
htmx intercepta el click de CUALQUIER elemento con hx-get/post (preventDefault
sobre la navegacion nativa) para hacer la llamada AJAX en su lugar — y esa
vista (`mark_read`) es `@require_POST`, asi que un `hx-get` le pega con el
verbo equivocado -> 405 -> el handler global `htmx:responseError` de
`templates/base/base.html` muestra exactamente el toast de la captura. Aunque
el verbo estuviera bien, `hx-swap="none"` descarta la respuesta: el boton
NUNCA iba a navegar al curso, por diseño de la interceptacion de htmx.

Fix (F3): el `<a>` vuelve a ser un link plano (navega de verdad via `href`)
y el marcado-como-leida se dispara en paralelo via `fetch(..., {keepalive:
true})` en `onclick`, que no bloquea ni previene la navegacion nativa.
Para el contador junto a "Sistema": se agrega un segundo span
`#navbar-notif-badge-sistema` con el mismo `hx-get` de
`notifications:unread-count`, ahora DENTRO de `<summary>` (visible sin abrir
el dropdown), en `templates/partials/navbar.html`.

Refs #119
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.tests.factories import NotificationWithActionFactory

User = get_user_model()


def _make_user(**overrides):
    defaults = {
        "email": "issue119_user@example.com",
        "password": "testpass123",
        "first_name": "User",
        "last_name": "Issue119",
        "document_type": "CC",
        "document_number": "1190000001",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class NotificationActionButtonNavigatesTests(TestCase):
    """El boton de accion ("Ir al curso"/"Ver") debe navegar de verdad."""

    def setUp(self):
        self.client = Client()
        self.user = _make_user()
        self.client.force_login(self.user)

    @staticmethod
    def _action_anchor(html, action_url):
        """Extrae el tag de apertura del <a> cuyo href es `action_url`."""
        pattern = r'<a\s+href="' + re.escape(action_url) + r'"[^>]*>'
        match = re.search(pattern, html, re.DOTALL)
        return match.group(0) if match else None

    def test_action_anchor_no_lleva_hx_get_que_bloquee_la_navegacion(self):
        """Regresion directa del bug: el <a href="action_url"> NO debe tener
        hx-get (eso es lo que interceptaba el click e impedia navegar)."""
        notif = NotificationWithActionFactory(
            user=self.user, action_url="/courses/42/", action_text="Ir al curso"
        )

        response = self.client.get(
            reverse("notifications:list"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        anchor = self._action_anchor(html, notif.action_url)
        self.assertIsNotNone(
            anchor,
            "No se encontro el <a href> de accion en el HTML renderizado "
            "de la lista de notificaciones.",
        )
        self.assertNotIn(
            "hx-get",
            anchor,
            "El <a> de accion no debe tener hx-get: htmx previene la "
            "navegacion nativa del <a> en cualquier elemento con hx-get/post, "
            "y ademas mark-read es @require_POST (hx-get -> 405 -> toast de "
            "error). Esa combinacion es exactamente el bug de SD#119.",
        )
        self.assertIn("Ir al curso", html)

    def test_action_anchor_dispara_mark_read_sin_bloquear_click(self):
        """El marcado-como-leida se preserva, pero via fetch en background
        (onclick), no via hx-get bloqueando la navegacion."""
        notif = NotificationWithActionFactory(
            user=self.user, action_url="/courses/42/", action_text="Ir al curso"
        )
        mark_read_url = reverse("notifications:mark-read", args=[notif.id])

        response = self.client.get(
            reverse("notifications:list"), HTTP_HX_REQUEST="true"
        )
        html = response.content.decode()
        anchor = self._action_anchor(html, notif.action_url)

        self.assertIn(mark_read_url, anchor)
        self.assertIn("fetch(", anchor)
        self.assertIn("keepalive", anchor)

    def test_mark_read_sigue_siendo_post_only(self):
        """Guarda de regresion: si alguien reintroduce hx-get sobre esta
        vista, este test lo atrapa (GET debe seguir en 405)."""
        notif = NotificationWithActionFactory(user=self.user)
        url = reverse("notifications:mark-read", args=[notif.id])

        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(url)
        self.assertEqual(post_response.status_code, 200)
        notif.refresh_from_db()
        self.assertIsNotNone(notif.read_at)

    def test_notification_sin_action_url_no_rompe(self):
        """Notificaciones sin action_url (la mayoria) no deben renderizar
        ningun boton de accion ni fallar."""
        Notification.objects.create(
            user=self.user,
            subject="Sin accion",
            body="cuerpo",
            action_url="",
            action_text="",
        )
        response = self.client.get(
            reverse("notifications:list"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sin accion", response.content.decode())


class NavbarSistemaBadgeTests(TestCase):
    """El contador de no-leidas debe verse junto al toggle "Sistema", sin
    necesidad de abrir el submenu."""

    def setUp(self):
        self.client = Client()
        self.user = _make_user(
            email="issue119_navbar@example.com", document_number="1190000002"
        )
        self.client.force_login(self.user)

    def test_summary_sistema_incluye_badge_de_no_leidas(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        match = re.search(
            r"<summary>.*?Sistema.*?</summary>", html, re.DOTALL
        )
        self.assertIsNotNone(
            match, "No se encontro el <summary>Sistema...</summary> del navbar."
        )
        summary_html = match.group(0)

        self.assertIn(
            'id="navbar-notif-badge-sistema"',
            summary_html,
            "El toggle 'Sistema' debe traer su propio badge de no-leidas, "
            "visible sin necesidad de abrir el dropdown (pedido explicito "
            "del cliente en SD#119).",
        )
        self.assertIn(reverse("notifications:unread-count"), summary_html)

    def test_badge_sistema_hace_polling_igual_que_el_de_notificaciones(self):
        """Mismo patron hx-trigger que el badge existente junto a
        'Notificaciones' (load + cada 30s) — consistencia, no una
        implementacion ad-hoc distinta."""
        response = self.client.get(reverse("accounts:dashboard"))
        html = response.content.decode()

        badge_pattern = (
            r'<span id="navbar-notif-badge-sistema"[^>]*hx-trigger="load, '
            r'every 30s"[^>]*></span>'
        )
        self.assertRegex(html, badge_pattern)
