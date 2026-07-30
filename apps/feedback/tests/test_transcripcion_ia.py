"""
Tests de la transcripción IA de adjuntos del portal de feedback.

Issue #71 ronda 3 (bounce=2, FIX_INCOMPLETO x2 — el reclamo del cliente fue
diferido sin preguntar en las 2 rondas previas). El reclamo literal
(2026-07-29): *"el sistema no lo integro con la IA para cuando llegue a GH
traiga la informacion del audio, video o imagenes o docs cargados como se
hace en Arcopack"*.

Cubre, de punta a punta:
  1. `gemini_client.transcribir_media` — selección de prompt por mime,
     manejo de API key ausente, y que NUNCA propaga excepciones (best-effort).
  2. `services.procesar_archivos_subidos` — invoca la transcripción tras
     cada adjunto válido y persiste `FeedbackAttachment.transcripcion_ia`;
     si Gemini falla, el adjunto (y el ticket) se crean igual, sin 500.
  3. `services.sincronizar_ticket` — propaga `transcripcion_ia` al dict de
     adjuntos que llega a `GitHubFeedbackClient.crear_issue`.
  4. `github_client.GitHubFeedbackClient._build_body` /
     `_bloque_transcripcion` — el texto llega al body del issue de GitHub
     bajo el encabezado `**Transcripción:**` (el mismo marcador que valida
     el journey `SD_71.yaml` contra el issue real).
"""

import base64
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.feedback import gemini_client
from apps.feedback.github_client import GitHubFeedbackClient
from apps.feedback.models import FeedbackAttachment, FeedbackTicket
from apps.feedback.services import procesar_archivos_subidos, sincronizar_ticket

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
WAV_FAKE = b"RIFF....WAVEfmt contenido de prueba de un audio"


def _mock_genai_response(texto):
    """Simula la respuesta de `client.models.generate_content(...)`."""
    response = Mock()
    response.text = texto
    return response


class TranscribirMediaTestCase(TestCase):
    """Unitarios de `gemini_client.transcribir_media` — sin BD, sin red real."""

    @override_settings(GEMINI_API_KEY="fake-key-123")
    @patch("apps.feedback.gemini_client._get_genai_client")
    def test_audio_selecciona_prompt_audio_y_devuelve_texto(self, mock_get_client):
        mock_client = Mock()
        mock_client.models.generate_content.return_value = _mock_genai_response(
            "Hola, este es un audio de prueba."
        )
        mock_get_client.return_value = mock_client

        texto = gemini_client.transcribir_media(WAV_FAKE, "audio/wav")

        self.assertEqual(texto, "Hola, este es un audio de prueba.")
        _args, kwargs = mock_client.models.generate_content.call_args
        # El segundo elemento de `contents` es el prompt de audio.
        self.assertIn("Transcribe literalmente este audio", kwargs["contents"][1])

    @override_settings(GEMINI_API_KEY="fake-key-123")
    @patch("apps.feedback.gemini_client._get_genai_client")
    def test_video_selecciona_prompt_video(self, mock_get_client):
        mock_client = Mock()
        mock_client.models.generate_content.return_value = _mock_genai_response(
            "**Resumen:** un video de prueba.\n**Transcripción:** hola."
        )
        mock_get_client.return_value = mock_client

        texto = gemini_client.transcribir_media(b"contenido video falso", "video/webm")

        self.assertIn("Transcripción", texto)
        _args, kwargs = mock_client.models.generate_content.call_args
        self.assertIn("Analiza este video", kwargs["contents"][1])

    @override_settings(GEMINI_API_KEY="fake-key-123")
    @patch("apps.feedback.gemini_client._get_genai_client")
    def test_imagen_selecciona_prompt_imagen(self, mock_get_client):
        mock_client = Mock()
        mock_client.models.generate_content.return_value = _mock_genai_response(
            "**Descripción:** una captura de pantalla del portal."
        )
        mock_get_client.return_value = mock_client

        texto = gemini_client.transcribir_media(PNG_1X1, "image/png")

        self.assertIn("Descripción", texto)
        _args, kwargs = mock_client.models.generate_content.call_args
        self.assertIn("portal de tickets de SD", kwargs["contents"][1])

    @override_settings(GEMINI_API_KEY="fake-key-123")
    @patch("apps.feedback.gemini_client._get_genai_client")
    def test_pdf_selecciona_prompt_pdf(self, mock_get_client):
        mock_client = Mock()
        mock_client.models.generate_content.return_value = _mock_genai_response(
            "Contenido extraído del PDF."
        )
        mock_get_client.return_value = mock_client

        texto = gemini_client.transcribir_media(b"%PDF-1.4 falso", "application/pdf")

        self.assertEqual(texto, "Contenido extraído del PDF.")
        _args, kwargs = mock_client.models.generate_content.call_args
        self.assertIn("Extrae el contenido textual completo", kwargs["contents"][1])

    def test_mime_no_soportado_devuelve_cadena_vacia_sin_llamar_a_gemini(self):
        """Edge case explícito del contrato F3: adjunto de tipo no soportado."""
        with patch("apps.feedback.gemini_client._get_genai_client") as mock_get_client:
            texto = gemini_client.transcribir_media(b"contenido cualquiera", "text/plain")

        self.assertEqual(texto, "")
        mock_get_client.assert_not_called()

    def test_datos_vacios_devuelve_cadena_vacia(self):
        texto = gemini_client.transcribir_media(b"", "audio/wav")
        self.assertEqual(texto, "")

    @override_settings(GEMINI_API_KEY="")
    def test_sin_api_key_devuelve_cadena_vacia_sin_excepcion(self):
        """`GEMINI_API_KEY` vacío (default seguro si el secret no está montado
        aún en el workflow de deploy) NUNCA debe levantar excepción."""
        texto = gemini_client.transcribir_media(WAV_FAKE, "audio/wav")
        self.assertEqual(texto, "")

    @override_settings(GEMINI_API_KEY="fake-key-123")
    @patch("apps.feedback.gemini_client._get_genai_client")
    def test_api_falla_o_da_timeout_devuelve_cadena_vacia_sin_excepcion(
        self, mock_get_client
    ):
        """Gemini caído/timeout -> nunca debe propagar, solo degradar a ''."""
        mock_client = Mock()
        mock_client.models.generate_content.side_effect = TimeoutError("timeout")
        mock_get_client.return_value = mock_client

        texto = gemini_client.transcribir_media(WAV_FAKE, "audio/wav")

        self.assertEqual(texto, "")

    @override_settings(GEMINI_TRANSCRIBE_MAX_BYTES=10)
    def test_excede_limite_de_bytes_devuelve_cadena_vacia(self):
        with patch("apps.feedback.gemini_client._get_genai_client") as mock_get_client:
            texto = gemini_client.transcribir_media(b"x" * 500, "audio/wav")

        self.assertEqual(texto, "")
        mock_get_client.assert_not_called()

    @override_settings(GEMINI_TRANSCRIBE_ENABLED=False)
    def test_transcripcion_deshabilitada_devuelve_cadena_vacia(self):
        with patch("apps.feedback.gemini_client._get_genai_client") as mock_get_client:
            texto = gemini_client.transcribir_media(WAV_FAKE, "audio/wav")

        self.assertEqual(texto, "")
        mock_get_client.assert_not_called()


class ProcesarArchivosSubidosTranscripcionTestCase(TestCase):
    """Integración: `procesar_archivos_subidos` invoca la transcripción y la
    persiste en `FeedbackAttachment.transcripcion_ia` — sin bloquear el
    ticket si Gemini falla."""

    def _ticket(self):
        return FeedbackTicket.objects.create(
            nombre_reportante="QA_E2E_SD71",
            asunto="Adjunto de audio debe traer transcripcion IA",
            descripcion="Ticket de prueba para validar el pipeline de transcripción.",
        )

    @patch("apps.feedback.services.gemini_client.transcribir_media")
    def test_happy_path_transcripcion_se_persiste_en_el_adjunto(self, mock_transcribir):
        mock_transcribir.return_value = "Transcripción real generada por Gemini."
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "audio.wav", WAV_FAKE, content_type="audio/wav"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(
            creados[0].transcripcion_ia, "Transcripción real generada por Gemini."
        )
        mock_transcribir.assert_called_once()
        _args, _kwargs = mock_transcribir.call_args
        # (data, mime) posicionales
        self.assertEqual(mock_transcribir.call_args[0][1], "audio/wav")

    @patch("apps.feedback.services.gemini_client.transcribir_media")
    def test_gemini_falla_ticket_y_adjunto_se_crean_igual_sin_transcripcion(
        self, mock_transcribir
    ):
        """Gemini revienta con una excepción no contemplada (defensa de 2da
        capa, issue #81 mismo patrón) -> el adjunto se crea igual, sin 500,
        con `transcripcion_ia=""`."""
        mock_transcribir.side_effect = Exception("Gemini explotó de forma inesperada")
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "audio.wav", WAV_FAKE, content_type="audio/wav"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])  # NO debe lanzar

        self.assertEqual(len(creados), 1)
        self.assertEqual(creados[0].transcripcion_ia, "")

    def test_sin_mock_gemini_client_real_degrada_a_vacio_sin_api_key(self):
        """Sin mock: `GEMINI_API_KEY` está vacío por default en settings de
        test -> el pipeline real (no mockeado) debe degradar a "" y el
        adjunto se crea igual."""
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "foto.png", PNG_1X1, content_type="image/png"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(creados[0].transcripcion_ia, "")

    @patch("apps.feedback.services.gemini_client.transcribir_media")
    def test_adjunto_descartado_por_mime_no_permitido_nunca_llama_a_gemini(
        self, mock_transcribir
    ):
        """Edge case: adjunto de tipo no soportado por el portal (ni imagen,
        ni audio, ni video) -> se descarta ANTES de intentar transcribir."""
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "script.sh", b"#!/bin/sh\nrm -rf /", content_type="application/x-sh"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])
        mock_transcribir.assert_not_called()


class SincronizarTicketTranscripcionTestCase(TestCase):
    """`sincronizar_ticket` debe propagar `transcripcion_ia` al dict de
    adjuntos que recibe `GitHubFeedbackClient.crear_issue`."""

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_transcripcion_llega_al_dict_de_adjuntos_de_crear_issue(
        self, mock_client_cls
    ):
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="QA_E2E_SD71",
            asunto="Adjunto de audio debe traer transcripcion IA",
            descripcion="Ticket E2E automatizado.",
        )
        FeedbackAttachment.objects.create(
            ticket=ticket,
            archivo=SimpleUploadedFile("audio.wav", WAV_FAKE, content_type="audio/wav"),
            tipo=FeedbackAttachment.TIPO_AUDIO,
            mime_type="audio/wav",
            nombre_original="audio.wav",
            transcripcion_ia="Transcripción persistida en BD.",
        )
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.return_value = {
            "number": 101,
            "html_url": "https://github.com/Indunnova16/SD/issues/101",
            "id": 555,
        }

        resultado = sincronizar_ticket(ticket.pk)

        self.assertTrue(resultado)
        _args, kwargs = mock_client.crear_issue.call_args
        adjuntos_pasados = kwargs["adjuntos"]
        self.assertEqual(len(adjuntos_pasados), 1)
        self.assertEqual(
            adjuntos_pasados[0]["transcripcion"], "Transcripción persistida en BD."
        )

    @patch("apps.feedback.services.GitHubFeedbackClient")
    def test_adjunto_sin_transcripcion_manda_cadena_vacia_no_rompe(
        self, mock_client_cls
    ):
        """Adjunto cuyo Gemini falló (`transcripcion_ia=""`) no debe romper
        la sincronización ni mandar `None`."""
        ticket = FeedbackTicket.objects.create(
            nombre_reportante="Carlos Ruiz",
            asunto="Sugerencia de mejora",
            descripcion="Sería útil poder filtrar los cursos por categoría.",
        )
        FeedbackAttachment.objects.create(
            ticket=ticket,
            archivo=SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png"),
            tipo=FeedbackAttachment.TIPO_IMAGEN,
            mime_type="image/png",
            nombre_original="foto.png",
        )
        mock_client = mock_client_cls.return_value
        mock_client.crear_issue.return_value = {
            "number": 102,
            "html_url": "https://github.com/Indunnova16/SD/issues/102",
            "id": 556,
        }

        resultado = sincronizar_ticket(ticket.pk)

        self.assertTrue(resultado)
        _args, kwargs = mock_client.crear_issue.call_args
        self.assertEqual(kwargs["adjuntos"][0]["transcripcion"], "")


class BloqueTranscripcionGithubBodyTestCase(TestCase):
    """`GitHubFeedbackClient._bloque_transcripcion` / `_build_body` — el
    marcador que el journey `SD_71.yaml` valida contra el issue real."""

    def _client(self):
        return GitHubFeedbackClient(token="ghp_test-token", repo="Indunnova16/SD")

    def test_bloque_transcripcion_formatea_como_blockquote(self):
        bloque = GitHubFeedbackClient._bloque_transcripcion(
            "Primera línea.\nSegunda línea."
        )

        self.assertTrue(bloque.startswith("**Transcripción:**\n"))
        self.assertIn("> Primera línea.", bloque)
        self.assertIn("> Segunda línea.", bloque)

    def test_bloque_transcripcion_vacio_devuelve_cadena_vacia(self):
        self.assertEqual(GitHubFeedbackClient._bloque_transcripcion(""), "")
        self.assertEqual(GitHubFeedbackClient._bloque_transcripcion("   "), "")
        self.assertEqual(GitHubFeedbackClient._bloque_transcripcion(None), "")

    def test_build_body_incluye_transcripcion_del_adjunto_de_audio(self):
        client = self._client()

        body = client._build_body(
            descripcion="Adjunta un audio corto.",
            nombre_reportante="QA_E2E_SD71",
            adjuntos=[
                {
                    "nombre": "audio.wav",
                    "url": "https://example.com/audio.wav",
                    "tipo": "audio",
                    "transcripcion": "Hola, este es un audio de prueba.",
                }
            ],
        )

        self.assertIn("**Transcripción:**", body)
        self.assertIn("> Hola, este es un audio de prueba.", body)

    def test_build_body_sin_transcripcion_no_agrega_el_bloque(self):
        """Adjunto sin transcripción (Gemini falló o no corrió) -> el body
        no debe traer un encabezado 'Transcripción:' vacío."""
        client = self._client()

        body = client._build_body(
            descripcion="Una captura de pantalla.",
            nombre_reportante="Ana Pérez",
            adjuntos=[
                {
                    "nombre": "captura.png",
                    "url": "https://example.com/captura.png",
                    "tipo": "imagen",
                }
            ],
        )

        self.assertNotIn("Transcripción", body)

    def test_build_body_retrocompatible_con_adjuntos_sin_dict(self):
        """Regresión: la firma vieja (`adjunto` como string plano, no dict)
        seguía soportada antes de este fix — no debe romperse."""
        client = self._client()

        body = client._build_body(
            descripcion="Texto.",
            nombre_reportante="Ana Pérez",
            adjuntos=["https://example.com/legacy.png"],
        )

        self.assertIn("https://example.com/legacy.png", body)
        self.assertNotIn("Transcripción", body)

    @patch("apps.feedback.github_client.requests.post")
    def test_crear_issue_end_to_end_incluye_transcripcion_en_el_payload(
        self, mock_post
    ):
        """El mismo reclamo que valida el journey SD_71.yaml pero a nivel
        unitario: `crear_issue` (lo que golpea la API real de GitHub) debe
        mandar el bloque de transcripción en el body."""
        response = Mock()
        response.status_code = 201
        response.json.return_value = {
            "number": 71,
            "html_url": "https://github.com/Indunnova16/SD/issues/71",
            "id": 71071,
        }
        mock_post.return_value = response
        client = self._client()

        client.crear_issue(
            ticket_id=71,
            asunto="QA_E2E_SD71 - adjunto de audio debe traer transcripcion IA",
            descripcion="Ticket E2E automatizado.",
            nombre_reportante="QA_E2E_SD71",
            adjuntos=[
                {
                    "nombre": "audio.wav",
                    "url": "https://example.com/audio.wav",
                    "tipo": "audio",
                    "transcripcion": "[inaudible]",
                }
            ],
        )

        _args, kwargs = mock_post.call_args
        self.assertIn("**Transcripción:**", kwargs["json"]["body"])
        self.assertIn("> [inaudible]", kwargs["json"]["body"])
