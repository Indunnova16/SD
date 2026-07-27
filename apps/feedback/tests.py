"""
Tests del sub-item A1 (app skeleton + modelos) del portal de feedback.

Cubre: __str__ de FeedbackTicket, que la migración 0001_initial aplica
limpio sobre la BD de test (implícito en que este módulo colecta y corre
sin errores de BD), y los valores por defecto de los campos de
sincronización con GitHub. Tests de A2-A8 (github_client, forms, services,
views) se agregan a este mismo archivo en sub-items posteriores.
"""

from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings

from apps.feedback.github_client import (
    LABEL_PORTAL_WEB,
    LABEL_PORTAL_WEB_COLOR,
    GitHubClientError,
    GitHubFeedbackClient,
)
from apps.feedback.models import FeedbackTicket


class ModelsTestCase(TestCase):
    """Tests de los modelos FeedbackTicket / FeedbackAttachment."""

    def test_str_devuelve_asunto(self):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
        )
        self.assertEqual(str(ticket), "El botón de descarga no funciona")

    def test_campos_por_defecto_al_crear(self):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="Carlos Ruiz",
            asunto="Sugerencia de mejora",
            descripcion="Sería útil poder filtrar los cursos por categoría.",
        )
        self.assertFalse(ticket.sincronizado_github)
        self.assertEqual(ticket.error_sincronizacion, "")
        self.assertIsNone(ticket.github_issue_number)
        self.assertEqual(ticket.github_url, "")

    def test_ordering_mas_reciente_primero(self):
        primero = FeedbackTicket.objects.create(
            nombre_reportante="A",
            asunto="Primero",
            descripcion="Descripción del primer ticket creado en la prueba.",
        )
        segundo = FeedbackTicket.objects.create(
            nombre_reportante="B",
            asunto="Segundo",
            descripcion="Descripción del segundo ticket creado en la prueba.",
        )
        tickets = list(FeedbackTicket.objects.all())
        self.assertEqual(tickets, [segundo, primero])


class GithubClientTestCase(TestCase):
    """Tests del sub-item A2 (cliente GitHub REST minimal)."""

    def _client(self):
        return GitHubFeedbackClient(token="ghp_test-token", repo="Indunnova16/SD")

    def _mock_response(self, status_code, json_data=None, text=""):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        return response

    @patch("apps.feedback.github_client.requests.post")
    def test_crear_issue_payload_correcto_y_parseo_201(self, mock_post):
        mock_post.return_value = self._mock_response(
            201,
            json_data={
                "number": 42,
                "html_url": "https://github.com/Indunnova16/SD/issues/42",
                "id": 999888777,
            },
        )
        client = self._client()

        asunto_largo = "X" * 300  # fuerza el truncado a 256 chars
        resultado = client.crear_issue(
            ticket_id=7,
            asunto=asunto_largo,
            descripcion="El botón de descarga no funciona en el curso de inducción.",
            nombre_reportante="Ana Pérez",
            adjuntos=[{"nombre": "captura.png", "url": "https://example.com/captura.png"}],
        )

        self.assertEqual(
            resultado,
            {
                "number": 42,
                "html_url": "https://github.com/Indunnova16/SD/issues/42",
                "id": 999888777,
            },
        )

        self.assertEqual(mock_post.call_count, 1)
        _args, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer ghp_test-token",
        )
        payload = kwargs["json"]
        self.assertEqual(len(payload["title"]), 256)
        self.assertTrue(payload["title"].startswith("[Portal] "))
        self.assertIn(
            "El botón de descarga no funciona en el curso de inducción.",
            payload["body"],
        )
        self.assertIn("Ana Pérez", payload["body"])
        self.assertIn("![captura.png](https://example.com/captura.png)", payload["body"])
        self.assertEqual(payload["labels"], ["portal-web"])
        self.assertEqual(payload["assignees"], ["Indunnova"])

    @patch("apps.feedback.github_client.requests.post")
    def test_asegurar_label_portal_web_idempotente_creada(self, mock_post):
        mock_post.return_value = self._mock_response(201)
        client = self._client()

        client.asegurar_label_portal_web()  # no debe lanzar

        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["name"], LABEL_PORTAL_WEB)
        self.assertEqual(kwargs["json"]["color"], LABEL_PORTAL_WEB_COLOR)

    @patch("apps.feedback.github_client.requests.post")
    def test_asegurar_label_portal_web_idempotente_ya_existe(self, mock_post):
        mock_post.return_value = self._mock_response(422, text="already_exists")
        client = self._client()

        client.asegurar_label_portal_web()  # 422 = ya existe, no debe lanzar

    @patch("apps.feedback.github_client.requests.post")
    def test_asegurar_label_portal_web_status_inesperado_levanta_error(self, mock_post):
        mock_post.return_value = self._mock_response(500, text="internal error")
        client = self._client()

        with self.assertRaises(GitHubClientError):
            client.asegurar_label_portal_web()

    @patch("apps.feedback.github_client.requests.post")
    def test_crear_issue_request_exception_se_relanza_como_github_client_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("connect timeout")
        client = self._client()

        with self.assertRaises(GitHubClientError):
            client.crear_issue(
                ticket_id=1,
                asunto="Asunto",
                descripcion="Descripción de prueba con suficiente longitud.",
                nombre_reportante="Carlos Ruiz",
            )

    @patch("apps.feedback.github_client.requests.post")
    def test_crear_issue_status_inesperado_levanta_github_client_error(self, mock_post):
        mock_post.return_value = self._mock_response(403, text="Forbidden")
        client = self._client()

        with self.assertRaises(GitHubClientError) as ctx:
            client.crear_issue(
                ticket_id=2,
                asunto="Asunto",
                descripcion="Descripción de prueba con suficiente longitud.",
                nombre_reportante="Carlos Ruiz",
            )
        self.assertIn("403", str(ctx.exception))

    @override_settings(GITHUB_FEEDBACK_TOKEN="   ", GITHUB_FEEDBACK_REPO="Indunnova16/SD")
    def test_token_vacio_tras_strip_levanta_github_client_error(self):
        with self.assertRaises(GitHubClientError):
            GitHubFeedbackClient()
