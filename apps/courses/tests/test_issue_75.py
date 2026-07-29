"""
Tests for SD#75 — las notificaciones de vencimiento nunca se creaban.

Causa raiz
----------
`_send_deadline_notification` (apps/courses/tasks.py) construia el modelo a
mano con `Notification.objects.create(title=..., message=...)`, pero
`apps.notifications.models.Notification` define `subject`/`body`. Django lanza
`TypeError` ante kwargs desconocidos, asi que **toda** llamada fallaba... y el
`except Exception` que la envolvia la degradaba a `logger.warning` sin traza.
Resultado: cero notificaciones creadas y cero senal en los logs. Meses.

`check_enrollment_deadlines` corre a diario y notifica en 3 momentos
(vencido -> usuario + cada admin; por vencer en 3 dias; por vencer en 1 dia):
las 3 rutas pasan por el mismo helper, o sea que las 3 estaban rotas.

Que cubren estos tests
----------------------
El test que NO habria atrapado el bug es "la funcion no lanza excepcion" —
justamente lo que el `except` garantizaba. Aca se afirma que la fila
**existe en BD** y con los campos correctos:

  - test_helper_persiste_notificacion_con_campos_del_modelo
  - test_modelo_no_acepta_title_message  (regresion literal del typo)
  - test_task_notifica_al_usuario_y_al_admin_por_curso_vencido
  - test_task_notifica_por_curso_proximo_a_vencer  (3 dias y 1 dia)
  - test_fallo_se_loguea_a_error_con_stack  (el except ya no oculta nada)
"""

import logging
from datetime import timedelta

from django.utils import timezone

import pytest

from apps.courses.models import Enrollment
from apps.courses.tasks import _send_deadline_notification, check_enrollment_deadlines
from apps.courses.tests.factories import (
    AdminUserFactory,
    EnrollmentFactory,
    PublishedCourseFactory,
    UserFactory,
)
from apps.notifications.models import Notification, NotificationTemplate


@pytest.mark.django_db
class TestSendDeadlineNotificationHelper:
    """El helper debe DEJAR LA FILA en la tabla, no solo no explotar."""

    def test_helper_persiste_notificacion_con_campos_del_modelo(self):
        user = UserFactory()

        result = _send_deadline_notification(
            user=user,
            title="Curso vencido",
            message="Tu curso 'Trabajo en Alturas' ha vencido.",
            priority="high",
        )

        # Lo que el bug impedia: que exista la fila.
        assert Notification.objects.filter(user=user).count() == 1

        notification = Notification.objects.get(user=user)
        assert result is not None
        assert result.pk == notification.pk

        # Los nombres reales del modelo (subject/body), no title/message.
        assert notification.subject == "Curso vencido"
        assert notification.body == "Tu curso 'Trabajo en Alturas' ha vencido."
        assert notification.channel == NotificationTemplate.Channel.IN_APP
        assert notification.priority == Notification.Priority.HIGH
        assert notification.status == Notification.Status.DELIVERED
        assert notification.delivered_at is not None

    def test_modelo_no_acepta_title_message(self):
        """Regresion literal: el typo original era un TypeError duro."""
        user = UserFactory()

        with pytest.raises(TypeError):
            Notification.objects.create(
                user=user,
                title="Curso vencido",
                message="Tu curso ha vencido.",
                channel="in_app",
            )

        assert not Notification.objects.filter(user=user).exists()

    def test_fallo_se_loguea_a_error_con_stack(self, monkeypatch, caplog):
        """El `except` ya no puede volver invisible un fallo de creacion."""
        from apps.notifications.services import NotificationService

        def boom(*args, **kwargs):
            raise RuntimeError("BD caida")

        monkeypatch.setattr(NotificationService, "create_notification", boom)
        user = UserFactory()

        with caplog.at_level(logging.ERROR, logger="apps.courses.tasks"):
            result = _send_deadline_notification(user=user, title="Curso vencido", message="cuerpo")

        assert result is None
        assert not Notification.objects.filter(user=user).exists()

        records = [r for r in caplog.records if r.name == "apps.courses.tasks"]
        assert records, "el fallo debe quedar en el log, no descartarse en silencio"
        record = records[-1]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None, "debe conservar el stack trace"
        assert "BD caida" in caplog.text


@pytest.mark.django_db
class TestCheckEnrollmentDeadlinesCreaNotificaciones:
    """La task diaria completa: la matricula cambia de estado Y avisa."""

    def _setup(self, due_date, status=Enrollment.Status.ENROLLED):
        # Usuarios ANTES del curso: el signal de auto-matricula por perfil solo
        # dispara al guardar el usuario, asi que este orden evita matriculas
        # espurias que ensucien el conteo.
        user = UserFactory()
        admin = AdminUserFactory()
        course = PublishedCourseFactory(title="Trabajo en Alturas")
        enrollment = EnrollmentFactory(
            user=user,
            course=course,
            assigned_by=admin,
            due_date=due_date,
            status=status,
        )
        return user, admin, course, enrollment

    def test_task_notifica_al_usuario_y_al_admin_por_curso_vencido(self):
        ayer = timezone.now().date() - timedelta(days=1)
        user, admin, course, enrollment = self._setup(ayer)

        check_enrollment_deadlines()

        enrollment.refresh_from_db()
        assert enrollment.status == Enrollment.Status.EXPIRED

        # Al usuario
        user_notifications = Notification.objects.filter(user=user)
        assert user_notifications.count() == 1
        aviso = user_notifications.get()
        assert aviso.subject == "Curso vencido"
        assert "Trabajo en Alturas" in aviso.body
        assert aviso.priority == Notification.Priority.HIGH
        assert aviso.status == Notification.Status.DELIVERED

        # Al admin
        admin_notifications = Notification.objects.filter(user=admin)
        assert admin_notifications.count() == 1
        aviso_admin = admin_notifications.get()
        assert aviso_admin.subject == "Curso vencido - Usuario"
        assert "Trabajo en Alturas" in aviso_admin.body
        assert user.document_number in aviso_admin.body
        assert aviso_admin.priority == Notification.Priority.NORMAL

    @pytest.mark.parametrize(
        ("dias", "subject_esperado", "priority_esperada"),
        [
            (3, "Curso por vencer en 3 días", Notification.Priority.HIGH),
            (1, "Curso por vencer en 1 día", Notification.Priority.URGENT),
        ],
    )
    def test_task_notifica_por_curso_proximo_a_vencer(
        self, dias, subject_esperado, priority_esperada
    ):
        vence = timezone.now().date() + timedelta(days=dias)
        user, admin, course, enrollment = self._setup(vence)

        check_enrollment_deadlines()

        enrollment.refresh_from_db()
        assert enrollment.status == Enrollment.Status.ENROLLED  # aun no vencio

        notifications = Notification.objects.filter(user=user)
        assert notifications.count() == 1
        aviso = notifications.get()
        assert aviso.subject == subject_esperado
        assert "Trabajo en Alturas" in aviso.body
        assert vence.strftime("%d/%m/%Y") in aviso.body
        assert aviso.priority == priority_esperada
        assert aviso.status == Notification.Status.DELIVERED

        # El aviso de "por vencer" es solo para el usuario, no para admins.
        assert not Notification.objects.filter(user=admin).exists()

    def test_matricula_completada_no_genera_aviso(self):
        """Guardarrail: solo ENROLLED/IN_PROGRESS entran al barrido."""
        ayer = timezone.now().date() - timedelta(days=1)
        user, _admin, _course, enrollment = self._setup(ayer, status=Enrollment.Status.COMPLETED)

        check_enrollment_deadlines()

        enrollment.refresh_from_db()
        assert enrollment.status == Enrollment.Status.COMPLETED
        assert not Notification.objects.filter(user=user).exists()
