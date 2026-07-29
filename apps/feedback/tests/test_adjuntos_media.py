"""
Tests de adjuntos de audio y video en el portal público (issue #71 ronda 2).

Reclamo literal del cliente: *"falta la opcion de grabar video y audio"*.
La v1.0 solo aceptaba `image/*` (`services.procesar_archivos_subidos`
exigía `content_type.startswith("image/")` y el modelo usaba un
`ImageField`), así que un audio o un video grabado desde el navegador se
descartaba en silencio.
"""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.feedback.models import FeedbackAttachment, FeedbackTicket
from apps.feedback.services import normalizar_mime, procesar_archivos_subidos

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
# No hace falta un webm real: audio/video no pasan por PIL (ver
# `procesar_archivos_subidos`), el gate es prefijo MIME + tamaño.
WEBM_FAKE = b"\x1a\x45\xdf\xa3 contenido de prueba de un webm"


class NormalizarMimeTestCase(TestCase):
    """`MediaRecorder` manda el codec dentro del content-type."""

    def test_recorta_parametro_codecs(self):
        self.assertEqual(normalizar_mime("audio/webm;codecs=opus"), "audio/webm")
        self.assertEqual(normalizar_mime("video/webm;codecs=vp9,opus"), "video/webm")

    def test_normaliza_mayusculas_y_espacios(self):
        self.assertEqual(normalizar_mime("  IMAGE/PNG  "), "image/png")

    def test_vacio_o_none_devuelve_cadena_vacia(self):
        self.assertEqual(normalizar_mime(""), "")
        self.assertEqual(normalizar_mime(None), "")


class InferirTipoTestCase(TestCase):
    def test_infiere_audio_video_e_imagen(self):
        self.assertEqual(
            FeedbackAttachment.inferir_tipo("audio/webm"),
            FeedbackAttachment.TIPO_AUDIO,
        )
        self.assertEqual(
            FeedbackAttachment.inferir_tipo("video/mp4"),
            FeedbackAttachment.TIPO_VIDEO,
        )
        self.assertEqual(
            FeedbackAttachment.inferir_tipo("image/png"),
            FeedbackAttachment.TIPO_IMAGEN,
        )


class ProcesarMediaTestCase(TestCase):
    def _ticket(self):
        return FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="No se escucha el audio del curso",
            descripcion="El módulo 3 no reproduce el audio en ningún navegador.",
        )

    def test_audio_grabado_por_mediarecorder_crea_attachment_tipo_audio(self):
        """El caso real: content-type con `;codecs=opus`, como lo manda el navegador."""
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "audio-2026-07-28.webm", WEBM_FAKE, content_type="audio/webm;codecs=opus"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(creados[0].tipo, FeedbackAttachment.TIPO_AUDIO)
        # El parámetro `codecs` no debe quedar guardado: se usa como
        # `<source type="...">` en el detalle.
        self.assertEqual(creados[0].mime_type, "audio/webm")

    def test_video_grabado_crea_attachment_tipo_video(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "video-2026-07-28.webm",
            WEBM_FAKE,
            content_type="video/webm;codecs=vp9,opus",
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(creados[0].tipo, FeedbackAttachment.TIPO_VIDEO)
        self.assertEqual(creados[0].mime_type, "video/webm")

    def test_video_mp4_de_ios_safari_se_acepta(self):
        """iOS/Safari no soporta webm: MediaRecorder cae a `video/mp4`."""
        ticket = self._ticket()
        archivo = SimpleUploadedFile("video.mp4", WEBM_FAKE, content_type="video/mp4")

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)
        self.assertEqual(creados[0].tipo, FeedbackAttachment.TIPO_VIDEO)

    def test_audio_video_no_pasan_por_pillow(self):
        """Un webm no es una imagen; si se validara con PIL se descartaría.

        Es la regresión concreta que rompería el feature pedido.
        """
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "grabacion.webm", b"no es una imagen ni de lejos", content_type="audio/webm"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(len(creados), 1)

    def test_imagen_sigue_validandose_con_pillow(self):
        """La ronda 2 NO debe aflojar la validación de imágenes de v1.0."""
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "falsa.png", b"bytes de texto disfrazados de png", content_type="image/png"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])

    def test_tipo_mime_no_permitido_se_sigue_descartando(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile(
            "script.sh", b"#!/bin/sh\nrm -rf /", content_type="application/x-sh"
        )

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])

    @override_settings(FEEDBACK_MAX_ATTACHMENT_BYTES=10)
    def test_video_que_excede_el_limite_se_descarta(self):
        ticket = self._ticket()
        archivo = SimpleUploadedFile("pesado.webm", b"x" * 500, content_type="video/webm")

        creados = procesar_archivos_subidos(ticket, [archivo])

        self.assertEqual(creados, [])

    def test_mezcla_imagen_audio_video_en_un_solo_ticket(self):
        ticket = self._ticket()
        archivos = [
            SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png"),
            SimpleUploadedFile("a.webm", WEBM_FAKE, content_type="audio/webm"),
            SimpleUploadedFile("v.webm", WEBM_FAKE, content_type="video/webm"),
        ]

        creados = procesar_archivos_subidos(ticket, archivos)

        self.assertEqual(len(creados), 3)
        self.assertEqual(sorted(a.tipo for a in creados), ["audio", "imagen", "video"])


class DetalleRenderizaMediaTestCase(TestCase):
    """El detalle debe reproducir el media, no linkearlo como imagen rota."""

    def setUp(self):
        self.ticket = FeedbackTicket.objects.create(
            nombre_reportante="Ana Pérez",
            asunto="No se escucha el audio",
            descripcion="El módulo 3 no reproduce el audio en ningún navegador.",
        )

    def test_audio_se_renderiza_con_tag_audio(self):
        procesar_archivos_subidos(
            self.ticket,
            [SimpleUploadedFile("a.webm", WEBM_FAKE, content_type="audio/webm")],
        )

        response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("<audio", html)
        self.assertIn('type="audio/webm"', html)

    def test_video_se_renderiza_con_tag_video(self):
        procesar_archivos_subidos(
            self.ticket,
            [SimpleUploadedFile("v.webm", WEBM_FAKE, content_type="video/webm")],
        )

        response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})
        )

        html = response.content.decode()
        self.assertIn("<video", html)
        self.assertIn('data-tipo="video"', html)

    def test_imagen_se_sigue_renderizando_con_img(self):
        procesar_archivos_subidos(
            self.ticket,
            [SimpleUploadedFile("foto.png", PNG_1X1, content_type="image/png")],
        )

        response = self.client.get(
            reverse("feedback:detalle", kwargs={"ticket_id": self.ticket.id})
        )

        html = response.content.decode()
        self.assertIn("<img", html)
        self.assertIn('data-tipo="imagen"', html)


class FormularioAceptaMediaTestCase(TestCase):
    """El input tiene que ofrecer audio/video, si no el usuario ni puede elegirlo."""

    def test_input_accept_incluye_audio_y_video(self):
        response = self.client.get(reverse("feedback:nuevo"))

        self.assertContains(response, 'accept="image/*,audio/*,video/*"')

    def test_hay_botones_de_grabar_audio_y_video(self):
        response = self.client.get(reverse("feedback:nuevo"))

        self.assertContains(response, 'id="btn-grabar-audio"')
        self.assertContains(response, 'id="btn-grabar-video"')

    def test_el_js_recibe_los_limites_reales_del_backend(self):
        """Si el JS hardcodea los límites, se desincroniza del servidor."""
        with override_settings(FEEDBACK_MAX_ATTACHMENTS=7, FEEDBACK_MAX_ATTACHMENT_BYTES=12345):
            response = self.client.get(reverse("feedback:nuevo"))

        html = response.content.decode()
        self.assertIn("var MAX_FILES = 7;", html)
        self.assertIn("var MAX_BYTES = 12345;", html)

    def test_post_con_audio_crea_ticket_con_adjunto_de_audio(self):
        """End-to-end HTTP: el flujo que el cliente dice que falta."""
        datos = {
            "nombre_reportante": "Ana Pérez",
            "asunto": "No se escucha el audio",
            "descripcion": "Grabé un audio explicando el problema del módulo 3.",
            "website": "",
        }
        archivo = SimpleUploadedFile(
            "audio-2026-07-28.webm", WEBM_FAKE, content_type="audio/webm;codecs=opus"
        )

        response = self.client.post(
            reverse("feedback:nuevo"), data={**datos, "imagenes": [archivo]}
        )

        self.assertEqual(response.status_code, 302)
        ticket = FeedbackTicket.objects.get(asunto="No se escucha el audio")
        adjunto = ticket.adjuntos.get()
        self.assertEqual(adjunto.tipo, FeedbackAttachment.TIPO_AUDIO)
