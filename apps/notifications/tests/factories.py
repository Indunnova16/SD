"""
Factory classes for notifications tests.

Uses factory_boy to create test data for all notification models.
"""

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

import factory
from factory.django import DjangoModelFactory

from apps.notifications.models import (
    Notification,
    NotificationTemplate,
    PushSubscription,
    UserNotificationPreference,
)

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for User model."""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"notifuser{n}@test.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: f"{20000000 + n}")
    job_position = "Technician"
    # `job_profile` es FK a `courses.JobProfileType` (nullable) — issue #58
    # (PLAN F2): el enum `User.JobProfile` (TextChoices) es código muerto, y
    # el string "LINIERO" NUNCA fue un valor válido acá (ValueError: Cannot
    # assign — pre-existente, ajeno a RBAC, mismo patrón que A4 documentó en
    # otras 9 apps). None es el valor seguro que ya usan el resto de
    # factories/fixtures del repo.
    job_profile = None
    hire_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    is_active = True


class StaffUserFactory(UserFactory):
    """Factory for staff users."""

    email = factory.Sequence(lambda n: f"notifstaff{n}@test.com")
    is_staff = True


class AdminUserFactory(UserFactory):
    """Factory for admin users."""

    email = factory.Sequence(lambda n: f"notifadmin{n}@test.com")
    is_staff = True
    is_superuser = True
    # RBAC (issue #58, A10): `NotificationTemplateViewSet` ahora exige
    # `rol == ADMINISTRADOR` (ver `apps.notifications.api.permissions
    # .IsAdministrador`) — `is_staff`/`is_superuser` solos ya NO alcanzan
    # (decisión de Miguel #2 del PLAN: `rol` es la única fuente de verdad).
    rol = User.Rol.ADMINISTRADOR


class NotificationTemplateFactory(DjangoModelFactory):
    """Factory for NotificationTemplate model."""

    class Meta:
        model = NotificationTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Template {n}")
    description = factory.Faker("sentence")
    subject = factory.Sequence(lambda n: f"Test Subject {n}")
    body = factory.Faker("paragraph")
    html_body = factory.LazyAttribute(lambda obj: f"<p>{obj.body}</p>")
    channel = NotificationTemplate.Channel.IN_APP
    is_active = True


class EmailTemplateFactory(NotificationTemplateFactory):
    """Factory for email notification templates."""

    name = factory.Sequence(lambda n: f"Email Template {n}")
    channel = NotificationTemplate.Channel.EMAIL
    html_body = factory.LazyAttribute(
        lambda obj: f"<html><body><h1>{obj.subject}</h1><p>{obj.body}</p></body></html>"
    )


class PushTemplateFactory(NotificationTemplateFactory):
    """Factory for push notification templates."""

    name = factory.Sequence(lambda n: f"Push Template {n}")
    channel = NotificationTemplate.Channel.PUSH
    html_body = ""


class SMSTemplateFactory(NotificationTemplateFactory):
    """Factory for SMS notification templates."""

    name = factory.Sequence(lambda n: f"SMS Template {n}")
    channel = NotificationTemplate.Channel.SMS
    html_body = ""
    body = factory.Faker("text", max_nb_chars=160)


class InactiveTemplateFactory(NotificationTemplateFactory):
    """Factory for inactive notification templates."""

    name = factory.Sequence(lambda n: f"Inactive Template {n}")
    is_active = False


class NotificationFactory(DjangoModelFactory):
    """Factory for Notification model."""

    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    template = None
    channel = NotificationTemplate.Channel.IN_APP
    subject = factory.Sequence(lambda n: f"Notification Subject {n}")
    body = factory.Faker("paragraph")
    status = Notification.Status.PENDING
    priority = Notification.Priority.NORMAL
    action_url = ""
    action_text = ""
    metadata = factory.LazyFunction(dict)
    sent_at = None
    delivered_at = None
    read_at = None
    error_message = ""
    retry_count = 0


class SentNotificationFactory(NotificationFactory):
    """Factory for sent notifications."""

    status = Notification.Status.SENT
    sent_at = factory.LazyFunction(timezone.now)


class DeliveredNotificationFactory(NotificationFactory):
    """Factory for delivered notifications."""

    status = Notification.Status.DELIVERED
    sent_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=5))
    delivered_at = factory.LazyFunction(timezone.now)


class ReadNotificationFactory(NotificationFactory):
    """Factory for read notifications."""

    status = Notification.Status.READ
    sent_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1))
    delivered_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=30))
    read_at = factory.LazyFunction(timezone.now)


class FailedNotificationFactory(NotificationFactory):
    """Factory for failed notifications."""

    status = Notification.Status.FAILED
    error_message = "Failed to send notification"
    retry_count = 1


class EmailNotificationFactory(NotificationFactory):
    """Factory for email notifications."""

    channel = NotificationTemplate.Channel.EMAIL
    template = factory.SubFactory(EmailTemplateFactory)


class PushNotificationFactory(NotificationFactory):
    """Factory for push notifications."""

    channel = NotificationTemplate.Channel.PUSH


class SMSNotificationFactory(NotificationFactory):
    """Factory for SMS notifications."""

    channel = NotificationTemplate.Channel.SMS


class HighPriorityNotificationFactory(NotificationFactory):
    """Factory for high priority notifications."""

    priority = Notification.Priority.HIGH


class UrgentNotificationFactory(NotificationFactory):
    """Factory for urgent notifications."""

    priority = Notification.Priority.URGENT


class NotificationWithActionFactory(NotificationFactory):
    """Factory for notifications with action URL."""

    action_url = "https://example.com/action"
    action_text = "Ver detalles"


class UserNotificationPreferenceFactory(DjangoModelFactory):
    """Factory for UserNotificationPreference model.

    Note: When a User is created, a signal automatically creates
    UserNotificationPreference with default values. This factory
    gets the existing preference and updates it with the specified values.
    """

    class Meta:
        model = UserNotificationPreference

    user = factory.SubFactory(UserFactory)
    email_enabled = True
    push_enabled = True
    sms_enabled = False
    in_app_enabled = True
    course_reminders = True
    assessment_results = True
    certificate_issued = True
    new_assignments = True
    deadline_reminders = True
    lesson_learned_updates = True
    quiet_hours_start = None
    quiet_hours_end = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to update existing preferences created by signal."""
        user = kwargs.pop("user", None)
        if user:
            # Get existing preference (created by signal) or create new one
            obj, created = model_class.objects.get_or_create(user=user)
            # Update all attributes from kwargs
            for key, value in kwargs.items():
                setattr(obj, key, value)
            obj.save()
            return obj
        # If no user, use default factory behavior (will create new user)
        return super()._create(model_class, *args, **kwargs)


class AllChannelsEnabledPreferenceFactory(UserNotificationPreferenceFactory):
    """Factory for preferences with all channels enabled."""

    email_enabled = True
    push_enabled = True
    sms_enabled = True
    in_app_enabled = True


class AllChannelsDisabledPreferenceFactory(UserNotificationPreferenceFactory):
    """Factory for preferences with all channels disabled."""

    email_enabled = False
    push_enabled = False
    sms_enabled = False
    in_app_enabled = False


class QuietHoursPreferenceFactory(UserNotificationPreferenceFactory):
    """Factory for preferences with quiet hours set."""

    quiet_hours_start = time(22, 0)  # 10 PM
    quiet_hours_end = time(7, 0)  # 7 AM


class MinimalNotificationsPreferenceFactory(UserNotificationPreferenceFactory):
    """Factory for preferences with minimal notifications."""

    course_reminders = False
    assessment_results = True  # Keep only critical notifications
    certificate_issued = True
    new_assignments = False
    deadline_reminders = True
    lesson_learned_updates = False


class PushSubscriptionFactory(DjangoModelFactory):
    """Factory for PushSubscription model."""

    class Meta:
        model = PushSubscription

    user = factory.SubFactory(UserFactory)
    endpoint = factory.Sequence(lambda n: f"https://push.example.com/endpoint/{n}")
    p256dh_key = factory.Sequence(
        lambda n: (
            f"BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM{n}"
        )
    )
    auth_key = factory.Sequence(lambda n: f"tBHItJI5svbpez7KI4CCXg{n}")
    device_name = factory.Faker("user_agent")
    device_type = factory.Iterator(["mobile", "desktop", "tablet"])
    is_active = True


class InactivePushSubscriptionFactory(PushSubscriptionFactory):
    """Factory for inactive push subscriptions."""

    is_active = False


class MobilePushSubscriptionFactory(PushSubscriptionFactory):
    """Factory for mobile push subscriptions."""

    device_name = "iPhone 15 Pro"
    device_type = "mobile"


class DesktopPushSubscriptionFactory(PushSubscriptionFactory):
    """Factory for desktop push subscriptions."""

    device_name = "Chrome on Windows"
    device_type = "desktop"
