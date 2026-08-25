"""Issue #144: rol TESORERIA con acceso EXCLUSIVO al modulo de pagos.

El resto de las apps del portal (courses, assessments, certifications,
reports, gamification, preop_talks) solo exigen `@login_required` sin
chequeo de rol adicional -- sin `TesoreriaScopeMiddleware`, un usuario
TESORERIA tendria acceso amplio a todas ellas via esas vistas. Este test
verifica el aislamiento real: TESORERIA entra a /pagos/ y es redirigido
de vuelta desde cualquier otra app; ADMINISTRADOR no se ve afectado.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


def _crear_tesoreria(document_number='90000144', **overrides):
    defaults = dict(
        password='x',
        first_name='Tesoreria',
        last_name='SD',
        job_position='Tesoreria',
        hire_date=date(2024, 1, 1),
        rol=User.Rol.TESORERIA,
    )
    defaults.update(overrides)
    return User.objects.create_user(document_number=document_number, **defaults)


def _crear_administrador(document_number='90000145', **overrides):
    defaults = dict(
        password='x',
        first_name='QA',
        last_name='Admin',
        job_position='Administrador',
        hire_date=date(2024, 1, 1),
        rol=User.Rol.ADMINISTRADOR,
    )
    defaults.update(overrides)
    return User.objects.create_user(document_number=document_number, **defaults)


class TesoreriaScopeMiddlewareTests(TestCase):
    def setUp(self):
        self.tesoreria = _crear_tesoreria()
        self.client = Client()
        self.client.force_login(self.tesoreria)

    def test_tesoreria_accede_al_portal_de_pagos(self):
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.status_code, 200)

    def test_tesoreria_bloqueada_de_cursos_redirige_a_pagos(self):
        r = self.client.get('/courses/', follow=True)
        self.assertRedirects(r, reverse('pagos:portal'))
        mensajes = [str(m) for m in r.context['messages']]
        self.assertTrue(any('solo tiene acceso al módulo de pagos' in m for m in mensajes))

    def test_tesoreria_bloqueada_de_reportes_redirige_a_pagos(self):
        r = self.client.get('/reports/dashboard/', follow=True)
        self.assertRedirects(r, reverse('pagos:portal'))

    def test_tesoreria_bloqueada_de_gestion_usuarios_redirige_a_pagos(self):
        r = self.client.get('/accounts/users/', follow=True)
        self.assertRedirects(r, reverse('pagos:portal'))

    def test_tesoreria_puede_hacer_logout(self):
        r = self.client.get(reverse('accounts:logout'))
        self.assertNotEqual(r.status_code, 403)

    def test_tesoreria_puede_pollear_notificaciones_sin_ser_redirigida(self):
        r = self.client.get('/notifications/unread-count/')
        self.assertNotIn(r.status_code, (301, 302))


class TesoreriaScopeMiddlewareNoAfectaOtrosRolesTests(TestCase):
    """Regresion: el middleware NO debe restringir a roles distintos de
    TESORERIA -- un ADMINISTRADOR debe seguir con acceso amplio."""

    def setUp(self):
        self.admin = _crear_administrador()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_administrador_sigue_accediendo_a_cursos(self):
        r = self.client.get('/courses/')
        self.assertEqual(r.status_code, 200)

    def test_administrador_sigue_accediendo_a_pagos(self):
        r = self.client.get(reverse('pagos:portal'))
        self.assertEqual(r.status_code, 200)
