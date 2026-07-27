"""
Tests del sub-item A1 (app skeleton + modelos) del portal de feedback.

Cubre: __str__ de FeedbackTicket, que la migración 0001_initial aplica
limpio sobre la BD de test (implícito en que este módulo colecta y corre
sin errores de BD), y los valores por defecto de los campos de
sincronización con GitHub. Tests de A2-A8 (github_client, forms, services,
views) se agregan a este mismo archivo en sub-items posteriores.
"""

from django.test import TestCase

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
