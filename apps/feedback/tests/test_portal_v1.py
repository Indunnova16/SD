"""
Tests del sub-item A1 (app skeleton + modelos) del portal de feedback.

Cubre: __str__ de FeedbackTicket, que la migración 0001_initial aplica
limpio sobre la BD de test (implícito en que este módulo colecta y corre
sin errores de BD), y los valores por defecto de los campos de
sincronización con GitHub. Tests de A2-A8 (github_client, forms, services,
views) se agregan a este mismo archivo en sub-items posteriores.
"""

import base64
from unittest.mock import Mock, patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.feedback.github_client import (
    LABEL_PORTAL_WEB,
    LABEL_PORTAL_WEB_COLOR,
    GitHubClientError,
    GitHubFeedbackClient,
)
from apps.feedback.forms import NuevoTicketForm
from apps.feedback.models import FeedbackAttachment, FeedbackTicket
from apps.feedback.services import (
    encolar_sincronizacion_ticket,
    procesar_archivos_subidos,
    sincronizar_ticket,
)


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


class NuevoTicketFormTestCase(TestCase):
    """Tests del sub-item A3 (NuevoTicketForm con honeypot anti-spam)."""

    def _datos_validos(self, **overrides):
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "El botón de descarga no funciona",
            "descripcion": "Al hacer click en descargar el certificado no pasa nada.",
            "website": "",
        }
        datos.update(overrides)
        return datos

    def test_form_valido_con_los_4_campos_reales_y_honeypot_vacio(self):
        form = NuevoTicketForm(data=self._datos_validos())
        self.assertTrue(form.is_valid())

    def test_honeypot_poblado_invalida_el_form_con_mensaje_generico(self):
        form = NuevoTicketForm(
            data=self._datos_validos(website="http://spam-bot.example.com")
        )
        self.assertFalse(form.is_valid())
        errores = " ".join(form.errors.get("website", []))
        self.assertTrue(errores)
        errores_lower = errores.lower()
        for palabra_delatora in ("bot", "honeypot", "spam"):
            self.assertNotIn(palabra_delatora, errores_lower)

    def test_nombre_reportante_de_un_caracter_es_invalido(self):
        form = NuevoTicketForm(data=self._datos_validos(nombre_reportante="A"))
        self.assertFalse(form.is_valid())
        self.assertIn("nombre_reportante", form.errors)

    def test_descripcion_muy_corta_es_invalida(self):
        form = NuevoTicketForm(data=self._datos_validos(descripcion="muy corta"))
        self.assertFalse(form.is_valid())
        self.assertIn("descripcion", form.errors)

    def test_falta_asunto_es_invalido(self):
        datos = self._datos_validos()
        del datos["asunto"]
        form = NuevoTicketForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("asunto", form.errors)


# PNG real de 1x1 pixel (transparente) — usado para probar el camino feliz
# de procesar_archivos_subidos sin depender de un archivo externo.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# PNG de 4x4 con IHDR válido pero CRC corrupto en el chunk IDAT (issue
# #81, mismo fixture que usa el journey E2E de SD_81 —
# ~/.claude/skills/qa-prod/fixtures/SD/crc_corrupto_idat_sd81.png).
# `Image.open()` lo "abre" sin problema (el header es válido); revienta
# recién en `.verify()` con `SyntaxError: broken PNG file (bad header
# checksum in b'IDAT')` — NO es subclase de OSError/ValueError/
# UnidentifiedImageError, por eso escapaba el except viejo de
# `services.py` y producía un 500. Verificado contra Pillow 10.4.0.
PNG_CRC_IDAT_CORRUPTO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEElEQVR4nGP8"
    "z4AATAxEcQAz0QEHxYQ+uAAAAABJRU5ErkJggg=="
)

# PNG de 68 bytes con un IHDR que declara 20000x20000 píxeles (400M) pero
# datos de IDAT triviales/no reales — no hace falta un archivo pesado de
# verdad: `Image.open()` calcula el tamaño total desde el header y lanza
# `Image.DecompressionBombError` ANTES de decodificar un solo píxel (issue
# #81). Su MRO es [DecompressionBombError, Exception] — tampoco hereda de
# OSError/ValueError, mismo hueco que el CRC corrupto. Verificado contra
# Pillow 10.4.0 (MAX_IMAGE_PIXELS=89478485, límite real de error=2x eso).
PNG_DECOMPRESSION_BOMB = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAATiAAAE4gCAIAAABsEtFuAAAAC0lEQVR4nGNg"
    "wAsAAB8AAYD9Q9oAAAAASUVORK5CYII="
)


class ProcesarArchivosSubidosTestCase(TestCase):
    """Tests del sub-item A4 — validación explícita de imágenes subidas.

    Cubre el hallazgo de F2: `FeedbackAttachment.objects.create(archivo=...)`
    fuera de un `ModelForm` no ejecuta `full_clean()`, por lo que
    `procesar_archivos_subidos` debe validar content_type + tamaño +
    contenido real (Pillow) de forma explícita, best-effort por archivo.

    Los casos de audio/video que agregó la ronda 2 de #71 viven en
    `test_adjuntos_media.py`.
    """

    def _ticket(self):
        return FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="El botón de descarga no funciona",
            descripcion="Al hacer click en descargar el certificado no pasa nada.",
        )

    def test_archivo_imagen_valida_crea_un_attachment(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png")

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 1
        )
        self.assertEqual(creados[0].nombre_original, "foto.png")

    def test_archivo_content_type_no_imagen_no_crea_attachment_ni_lanza(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "documento.pdf",
            b"%PDF-1.4 contenido de prueba, no es una imagen",
            content_type="application/pdf",
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

    def test_archivo_content_type_spoofeado_bytes_corruptos_no_crea_attachment(
        self,
    ):
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "malicioso.png",
            b"esto no es una imagen real, son bytes de texto disfrazados de png",
            content_type="image/png",
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

    def test_archivo_png_crc_idat_corrupto_no_crea_attachment_ni_lanza(self):
        """Issue #81 — regresión real, NO simulada con bytes de texto.

        A diferencia de `test_archivo_content_type_spoofeado_bytes_
        corruptos_no_crea_attachment` (que cae en `UnidentifiedImageError`,
        ya cubierto desde v1.0), este PNG tiene un IHDR perfectamente
        válido y solo el chunk IDAT corrupto — `Image.open()` lo abre sin
        problema y revienta con `SyntaxError` recién en `.verify()`. Antes
        del fix esta excepción escapaba el `except` y producía un 500 real
        en prod (traza 2026-07-29T12:02:25Z, ver F1/F2).
        """
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "crc_corrupto.png", PNG_CRC_IDAT_CORRUPTO, content_type="image/png"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

    def test_archivo_png_decompression_bomb_no_crea_attachment_ni_lanza(self):
        """Issue #81 — segundo vector confirmado por F2.

        `Image.DecompressionBombError` tampoco hereda de OSError/
        ValueError (MRO: [DecompressionBombError, Exception]) y se lanza
        desde el propio `Image.open()` cuando el header declara más
        píxeles que `Image.MAX_IMAGE_PIXELS` — mismo hueco estructural que
        el CRC corrupto, con la clase de excepción distinta. El fixture no
        necesita una imagen pesada de verdad: el header alcanza para
        disparar el chequeo antes de decodificar un solo píxel.
        """
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "bomba.png", PNG_DECOMPRESSION_BOMB, content_type="image/png"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

    @override_settings(FEEDBACK_MAX_ATTACHMENT_BYTES=10)
    def test_archivo_excede_tamano_maximo_no_crea_attachment(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png")

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

    @override_settings(FEEDBACK_MAX_ATTACHMENTS=2)
    def test_mas_de_max_attachments_solo_procesa_los_primeros_n(self):
        ticket = self._ticket()
        archivos = [
            SimpleUploadedFile(f"foto{i}.png", PNG_1X1, content_type="image/png")
            for i in range(4)
        ]

        creados = procesar_archivos_subidos(ticket, archivos)

        self.assertEqual(len(creados), 2)
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 2
        )


class SincronizarTicketTestCase(TestCase):
    """Tests del sub-item A4 — sincronizar_ticket (idempotencia + resiliencia)."""

    def _ticket(self, **overrides):
        datos = dict(
            nombre_reportante="Carlos Ruiz",
            asunto="Sugerencia de mejora",
            descripcion="Sería útil poder filtrar los cursos por categoría.",
        )
        datos.update(overrides)
        return FeedbackTicket.objects.create(**datos)

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_happy_path_deja_ticket_sincronizado(self, mock_client_cls):
        ticket = self._ticket()
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.return_value = {
            "number": 55,
            "html_url": "https://github.com/Indunnova16/SD/issues/55",
            "id": 123,
        }

        resultado = sincronizar_ticket(ticket.pk)

        self.assertTrue(resultado)
        mock_client.asegurar_label_portal_web.assert_called_once()
        mock_client.crear_issue.assert_called_once()
        ticket.refresh_from_db()
        self.assertTrue(ticket.sincronizado_github)
        self.assertEqual(ticket.github_issue_number, 55)
        self.assertEqual(
            ticket.github_url, "https://github.com/Indunnova16/SD/issues/55"
        )
        self.assertEqual(ticket.error_sincronizacion, "")

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_idempotente_no_llama_de_nuevo_si_ya_tiene_issue(self, mock_client_cls):
        ticket = self._ticket(
            github_issue_number=99,
            github_url="https://github.com/Indunnova16/SD/issues/99",
            sincronizado_github=True,
        )

        resultado = sincronizar_ticket(ticket.pk)

        self.assertTrue(resultado)
        mock_client_cls.assert_not_called()

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_error_github_no_propaga_deja_ticket_con_error(self, mock_client_cls):
        ticket = self._ticket()
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.side_effect = GitHubClientError("GitHub caído")

        resultado = sincronizar_ticket(ticket.pk)  # NO debe lanzar

        self.assertFalse(resultado)
        ticket.refresh_from_db()
        self.assertFalse(ticket.sincronizado_github)
        self.assertIn("GitHub caído", ticket.error_sincronizacion)
        self.assertIsNone(ticket.github_issue_number)


class EncolarSincronizacionTicketTestCase(TestCase):
    """Tests del sub-item A4 — encolar_sincronizacion_ticket vía on_commit."""

    @patch("apps.feedback.services.sincronizar_ticket")
    def test_dispara_sincronizar_ticket_solo_tras_commit(self, mock_sincronizar):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            ticket = FeedbackTicket.objects.create(
                nombre_reportante="Diana",
                asunto="Prueba de encolado",
                descripcion="Verifica que la sincronización se dispare on_commit.",
            )
            encolar_sincronizacion_ticket(ticket.pk)

        self.assertEqual(len(callbacks), 1)
        mock_sincronizar.assert_called_once_with(ticket.pk)


class ViewsTestCase(TestCase):
    """Tests del sub-item A5 — vistas públicas (lista/nuevo/detalle) + urls.

    El portal es público/anónimo: todas las requests usan `self.client`
    normal, sin login. No se testea de nuevo el flujo completo de
    `sincronizar_ticket`/`procesar_archivos_subidos` (ya cubierto por A4) —
    solo que `nuevo_view` los orquesta correctamente.
    """

    def _datos_validos(self, **overrides):
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "El botón de descarga no funciona",
            "descripcion": "Al hacer click en descargar el certificado no pasa nada.",
            "website": "",
        }
        datos.update(overrides)
        return datos

    def _ticket(self, **overrides):
        datos = dict(
            nombre_reportante="Carlos Ruiz",
            asunto="Sugerencia de mejora",
            descripcion="Sería útil poder filtrar los cursos por categoría.",
        )
        datos.update(overrides)
        return FeedbackTicket.objects.create(**datos)

    # -- lista_view --------------------------------------------------

    def test_lista_view_200_sin_tickets(self):
        response = self.client.get(reverse("feedback:lista"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 0)

    def test_lista_view_200_con_tickets(self):
        self._ticket(asunto="Primer ticket")
        self._ticket(asunto="Segundo ticket")

        response = self.client.get(reverse("feedback:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 2)

    # -- nuevo_view (GET) ---------------------------------------------

    def test_nuevo_view_get_200_form_en_contexto(self):
        response = self.client.get(reverse("feedback:nuevo"))

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], NuevoTicketForm)

    # -- nuevo_view (POST) ---------------------------------------------

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_nuevo_view_post_happy_path_crea_ticket_y_redirige_a_detalle(
        self, mock_client_cls
    ):
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.return_value = {
            "number": 10,
            "html_url": "https://github.com/Indunnova16/SD/issues/10",
            "id": 1,
        }
        datos = self._datos_validos()

        response = self.client.post(reverse("feedback:nuevo"), data=datos)

        ticket = FeedbackTicket.objects.filter(asunto=datos["asunto"]).first()
        self.assertIsNotNone(ticket)
        self.assertTrue(
            FeedbackTicket.objects.filter(
                asunto=datos["asunto"],
                nombre_reportante=datos["nombre_reportante"],
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("feedback:detalle", kwargs={"ticket_id": ticket.id})
        )

    def test_nuevo_view_post_honeypot_poblado_no_crea_ticket_y_rerenderiza(self):
        response = self.client.post(
            reverse("feedback:nuevo"),
            data=self._datos_validos(website="http://spam-bot.example.com"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FeedbackTicket.objects.exists())
        self.assertFalse(response.context["form"].is_valid())

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_nuevo_view_post_con_imagen_valida_crea_ticket_y_attachment(
        self, mock_client_cls
    ):
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.return_value = {
            "number": 11,
            "html_url": "https://github.com/Indunnova16/SD/issues/11",
            "id": 2,
        }
        archivo = SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png")
        datos = self._datos_validos()

        response = self.client.post(
            reverse("feedback:nuevo"), data={**datos, "imagenes": [archivo]}
        )

        self.assertEqual(response.status_code, 302)
        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 1
        )

    @patch("apps.feedback.views.encolar_sincronizacion_ticket")
    def test_nuevo_view_dispara_encolar_sincronizacion_ticket(self, mock_encolar):
        datos = self._datos_validos()

        self.client.post(reverse("feedback:nuevo"), data=datos)

        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])
        mock_encolar.assert_called_once_with(ticket.id)

    @patch("apps.feedback.views.procesar_archivos_subidos")
    def test_atomic_revierte_el_ticket_si_procesar_archivos_lanza_excepcion_no_contemplada(
        self, mock_procesar
    ):
        """Red de seguridad del cambio 2 (issue #81), independiente del
        cambio 1: aunque escape una excepción que `services.py` NO
        contempla (simulando una futura variante de PIL no cubierta por
        el except explícito), `transaction.atomic()` alrededor de
        `nuevo_view` revierte el `FeedbackTicket.objects.create()` — el
        ticket NUNCA queda huérfano en BD. La request en sí sigue
        propagando el error (eso lo resuelve el except ampliado de
        `procesar_archivos_subidos`, no la atomicidad), pero ya no hay
        efecto secundario de "ticket fantasma sin sincronizar".
        """
        mock_procesar.side_effect = RuntimeError("excepción no contemplada")
        datos = self._datos_validos()

        with self.assertRaises(RuntimeError):
            self.client.post(reverse("feedback:nuevo"), data=datos)

        self.assertFalse(
            FeedbackTicket.objects.filter(asunto=datos["asunto"]).exists()
        )

    # -- detalle_view --------------------------------------------------

    def test_detalle_view_200_ticket_existente(self):
        ticket = self._ticket()

        response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["ticket"], ticket)

    def test_detalle_view_404_ticket_inexistente(self):
        response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": 999999})
        )

        self.assertEqual(response.status_code, 404)


@override_settings(
    GITHUB_FEEDBACK_TOKEN="ghp_test-token-a8", GITHUB_FEEDBACK_REPO="Indunnova16/SD"
)
class IntegracionEndToEndTestCase(TestCase):
    """Tests del sub-item A8 — integración end-to-end de la cadena real.

    A diferencia de las clases anteriores (GithubClientTestCase,
    ProcesarArchivosSubidosTestCase/SincronizarTicketTestCase, ViewsTestCase),
    que testean cada capa aislada mockeando la clase/función de la capa
    vecina, estos tests ejercitan la cadena COMPLETA real:

        request HTTP POST -> nuevo_view -> NuevoTicketForm ->
        FeedbackTicket/FeedbackAttachment -> procesar_archivos_subidos ->
        encolar_sincronizacion_ticket (transaction.on_commit) ->
        sincronizar_ticket -> GitHubFeedbackClient -> github_client.py ->
        requests.post

    El ÚNICO mock es `apps.feedback.github_client.requests.post` — el punto
    más bajo posible (la llamada HTTP saliente real). Nada intermedio se
    mockea: si algún nombre de campo/parámetro no coincidiera entre capas
    (el tipo de bug que un test unitario aislado no caza), estos tests
    fallarían.

    Necesita `@override_settings(GITHUB_FEEDBACK_TOKEN=...)` porque
    `GITHUB_FEEDBACK_TOKEN` no tiene default en settings de test (default=""
    en base.py) y `sincronizar_ticket` instancia `GitHubFeedbackClient()`
    SIN pasar token/repo explícitos — usa `settings.GITHUB_FEEDBACK_TOKEN`
    directo. Sin este override el constructor real levanta
    `GitHubClientError` ANTES de siquiera llamar a `requests.post`, y el
    mock nunca se invoca (se descubrió escribiendo este test).
    """

    def _datos_validos(self, **overrides):
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "El botón de descarga no funciona",
            "descripcion": "Al hacer click en descargar el certificado no pasa nada.",
            "website": "",
        }
        datos.update(overrides)
        return datos

    def _mock_response(self, status_code, json_data=None, text=""):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        return response

    def _issues_call(self, mock_post):
        """Devuelve el `call()` de `mock_post` dirigido al endpoint
        `/issues` (descarta la llamada previa a `/labels` que hace
        `asegurar_label_portal_web`, para no confundir los payloads)."""
        llamadas = [
            llamada
            for llamada in mock_post.call_args_list
            if llamada.args and llamada.args[0].endswith("/issues")
        ]
        self.assertEqual(
            len(llamadas), 1, "se esperaba exactamente 1 POST al endpoint /issues"
        )
        return llamadas[0]

    @patch("apps.feedback.github_client.requests.post")
    def test_happy_path_completo_http_hasta_github(self, mock_post):
        """POST real -> view -> form -> modelo -> services -> github_client
        -> requests.post (único mock). Verifica ticket+adjunto en BD,
        sincronización marcada True con el número de issue del mock, y que
        el payload real enviado a GitHub trae intactos los datos del form.
        """
        mock_post.return_value = self._mock_response(
            201,
            json_data={
                "number": 77,
                "html_url": "https://github.com/Indunnova16/SD/issues/77",
                "id": 555,
            },
        )
        archivo = SimpleUploadedFile(
            "captura.png", PNG_1X1, content_type="image/png"
        )
        datos = self._datos_validos()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("feedback:nuevo"), data={**datos, "imagenes": [archivo]}
            )

        # (a) el FeedbackTicket existe en BD con los datos correctos
        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])
        self.assertEqual(ticket.nombre_reportante, datos["nombre_reportante"])
        self.assertEqual(ticket.descripcion, datos["descripcion"])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id}),
        )

        # (b) el FeedbackAttachment fue creado y asociado al ticket
        adjuntos = FeedbackAttachment.objects.filter(ticket=ticket)
        self.assertEqual(adjuntos.count(), 1)
        self.assertEqual(adjuntos.first().nombre_original, "captura.png")

        # (c) sincronizado_github == True, github_issue_number poblado con
        # el valor exacto que devolvió el mock de GitHub
        ticket.refresh_from_db()
        self.assertTrue(ticket.sincronizado_github)
        self.assertEqual(ticket.github_issue_number, 77)
        self.assertEqual(
            ticket.github_url, "https://github.com/Indunnova16/SD/issues/77"
        )
        self.assertEqual(ticket.error_sincronizacion, "")

        # (d) el payload real que llegó a requests.post trae intacto lo que
        # el usuario mandó por el form — la prueba de que TODA la cadena de
        # datos (form -> modelo -> services -> github_client) llegó bien.
        issues_call = self._issues_call(mock_post)
        payload = issues_call.kwargs["json"]
        self.assertEqual(payload["title"], f"[Portal] {datos['asunto']}")
        self.assertIn(datos["descripcion"], payload["body"])
        self.assertIn(datos["nombre_reportante"], payload["body"])
        self.assertIn("captura.png", payload["body"])
        self.assertEqual(payload["labels"], ["portal-web"])
        self.assertEqual(payload["assignees"], ["Indunnova"])

    @patch("apps.feedback.github_client.requests.post")
    def test_resiliencia_end_to_end_github_caido_no_pierde_el_ticket(
        self, mock_post
    ):
        """Si GitHub falla (red caída), el ticket del usuario NO se pierde:
        queda en BD con sincronizado_github=False + error_sincronizacion
        poblado, y la vista sigue respondiendo 302 al usuario (nunca 500),
        mostrando el ticket igual aunque la sync a GitHub haya fallado."""
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "no se pudo conectar a api.github.com"
        )
        datos = self._datos_validos()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("feedback:nuevo"), data=datos)

        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id}),
        )

        self.assertFalse(ticket.sincronizado_github)
        self.assertIsNone(ticket.github_issue_number)
        self.assertTrue(ticket.error_sincronizacion)

        # el detalle del ticket sigue siendo accesible (200) pese a que la
        # sincronización con GitHub falló — nunca un 500 al usuario.
        detalle_response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id})
        )
        self.assertEqual(detalle_response.status_code, 200)
        self.assertContains(detalle_response, datos["asunto"])

    @patch("apps.feedback.github_client.requests.post")
    def test_imagen_png_crc_idat_corrupta_no_produce_500_ni_ticket_huerfano(
        self, mock_post
    ):
        """Issue #81 — reproduce el escenario EXACTO del journey E2E
        (SD_81, i81_portal_feedback_imagen_crc_corrupto_no_500_no_huerfano)
        contra la cadena completa real: POST público -> nuevo_view ->
        procesar_archivos_subidos (PIL real) -> transaction.atomic ->
        encolar_sincronizacion_ticket -> sincronizar_ticket ->
        GitHubFeedbackClient -> requests.post (único mock).

        Antes del fix esto era un Server Error (500) y, si el ticket ya
        alcanzaba a insertarse antes de que PIL reventara, quedaba
        huérfano (sin sincronizar) porque `nuevo_view` no era atómica.
        Después del fix: (a) NO 500 — 302 a la página de detalle; (b) el
        archivo corrupto NO se guarda como adjunto; (c) el ticket SÍ queda
        sincronizado con GitHub (no huérfano).
        """
        mock_post.return_value = self._mock_response(
            201,
            json_data={
                "number": 81,
                "html_url": "https://github.com/Indunnova16/SD/issues/81",
                "id": 8181,
            },
        )
        archivo = SimpleUploadedFile(
            "crc_corrupto.png", PNG_CRC_IDAT_CORRUPTO, content_type="image/png"
        )
        datos = self._datos_validos(
            asunto="QA_E2E_SD81 - imagen PNG con CRC corrupto en IDAT"
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("feedback:nuevo"), data={**datos, "imagenes": [archivo]}
            )

        # (a) nunca un 500 -- redirige al detalle del ticket recién creado
        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id}),
        )

        # (b) el archivo corrupto se descartó -- no quedó como adjunto
        self.assertEqual(
            FeedbackAttachment.objects.filter(ticket=ticket).count(), 0
        )

        # (c) el ticket NO quedó huérfano -- se sincronizó con GitHub
        ticket.refresh_from_db()
        self.assertTrue(ticket.sincronizado_github)
        self.assertEqual(ticket.github_issue_number, 81)
        self.assertEqual(ticket.error_sincronizacion, "")

        # el detalle es 200 y no muestra el banner de "sincronización
        # pendiente" (observable visible, mismo criterio que el journey).
        detalle_response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id})
        )
        self.assertEqual(detalle_response.status_code, 200)
        self.assertNotContains(
            detalle_response, "estamos procesando la sincronización"
        )

    @patch("apps.feedback.github_client.requests.post")
    def test_flujo_completo_navegacion_lista_y_detalle_con_imagen(
        self, mock_post
    ):
        """Crea un ticket con imagen (mock exitoso) y confirma que aparece
        en `feedback:lista` y que su `feedback:detalle` muestra el asunto Y
        la imagen adjunta en el HTML de respuesta."""
        mock_post.return_value = self._mock_response(
            201,
            json_data={
                "number": 88,
                "html_url": "https://github.com/Indunnova16/SD/issues/88",
                "id": 666,
            },
        )
        archivo = SimpleUploadedFile(
            "evidencia.png", PNG_1X1, content_type="image/png"
        )
        datos = self._datos_validos(
            asunto="El certificado no descarga en Safari"
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("feedback:nuevo"), data={**datos, "imagenes": [archivo]}
            )

        ticket = FeedbackTicket.objects.get(asunto=datos["asunto"])

        lista_response = self.client.get(reverse("feedback:lista"))
        self.assertEqual(lista_response.status_code, 200)
        self.assertContains(lista_response, datos["asunto"])

        detalle_response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": ticket.id})
        )
        self.assertEqual(detalle_response.status_code, 200)
        self.assertContains(detalle_response, datos["asunto"])

        adjunto = FeedbackAttachment.objects.get(ticket=ticket)
        self.assertContains(detalle_response, adjunto.archivo.url)
