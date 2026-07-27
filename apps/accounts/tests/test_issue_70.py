"""Tests for issue #70 — bug de scope Alpine.js en el navbar mobile.

Diagnóstico F2 (confirmado con Playwright real, viewport 375x812 contra
las 3 URLs pedidas por el cliente: /accounts/, /reports/dashboard/,
/courses/): `x-data="{ mobileMenuOpen: false }"` vivía en `<nav>`
(templates/partials/navbar.html líneas 3-6), pero `<nav>` cierra antes
de `#mobile-menu` (que es HERMANO de `<nav>` dentro de `<header>`, no
descendiente). Alpine.js solo resuelve scope reactivo ancestro→
descendiente, nunca entre hermanos — por eso el botón hamburguesa
togglea el ícono (dentro del scope de `<nav>`) pero el panel
`#mobile-menu` nunca se hace visible (0/18 links visibles tras click
en los 3 casos reales).

Fix (F3): mover `x-data="{ mobileMenuOpen: false }"` de `<nav>` al
`<header>` ancestro común — sin tocar nada más (el botón hamburguesa,
sus íconos y el panel `#mobile-menu`, incluyendo "Cerrar Sesión" en
líneas 327-330 de navbar.html, quedan como descendientes reales).

Este test verifica el fix por ESTRUCTURA DOM del HTML renderizado
(assertions sobre el tag de apertura de `<header>` y de `<nav>`), que
es lo verificable con el Django test client — Alpine.js no se ejecuta
en este entorno (no hay navegador real). La confirmación visual
interactiva (click real en viewport móvil, panel se hace visible) es
responsabilidad de F5 (re-verificación post-deploy), no de este test.

Suite exclusivo de este issue (RUN con issues hermanos SD#69 y SD#62
en otros worktrees) — no se apendea a `test_views.py` ni otros módulos
compartidos.

Refs #70
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class NavbarAlpineScopeIssue70Tests(TestCase):
    """El x-data de mobileMenuOpen debe vivir en <header>, no en <nav>."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="nav_i70@example.com",
            password="testpassword123",
            first_name="Nav",
            last_name="Issue70",
            document_type="CC",
            document_number="70707070",
            hire_date=date(2024, 1, 1),
        )
        self.client.login(username="70707070", password="testpassword123")

    @staticmethod
    def _opening_tag(html, pattern):
        """Devuelve el tag de apertura completo (hasta el primer '>')
        que matchea `pattern`, incluyendo atributos multilinea."""
        match = re.search(pattern, html, re.DOTALL)
        return match.group(0) if match else None

    def test_header_carries_x_data_mobile_menu_open(self):
        """<header> (el ancestro común de la navbar y de #mobile-menu)
        debe declarar x-data con mobileMenuOpen."""
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        header_tag = self._opening_tag(html, r"<header\b[^>]*>")
        self.assertIsNotNone(
            header_tag,
            "No se encontro el tag <header> en el HTML renderizado del dashboard",
        )
        self.assertIn(
            "x-data",
            header_tag,
            "El <header> del navbar debe declarar x-data (scope de mobileMenuOpen) "
            "para que #mobile-menu (hermano de <nav>) sea descendiente reactivo real.",
        )
        self.assertIn("mobileMenuOpen", header_tag)

    def test_nav_no_longer_carries_x_data(self):
        """<nav class="navbar ..."> ya NO debe declarar x-data — moverlo
        de vuelta rompería el scope para #mobile-menu (hermano de <nav>)."""
        response = self.client.get(reverse("accounts:dashboard"))
        html = response.content.decode()

        nav_tag = self._opening_tag(html, r'<nav\s+class="navbar\b[^>]*>')
        self.assertIsNotNone(
            nav_tag,
            'No se encontro el tag <nav class="navbar ..."> en el HTML renderizado',
        )
        self.assertNotIn(
            "x-data",
            nav_tag,
            "<nav> no debe declarar x-data propio: mobileMenuOpen vive en <header> "
            "(el bug original era exactamente que <nav> lo declaraba localmente).",
        )

    def test_mobile_menu_panel_is_descendant_of_header_not_nav(self):
        """#mobile-menu debe seguir siendo hermano de <nav> dentro de
        <header> (no se reestructura el DOM, solo se mueve x-data) —
        confirma que el fix no cambia jerarquía, solo el scope Alpine."""
        response = self.client.get(reverse("accounts:dashboard"))
        html = response.content.decode()

        nav_close_idx = html.find("</nav>")
        mobile_menu_idx = html.find('id="mobile-menu"')
        header_close_idx = html.find("</header>")

        self.assertNotEqual(nav_close_idx, -1)
        self.assertNotEqual(mobile_menu_idx, -1)
        self.assertNotEqual(header_close_idx, -1)
        self.assertTrue(
            nav_close_idx < mobile_menu_idx < header_close_idx,
            "#mobile-menu debe quedar entre </nav> y </header> (hermano de <nav>, "
            "descendiente de <header>) — la topologia del DOM no cambia con este fix.",
        )
