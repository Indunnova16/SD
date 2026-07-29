"""
Tests de "resolver el caso" desde el portal (issue #71 ronda 2).

Reclamo literal del cliente: *"ni puede resolver el caso"*.
"""

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

import requests

from apps.feedback.github_client import GitHubClientError, GitHubFeedbackClient
from apps.feedback.models import FeedbackTicket
from apps.feedback.services import resolver_ticket


class CerrarIssueClientTestCase(TestCase):
    def setUp(self):
        self.client_gh = GitHubFeedbackClient(token="tok", repo="Indunnova16/SD")

    @patch("apps.feedback.github_client.requests.patch")
    @patch("apps.feedback.github_client.requests.post")
    def test_comenta_y_despues_cierra(self, mock_post, mock_patch):
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 99})
        mock_patch.return_value = Mock(status_code=200, json=lambda: {})

        resultado = self.client_gh.cerrar_issue(72, comentario="Ana lo resolvió")

        self.assertEqual(resultado, {"state": "closed", "comment_id": 99})
        self.assertIn("/issues/72/comments", mock_post.call_args[0][0])
        self.assertEqual(mock_post.call_args[1]["json"], {"body": "Ana lo resolvió"})
        self.assertEqual(mock_patch.call_args[1]["json"], {"state": "closed"})

    @patch("apps.feedback.github_client.requests.patch")
    @patch("apps.feedback.github_client.requests.post")
    def test_sin_comentario_no_postea(self, mock_post, mock_patch):
        mock_patch.return_value = Mock(status_code=200, json=lambda: {})

        resultado = self.client_gh.cerrar_issue(72)

        mock_post.assert_not_called()
        self.assertIsNone(resultado["comment_id"])

    @patch("apps.feedback.github_client.requests.patch")
    def test_status_inesperado_al_cerrar_levanta_error(self, mock_patch):
        mock_patch.return_value = Mock(status_code=403, text="Forbidden")

        with self.assertRaises(GitHubClientError):
            self.client_gh.cerrar_issue(72)

    @patch("apps.feedback.github_client.requests.patch")
    def test_error_de_red_se_normaliza(self, mock_patch):
        mock_patch.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(GitHubClientError):
            self.client_gh.cerrar_issue(72)


class ResolverTicketServiceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
            github_issue_number=72,
            sincronizado_github=True,
        )

    def test_estado_por_defecto_es_abierto(self):
        self.assertEqual(self.ticket.estado, FeedbackTicket.ESTADO_ABIERTO)
        self.assertFalse(self.ticket.esta_resuelto)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_happy_path_marca_resuelto_y_cierra_el_issue(self, mock_cls):
        ok = resolver_ticket(self.ticket.id, "Ana Pérez")

        self.assertTrue(ok)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, FeedbackTicket.ESTADO_RESUELTO)
        self.assertEqual(self.ticket.resuelto_por, "Ana Pérez")
        self.assertIsNotNone(self.ticket.resuelto_at)
        mock_cls.return_value.cerrar_issue.assert_called_once()
        self.assertEqual(mock_cls.return_value.cerrar_issue.call_args[0][0], 72)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_github_caido_igual_resuelve_localmente(self, mock_cls):
        """La intención del usuario no puede perderse porque GitHub falle."""
        mock_cls.return_value.cerrar_issue.side_effect = GitHubClientError("503")

        ok = resolver_ticket(self.ticket.id, "Ana Pérez")

        self.assertFalse(ok)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, FeedbackTicket.ESTADO_RESUELTO)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_idempotente_no_vuelve_a_llamar_a_github(self, mock_cls):
        resolver_ticket(self.ticket.id, "Ana Pérez")
        mock_cls.reset_mock()

        ok = resolver_ticket(self.ticket.id, "Otro")

        self.assertTrue(ok)
        mock_cls.return_value.cerrar_issue.assert_not_called()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.resuelto_por, "Ana Pérez")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_ticket_sin_issue_resuelve_local_sin_llamar_a_github(self, mock_cls):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="B", asunto="Sin sync", descripcion="x" * 20
        )

        ok = resolver_ticket(ticket.id, "Ana")

        self.assertFalse(ok)
        mock_cls.assert_not_called()
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, FeedbackTicket.ESTADO_RESUELTO)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_el_comentario_deja_registro_de_quien_resolvio(self, mock_cls):
        resolver_ticket(self.ticket.id, "Ana Pérez")

        comentario = mock_cls.return_value.cerrar_issue.call_args[1]["comentario"]
        self.assertIn("Ana Pérez", comentario)
        self.assertIn("resuelto", comentario)


class ResolverViewTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
            github_issue_number=72,
            sincronizado_github=True,
        )
        self.url = reverse("feedback:resolver", kwargs={"ticket_id": self.ticket.id})
        self.detalle_url = reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_post_valido_resuelve_y_redirige(self, mock_cls):
        response = self.client.post(self.url, data={"resuelto_por": "Ana Pérez"})

        self.assertRedirects(response, self.detalle_url)
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.esta_resuelto)

    def test_get_no_resuelve(self):
        """Resolver es mutativo: un prefetch o un crawler no puede cerrarlo."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.esta_resuelto)

    def test_nombre_vacio_no_resuelve_y_muestra_error(self):
        response = self.client.post(self.url, data={"resuelto_por": ""})

        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.esta_resuelto)
        self.assertTrue(response.context["resolver_form"].errors)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_honeypot_poblado_no_resuelve(self, mock_cls):
        response = self.client.post(
            self.url, data={"resuelto_por": "Bot", "website": "http://spam"}
        )

        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.esta_resuelto)
        # El re-render del detalle SÍ consulta comentarios (es la misma
        # página); lo que no puede haber pasado es el cierre del issue.
        mock_cls.return_value.cerrar_issue.assert_not_called()

    def test_ticket_inexistente_404(self):
        url = reverse("feedback:resolver", kwargs={"ticket_id": 999999})

        response = self.client.post(url, data={"resuelto_por": "Ana"})

        self.assertEqual(response.status_code, 404)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_resolver_dos_veces_es_idempotente(self, mock_cls):
        self.client.post(self.url, data={"resuelto_por": "Ana Pérez"})
        response = self.client.post(self.url, data={"resuelto_por": "Otro"})

        self.assertRedirects(response, self.detalle_url)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.resuelto_por, "Ana Pérez")


class DetalleMuestraEstadoTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
        )
        self.url = reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})

    def test_ticket_abierto_muestra_boton_resolver(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Resolver el caso")
        self.assertContains(response, 'id="form-resolver"')
        self.assertContains(response, "🔵 Abierto")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_ticket_resuelto_oculta_el_boton_y_muestra_quien(self, mock_cls):
        resolver_ticket(self.ticket.id, "Ana Pérez")

        response = self.client.get(self.url)

        self.assertNotContains(response, 'id="form-resolver"')
        self.assertContains(response, "🟢 Resuelto")
        self.assertContains(response, "Resuelto por")

    def test_lista_muestra_el_estado(self):
        response = self.client.get(reverse("feedback:lista"))

        self.assertContains(response, "🔵 Abierto")
