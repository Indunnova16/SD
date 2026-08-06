"""
Tests del issue #71 ronda 4 — lista consolidada de pendientes que dejó el
revisor (comentario 2026-08-01/2026-08-04) tras auditar `apps/feedback/`
contra la especificación funcional completa del portal:

1. Búsqueda pública por número de ticket.
2. Detección de posibles duplicados por palabras clave al crear un ticket.
4. Captura automática de IP del reportante (la fecha ya se capturaba desde
   v1.0 vía `created_at`/`auto_now_add`).
5. Comentar desde el portal, independiente de resolver.

El punto 3 (¿"resolver" debe exigir identificación?) es una decisión de
negocio pendiente de Indunnova — NO se implementa en esta ronda, así que no
tiene tests acá.
"""

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

import requests

from apps.feedback.github_client import GitHubClientError, GitHubFeedbackClient
from apps.feedback.models import FeedbackTicket
from apps.feedback.services import (
    buscar_posibles_duplicados,
    comentar_ticket,
    obtener_ip_cliente,
)


class ObtenerIpClienteTestCase(TestCase):
    """Sub-item #4 — captura automática de IP del reportante."""

    def _request(self, **meta):
        request = Mock()
        request.META = meta
        return request

    def test_usa_remote_addr_si_no_hay_x_forwarded_for(self):
        request = self._request(REMOTE_ADDR="203.0.113.5")
        self.assertEqual(obtener_ip_cliente(request), "203.0.113.5")

    def test_prioriza_x_forwarded_for_sobre_remote_addr(self):
        request = self._request(
            HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        self.assertEqual(obtener_ip_cliente(request), "203.0.113.9")

    def test_sin_ninguna_ip_devuelve_none(self):
        self.assertIsNone(obtener_ip_cliente(self._request()))

    def test_ip_malformada_en_header_no_lanza_devuelve_none(self):
        """Un `X-Forwarded-For` con basura no debe tumbar el INSERT del
        ticket (`GenericIPAddressField` es un `inet` en Postgres)."""
        request = self._request(HTTP_X_FORWARDED_FOR="no-es-una-ip")
        self.assertIsNone(obtener_ip_cliente(request))


class NuevoViewCapturaIpTestCase(TestCase):
    """Sub-item #4 — `nuevo_view` puebla `ip_reportante` al crear el ticket."""

    def _datos_validos(self, **overrides):
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "El botón de descarga no funciona",
            "descripcion": "Al hacer click en descargar el certificado no pasa nada.",
            "website": "",
        }
        datos.update(overrides)
        return datos

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_ip_reportante_queda_poblada_desde_remote_addr(self, mock_client_cls):
        mock_client_cls.return_value.crear_issue.return_value = {
            "number": 200,
            "html_url": "https://github.com/Indunnova16/SD/issues/200",
            "id": 1,
        }

        response = self.client.post(
            reverse("feedback:nuevo"),
            data=self._datos_validos(),
            REMOTE_ADDR="198.51.100.7",
        )

        self.assertEqual(response.status_code, 302)
        ticket = FeedbackTicket.objects.get(
            asunto="El botón de descarga no funciona"
        )
        self.assertEqual(ticket.ip_reportante, "198.51.100.7")


class BuscarPosiblesDuplicadosTestCase(TestCase):
    """Sub-item #1 — detección básica de duplicados por palabras clave."""

    def test_asunto_con_2_palabras_en_comun_es_duplicado(self):
        FeedbackTicket.objects.create(
            nombre_reportante="Ana",
            asunto="El certificado no descarga en Safari",
            descripcion="Descripción de prueba con longitud suficiente.",
        )

        posibles = buscar_posibles_duplicados(
            "El certificado no descarga en Chrome"
        )

        self.assertEqual(len(posibles), 1)
        self.assertEqual(posibles[0].asunto, "El certificado no descarga en Safari")

    def test_solo_1_palabra_en_comun_no_es_duplicado(self):
        FeedbackTicket.objects.create(
            nombre_reportante="Ana",
            asunto="El certificado no descarga",
            descripcion="Descripción de prueba con longitud suficiente.",
        )

        posibles = buscar_posibles_duplicados("Video de bienvenida se traba")

        self.assertEqual(posibles, [])

    def test_ignora_tickets_resueltos(self):
        resuelto = FeedbackTicket.objects.create(
            nombre_reportante="Ana",
            asunto="El certificado no descarga en Safari",
            descripcion="Descripción de prueba con longitud suficiente.",
        )
        resuelto.estado = FeedbackTicket.ESTADO_RESUELTO
        resuelto.save(update_fields=["estado"])

        posibles = buscar_posibles_duplicados(
            "El certificado no descarga en Chrome"
        )

        self.assertEqual(posibles, [])

    def test_excluye_id_dado(self):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana",
            asunto="El certificado no descarga en Safari",
            descripcion="Descripción de prueba con longitud suficiente.",
        )

        posibles = buscar_posibles_duplicados(
            "El certificado no descarga en Safari", excluir_id=ticket.id
        )

        self.assertEqual(posibles, [])

    def test_asunto_vacio_no_lanza_devuelve_vacio(self):
        self.assertEqual(buscar_posibles_duplicados(""), [])


class NuevoViewDuplicadosTestCase(TestCase):
    """Sub-item #1/#2 — `nuevo_view` interrumpe la creación ante posibles
    duplicados, salvo que el usuario confirme explícitamente."""

    def _datos_validos(self, **overrides):
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "El certificado no descarga en Chrome",
            "descripcion": "Al hacer click en descargar el certificado no pasa nada.",
            "website": "",
        }
        datos.update(overrides)
        return datos

    def setUp(self):
        self.existente = FeedbackTicket.objects.create(
            nombre_reportante="Carlos",
            asunto="El certificado no descarga en Safari",
            descripcion="Descripción de prueba con longitud suficiente.",
        )

    def test_asunto_similar_no_crea_ticket_y_muestra_advertencia(self):
        response = self.client.post(
            reverse("feedback:nuevo"), data=self._datos_validos()
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            FeedbackTicket.objects.filter(
                asunto="El certificado no descarga en Chrome"
            ).exists()
        )
        self.assertContains(response, "Ya hay ticket(s) abiertos")
        self.assertContains(response, self.existente.asunto)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_confirmar_duplicado_true_crea_el_ticket_igual(self, mock_client_cls):
        mock_client_cls.return_value.crear_issue.return_value = {
            "number": 201,
            "html_url": "https://github.com/Indunnova16/SD/issues/201",
            "id": 2,
        }

        response = self.client.post(
            reverse("feedback:nuevo"),
            data=self._datos_validos(confirmar_duplicado="true"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeedbackTicket.objects.filter(
                asunto="El certificado no descarga en Chrome"
            ).exists()
        )

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_asunto_sin_similares_crea_directo_sin_advertencia(
        self, mock_client_cls
    ):
        mock_client_cls.return_value.crear_issue.return_value = {
            "number": 202,
            "html_url": "https://github.com/Indunnova16/SD/issues/202",
            "id": 3,
        }

        response = self.client.post(
            reverse("feedback:nuevo"),
            data=self._datos_validos(asunto="Sugerencia de nuevo curso de Excel"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeedbackTicket.objects.filter(
                asunto="Sugerencia de nuevo curso de Excel"
            ).exists()
        )


class BuscarViewTestCase(TestCase):
    """Sub-item #1 — vista pública de búsqueda por número de ticket."""

    def setUp(self):
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Descripción de prueba con longitud suficiente.",
            github_issue_number=555,
        )

    def test_busca_por_id_interno_redirige_al_detalle(self):
        response = self.client.get(
            reverse("feedback:buscar"), {"numero": self.ticket.id}
        )
        self.assertRedirects(
            response,
            reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id}),
        )

    def test_busca_por_numero_de_issue_github_redirige_al_detalle(self):
        response = self.client.get(reverse("feedback:buscar"), {"numero": 555})
        self.assertRedirects(
            response,
            reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id}),
        )

    def test_numero_inexistente_redirige_a_lista_con_mensaje(self):
        response = self.client.get(
            reverse("feedback:buscar"), {"numero": 999999}, follow=True
        )
        self.assertRedirects(response, reverse("feedback:lista"))
        self.assertContains(response, "No encontramos ningún ticket")

    def test_numero_invalido_redirige_a_lista_sin_500(self):
        response = self.client.get(
            reverse("feedback:buscar"), {"numero": "no-es-un-numero"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("feedback:lista"))


class ComentarIssueGithubClientTestCase(TestCase):
    """Sub-item #5 — `GitHubFeedbackClient.comentar_issue` (extraído de
    `cerrar_issue`, ahora reusable sin cerrar el issue)."""

    def setUp(self):
        self.client_gh = GitHubFeedbackClient(token="tok", repo="Indunnova16/SD")

    @patch("apps.feedback.github_client.requests.post")
    def test_comenta_sin_cerrar(self, mock_post):
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 321})

        comment_id = self.client_gh.comentar_issue(72, "Sigue pasando")

        self.assertEqual(comment_id, 321)
        self.assertIn("/issues/72/comments", mock_post.call_args[0][0])
        self.assertEqual(
            mock_post.call_args[1]["json"], {"body": "Sigue pasando"}
        )

    @patch("apps.feedback.github_client.requests.post")
    def test_status_inesperado_levanta_error(self, mock_post):
        mock_post.return_value = Mock(status_code=403, text="Forbidden")

        with self.assertRaises(GitHubClientError):
            self.client_gh.comentar_issue(72, "Sigue pasando")

    @patch("apps.feedback.github_client.requests.post")
    def test_error_de_red_se_normaliza(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(GitHubClientError):
            self.client_gh.comentar_issue(72, "Sigue pasando")


class ComentarTicketServiceTestCase(TestCase):
    """Sub-item #5 — `services.comentar_ticket`."""

    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Descripción de prueba con longitud suficiente.",
            github_issue_number=72,
            sincronizado_github=True,
        )

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_happy_path_publica_comentario(self, mock_cls):
        ok = comentar_ticket(self.ticket.id, "Ana", "Sigue pasando")

        self.assertTrue(ok)
        mock_cls.return_value.comentar_issue.assert_called_once()
        args = mock_cls.return_value.comentar_issue.call_args[0]
        self.assertEqual(args[0], 72)
        self.assertIn("Ana", args[1])
        self.assertIn("Sigue pasando", args[1])

    def test_ticket_sin_issue_devuelve_false_sin_llamar_a_github(self):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="B",
            asunto="Sin sync",
            descripcion="x" * 20,
        )

        with patch("apps.feedback.services.GitHubFeedbackClient") as mock_cls:
            ok = comentar_ticket(ticket.id, "Ana", "Sigue pasando")

        self.assertFalse(ok)
        mock_cls.assert_not_called()

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_github_caido_devuelve_false_no_lanza(self, mock_cls):
        mock_cls.return_value.comentar_issue.side_effect = GitHubClientError("503")

        ok = comentar_ticket(self.ticket.id, "Ana", "Sigue pasando")

        self.assertFalse(ok)


class ComentarViewTestCase(TestCase):
    """Sub-item #5 — vista pública `comentar_view`, independiente de resolver."""

    def setUp(self):
        cache.clear()
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Descripción de prueba con longitud suficiente.",
            github_issue_number=72,
            sincronizado_github=True,
        )
        self.url = reverse("feedback:comentar", kwargs={"ticket_id": self.ticket.id})
        self.detalle_url = reverse(
            "feedback:detalle", kwargs={"ticket_id": self.ticket.id}
        )

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_post_valido_comenta_y_redirige_sin_resolver(self, mock_cls):
        response = self.client.post(
            self.url, data={"nombre": "Ana", "comentario": "Sigue pasando"}
        )

        self.assertRedirects(response, self.detalle_url)
        mock_cls.return_value.comentar_issue.assert_called_once()
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.esta_resuelto)

    def test_get_no_comenta(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_honeypot_poblado_no_comenta(self):
        with patch("apps.feedback.services.GitHubFeedbackClient") as mock_cls:
            response = self.client.post(
                self.url,
                data={
                    "nombre": "Bot",
                    "comentario": "spam",
                    "website": "http://spam.example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        mock_cls.return_value.comentar_issue.assert_not_called()

    def test_ticket_sin_sincronizar_no_comenta_y_avisa(self):
        ticket_sin_sync = FeedbackTicket.objects.create(
            nombre_reportante="B",
            asunto="Sin sync todavía",
            descripcion="x" * 20,
        )
        url = reverse("feedback:comentar", kwargs={"ticket_id": ticket_sin_sync.id})

        with patch("apps.feedback.services.GitHubFeedbackClient") as mock_cls:
            response = self.client.post(
                url, data={"nombre": "Ana", "comentario": "Sigue pasando"}, follow=True
            )

        mock_cls.assert_not_called()
        self.assertContains(response, "todavía se está sincronizando")

    def test_ticket_inexistente_404(self):
        url = reverse("feedback:comentar", kwargs={"ticket_id": 999999})
        response = self.client.post(
            url, data={"nombre": "Ana", "comentario": "Sigue pasando"}
        )
        self.assertEqual(response.status_code, 404)

    def test_comentario_visible_no_bloquea_si_ticket_ya_resuelto(self):
        """El comentario debe seguir disponible aunque el ticket esté
        resuelto (reclamo literal: independiente de resolver)."""
        self.ticket.estado = FeedbackTicket.ESTADO_RESUELTO
        self.ticket.save(update_fields=["estado"])

        response = self.client.get(self.detalle_url)

        self.assertContains(response, 'id="form-comentar"')
