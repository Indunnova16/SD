"""
Tests de la conversación de GitHub dentro del portal (issue #71 ronda 2).

Reclamos que cubren:
  - *"el usuario no puede ver los comentarios ... en el ticket"*.
  - Requisito literal del body del issue: *"que el usuario pueda ver las
    imágenes cargadas en GH desde su portal"*. La v1.0 lo implementó al
    revés (mostraba las imágenes que el usuario había subido); lo que falta
    es que se vean las imágenes que el equipo carga **en GitHub**.
"""

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

import requests

from apps.feedback.github_client import GitHubClientError, GitHubFeedbackClient
from apps.feedback.models import FeedbackTicket
from apps.feedback.services import obtener_comentarios_github
from apps.feedback.templatetags.feedback_markdown import markdownify

# Formato EXACTO con el que GitHub guarda una captura pegada en un
# comentario — copiado del comentario del revisor en el issue #71.
IMG_HTML_GITHUB = (
    '<img width="1236" height="702" alt="Image" '
    'src="https://github.com/user-attachments/assets/ea568f93-be82-43b6-90c7-f8fc5bcbb7c2" />'
)


class MarkdownifyTestCase(TestCase):
    """El filtro que hace visibles las imágenes de GitHub en el portal."""

    def test_imagen_markdown_se_renderiza_como_img(self):
        html = markdownify("![captura](https://github.com/user-attachments/assets/abc-123)")

        self.assertIn("<img", html)
        self.assertIn("https://github.com/user-attachments/assets/abc-123", html)

    def test_imagen_html_cruda_de_github_sobrevive_al_saneo(self):
        """El caso real: GitHub pega la captura como <img>, no como markdown.

        Si bleach quitara `img` o el atributo `src`, el cliente seguiría sin
        ver las imágenes — que es exactamente el reclamo.
        """
        html = markdownify("mirá esto\n\n" + IMG_HTML_GITHUB)

        self.assertIn("<img", html)
        self.assertIn(
            "https://github.com/user-attachments/assets/ea568f93-be82-43b6-90c7-f8fc5bcbb7c2",
            html,
        )
        self.assertIn('width="1236"', html)

    def test_script_se_elimina(self):
        """El issue es público: cualquiera puede comentar HTML en él.

        bleach con `strip=True` borra el TAG y deja el texto interno como
        texto plano inerte (`<p>hola alert('xss') chau</p>`). Lo que se
        verifica es que no sobreviva ningún `<script>` ejecutable, no que
        desaparezca la cadena "alert(".
        """
        html = markdownify("hola <script>alert('xss')</script> chau")

        self.assertNotIn("<script", html)
        self.assertNotIn("</script>", html)

    def test_handler_inline_se_elimina(self):
        html = markdownify('<img src="https://x/y.png" onerror="alert(1)">')

        self.assertNotIn("onerror", html)

    def test_protocolo_javascript_se_elimina(self):
        html = markdownify('<a href="javascript:alert(1)">click</a>')

        self.assertNotIn("javascript:", html)

    def test_formato_basico_se_conserva(self):
        html = markdownify("**negrita** y `código`\n\n- uno\n- dos")

        self.assertIn("<strong>", html)
        self.assertIn("<code>", html)
        self.assertIn("<li>", html)

    def test_vacio_devuelve_cadena_vacia(self):
        self.assertEqual(markdownify(""), "")
        self.assertEqual(markdownify(None), "")


class ListarComentariosClientTestCase(TestCase):
    """`GitHubFeedbackClient.listar_comentarios`."""

    def setUp(self):
        self.client_gh = GitHubFeedbackClient(token="tok", repo="Indunnova16/SD")

    @patch("apps.feedback.github_client.requests.get")
    def test_parsea_solo_los_campos_que_el_portal_usa(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "body": "Ya lo estamos viendo.",
                    "user": {"login": "Indunnova", "avatar_url": "https://a/v.png"},
                    "created_at": "2026-07-28T10:00:00Z",
                    "html_url": "https://github.com/Indunnova16/SD/issues/72#issuecomment-1",
                    "author_association": "MEMBER",
                }
            ],
        )

        comentarios = self.client_gh.listar_comentarios(72)

        self.assertEqual(len(comentarios), 1)
        self.assertEqual(comentarios[0]["autor"], "Indunnova")
        self.assertEqual(comentarios[0]["cuerpo"], "Ya lo estamos viendo.")
        self.assertNotIn("author_association", comentarios[0])

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"], {"per_page": 100})

    @patch("apps.feedback.github_client.requests.get")
    def test_comentario_sin_usuario_no_rompe(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [{"body": "texto", "user": None, "created_at": ""}],
        )

        comentarios = self.client_gh.listar_comentarios(72)

        self.assertEqual(comentarios[0]["autor"], "equipo")

    @patch("apps.feedback.github_client.requests.get")
    def test_status_inesperado_levanta_github_client_error(self, mock_get):
        mock_get.return_value = Mock(status_code=404, text="Not Found")

        with self.assertRaises(GitHubClientError):
            self.client_gh.listar_comentarios(72)

    @patch("apps.feedback.github_client.requests.get")
    def test_error_de_red_se_normaliza_a_github_client_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(GitHubClientError):
            self.client_gh.listar_comentarios(72)


class ObtenerComentariosServiceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
            github_issue_number=72,
            github_url="https://github.com/Indunnova16/SD/issues/72",
            sincronizado_github=True,
        )

    def test_ticket_sin_issue_no_llama_a_github(self):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="B", asunto="Sin sync", descripcion="x" * 20
        )

        with patch("apps.feedback.services.GitHubFeedbackClient") as mock_cls:
            self.assertEqual(obtener_comentarios_github(ticket), [])

        mock_cls.assert_not_called()

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_filtra_comentarios_marcados_como_internos(self, mock_cls):
        mock_cls.return_value.listar_comentarios.return_value = [
            {
                "autor": "Indunnova",
                "cuerpo": "Visible para el cliente",
                "created_at": "",
                "url": "",
            },
            {
                "autor": "mbrt26",
                "cuerpo": "[INTERNO] revisar la BD de prod",
                "created_at": "",
                "url": "",
            },
        ]

        comentarios = obtener_comentarios_github(self.ticket)

        self.assertEqual(len(comentarios), 1)
        self.assertEqual(comentarios[0]["cuerpo"], "Visible para el cliente")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_usa_cache_en_la_segunda_llamada(self, mock_cls):
        mock_cls.return_value.listar_comentarios.return_value = []

        obtener_comentarios_github(self.ticket)
        obtener_comentarios_github(self.ticket)

        self.assertEqual(mock_cls.return_value.listar_comentarios.call_count, 1)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_error_de_github_se_propaga(self, mock_cls):
        """Propagar, no devolver [] — la vista necesita distinguir
        "no hay comentarios" de "no pudimos traerlos"."""
        mock_cls.return_value.listar_comentarios.side_effect = GitHubClientError("caído")

        with self.assertRaises(GitHubClientError):
            obtener_comentarios_github(self.ticket)


class DetalleMuestraComentariosTestCase(TestCase):
    """La vista de detalle — donde el cliente dijo que no ve nada."""

    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
            github_issue_number=72,
            sincronizado_github=True,
        )
        self.url = reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_muestra_autor_y_cuerpo_del_comentario(self, mock_cls):
        mock_cls.return_value.listar_comentarios.return_value = [
            {
                "autor": "Indunnova",
                "cuerpo": "Ya lo corregimos, probá de nuevo.",
                "created_at": "2026-07-28T10:00:00Z",
                "url": "",
            }
        ]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indunnova")
        self.assertContains(response, "Ya lo corregimos, probá de nuevo.")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_imagen_cargada_en_github_se_ve_en_el_portal(self, mock_cls):
        """Requisito literal del issue: "ver las imágenes cargadas en GH
        desde su portal"."""
        mock_cls.return_value.listar_comentarios.return_value = [
            {
                "autor": "Indunnova",
                "cuerpo": "Así se ve de nuestro lado:\n\n" + IMG_HTML_GITHUB,
                "created_at": "2026-07-28T10:00:00Z",
                "url": "",
            }
        ]

        response = self.client.get(self.url)

        self.assertContains(
            response,
            "https://github.com/user-attachments/assets/ea568f93-be82-43b6-90c7-f8fc5bcbb7c2",
        )
        self.assertContains(response, "<img")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_github_caido_no_rompe_el_detalle_y_avisa(self, mock_cls):
        mock_cls.return_value.listar_comentarios.side_effect = GitHubClientError("503")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ticket.asunto)
        self.assertTrue(response.context["comentarios_error"])
        self.assertContains(response, "No pudimos cargar la conversación")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_sin_comentarios_muestra_mensaje_vacio(self, mock_cls):
        mock_cls.return_value.listar_comentarios.return_value = []

        response = self.client.get(self.url)

        self.assertContains(response, "Todavía no hay respuestas del equipo")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_comentario_con_script_no_llega_al_html(self, mock_cls):
        mock_cls.return_value.listar_comentarios.return_value = [
            {
                "autor": "anonimo",
                "cuerpo": "<script>alert('xss')</script>",
                "created_at": "",
                "url": "",
            }
        ]

        response = self.client.get(self.url)

        self.assertNotContains(response, "<script>alert(")
