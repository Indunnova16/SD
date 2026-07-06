"""
Tests for notifications API endpoints.

Covers:
- NotificationViewSet
- NotificationTemplateViewSet
- UserNotificationPreferenceViewSet
- PushSubscriptionViewSet
"""

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.models import (
    Notification,
    NotificationTemplate,
    PushSubscription,
    UserNotificationPreference,
)

from .factories import (
    AdminUserFactory,
    EmailNotificationFactory,
    EmailTemplateFactory,
    HighPriorityNotificationFactory,
    NotificationFactory,
    NotificationTemplateFactory,
    PushNotificationFactory,
    PushSubscriptionFactory,
    PushTemplateFactory,
    ReadNotificationFactory,
    SentNotificationFactory,
    StaffUserFactory,
    UserFactory,
    UserNotificationPreferenceFactory,
)


@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()


@pytest.fixture
def user():
    """Create and return a regular user."""
    return UserFactory()


@pytest.fixture
def staff_user():
    """Create and return a staff user."""
    return StaffUserFactory()


@pytest.fixture
def admin_user():
    """Create and return an admin user."""
    return AdminUserFactory()


@pytest.fixture
def authenticated_client(api_client, user):
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def staff_client(api_client, staff_user):
    """Return an authenticated staff API client."""
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Return an authenticated admin API client."""
    api_client.force_authenticate(user=admin_user)
    return api_client


# =============================================================================
# NotificationViewSet Tests
# =============================================================================


@pytest.mark.django_db
class TestNotificationList:
    """Tests for listing notifications."""

    def test_list_notifications_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list notifications."""
        url = reverse("notifications_api:notification-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_notifications_empty(self, authenticated_client):
        """Test listing notifications when user has none."""
        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 0

    def test_list_own_notifications(self, authenticated_client, user):
        """Test listing user's own notifications."""
        NotificationFactory(user=user)
        NotificationFactory(user=user)
        other_user = UserFactory()
        NotificationFactory(user=other_user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2

    def test_list_notifications_ordered_by_created_at(self, authenticated_client, user):
        """Test that notifications are ordered by created_at descending."""
        old_notification = NotificationFactory(user=user)
        new_notification = NotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url)

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert results[0]["id"] == new_notification.id
        assert results[1]["id"] == old_notification.id

    def test_list_notifications_filter_by_status(self, authenticated_client, user):
        """Test filtering notifications by status."""
        SentNotificationFactory(user=user)
        ReadNotificationFactory(user=user)
        SentNotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url, {"status": "sent"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2
        for result in results:
            assert result["status"] == "sent"

    def test_list_notifications_filter_by_channel(self, authenticated_client, user):
        """Test filtering notifications by channel."""
        EmailNotificationFactory(user=user)
        PushNotificationFactory(user=user)
        EmailNotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url, {"channel": "email"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2

    def test_list_notifications_filter_unread(self, authenticated_client, user):
        """Test filtering unread notifications."""
        NotificationFactory(user=user)
        ReadNotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url, {"unread": "true"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 1

    def test_list_notifications_filter_by_priority(self, authenticated_client, user):
        """Test filtering notifications by priority."""
        NotificationFactory(user=user, priority=Notification.Priority.NORMAL)
        HighPriorityNotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url, {"priority": "high"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 1
        assert results[0]["priority"] == "high"

    def test_staff_can_filter_by_user(self, staff_client, staff_user):
        """Test that staff can filter notifications by user."""
        user1 = UserFactory()
        user2 = UserFactory()
        NotificationFactory(user=user1)
        NotificationFactory(user=user1)
        NotificationFactory(user=user2)

        url = reverse("notifications_api:notification-list")
        response = staff_client.get(url, {"user": user1.id})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2


@pytest.mark.django_db
class TestNotificationDetail:
    """Tests for notification detail view."""

    def test_get_notification_detail(self, authenticated_client, user):
        """Test getting notification detail."""
        notification = NotificationFactory(user=user)

        url = reverse(
            "notifications_api:notification-detail",
            args=[notification.id],
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == notification.id
        assert response.data["subject"] == notification.subject

    def test_cannot_get_other_user_notification(self, authenticated_client):
        """Test that users cannot get other users' notifications."""
        other_user = UserFactory()
        notification = NotificationFactory(user=other_user)

        url = reverse(
            "notifications_api:notification-detail",
            args=[notification.id],
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestNotificationMarkRead:
    """Tests for marking notifications as read."""

    def test_mark_notification_read(self, authenticated_client, user):
        """Test marking a notification as read."""
        notification = SentNotificationFactory(user=user)

        url = reverse(
            "notifications_api:notification-mark-read",
            args=[notification.id],
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.read_at is not None
        assert notification.status == Notification.Status.READ

    def test_mark_notification_read_idempotent(self, authenticated_client, user):
        """Test that marking as read is idempotent."""
        notification = ReadNotificationFactory(user=user)
        original_read_at = notification.read_at

        url = reverse(
            "notifications_api:notification-mark-read",
            args=[notification.id],
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.read_at == original_read_at

    def test_cannot_mark_other_user_notification_read(self, authenticated_client):
        """Test that users cannot mark other users' notifications as read."""
        other_user = UserFactory()
        notification = NotificationFactory(user=other_user)

        url = reverse(
            "notifications_api:notification-mark-read",
            args=[notification.id],
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_staff_can_mark_any_notification_read(self, staff_client):
        """Test that staff can mark any notification as read."""
        other_user = UserFactory()
        notification = SentNotificationFactory(user=other_user)

        url = reverse(
            "notifications_api:notification-mark-read",
            args=[notification.id],
        )
        response = staff_client.post(url)

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestNotificationMarkAllRead:
    """Tests for marking all notifications as read."""

    def test_mark_all_read(self, authenticated_client, user):
        """Test marking all notifications as read."""
        NotificationFactory(user=user)
        NotificationFactory(user=user)
        NotificationFactory(user=user)

        url = reverse("notifications_api:notification-mark-all-read")
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated"] == 3

        unread_count = Notification.objects.filter(user=user, read_at__isnull=True).count()
        assert unread_count == 0

    def test_mark_all_read_only_unread(self, authenticated_client, user):
        """Test that mark all read only affects unread notifications."""
        NotificationFactory(user=user)
        ReadNotificationFactory(user=user)

        url = reverse("notifications_api:notification-mark-all-read")
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated"] == 1

    def test_mark_all_read_does_not_affect_other_users(self, authenticated_client, user):
        """Test that mark all read doesn't affect other users' notifications."""
        other_user = UserFactory()
        NotificationFactory(user=user)
        NotificationFactory(user=other_user)

        url = reverse("notifications_api:notification-mark-all-read")
        authenticated_client.post(url)

        other_unread = Notification.objects.filter(user=other_user, read_at__isnull=True).count()
        assert other_unread == 1


@pytest.mark.django_db
class TestNotificationMarkSelectedRead:
    """Tests for marking selected notifications as read."""

    def test_mark_selected_read(self, authenticated_client, user):
        """Test marking selected notifications as read."""
        n1 = NotificationFactory(user=user)
        n2 = NotificationFactory(user=user)
        n3 = NotificationFactory(user=user)

        url = reverse("notifications_api:notification-mark-selected-read")
        response = authenticated_client.post(
            url,
            {"notification_ids": [n1.id, n2.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated"] == 2

        n3.refresh_from_db()
        assert n3.read_at is None

    def test_mark_selected_read_with_mark_all(self, authenticated_client, user):
        """Test mark selected with mark_all flag."""
        NotificationFactory(user=user)
        NotificationFactory(user=user)

        url = reverse("notifications_api:notification-mark-selected-read")
        response = authenticated_client.post(
            url,
            {"mark_all": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated"] == 2


@pytest.mark.django_db
class TestNotificationUnreadCount:
    """Tests for unread notification count."""

    def test_get_unread_count(self, authenticated_client, user):
        """Test getting unread notification count."""
        NotificationFactory(user=user)
        NotificationFactory(user=user)
        ReadNotificationFactory(user=user)

        url = reverse("notifications_api:notification-unread-count")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2

    def test_unread_count_zero(self, authenticated_client, user):
        """Test unread count when all are read."""
        ReadNotificationFactory(user=user)

        url = reverse("notifications_api:notification-unread-count")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0


@pytest.mark.django_db
class TestNotificationSend:
    """Tests for sending notifications (staff only)."""

    def test_send_notification_requires_staff(self, authenticated_client, user):
        """Test that only staff can send notifications."""
        url = reverse("notifications_api:notification-send")
        response = authenticated_client.post(
            url,
            {"user_id": user.id, "subject": "Test", "body": "Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_send_notification_as_staff(self, staff_client):
        """Test sending notification as staff."""
        target_user = UserFactory()

        url = reverse("notifications_api:notification-send")
        response = staff_client.post(
            url,
            {
                "user_id": target_user.id,
                "subject": "Staff Notification",
                "body": "Sent by staff",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] == 1

        notification = Notification.objects.get(user=target_user)
        assert notification.subject == "Staff Notification"

    def test_send_notification_to_multiple_users(self, staff_client):
        """Test sending notification to multiple users."""
        users = [UserFactory() for _ in range(3)]
        user_ids = [u.id for u in users]

        url = reverse("notifications_api:notification-send")
        response = staff_client.post(
            url,
            {
                "user_ids": user_ids,
                "subject": "Bulk Notification",
                "body": "Sent to multiple users",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] == 3

    def test_send_notification_with_template(self, staff_client):
        """Test sending notification with template."""
        template = NotificationTemplateFactory()
        target_user = UserFactory()

        url = reverse("notifications_api:notification-send")
        response = staff_client.post(
            url,
            {
                "user_id": target_user.id,
                "template_id": template.id,
                "subject": "Templated",
                "body": "Using template",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        notification = Notification.objects.get(user=target_user)
        assert notification.template == template

    def test_send_notification_with_priority(self, staff_client):
        """Test sending notification with priority."""
        target_user = UserFactory()

        url = reverse("notifications_api:notification-send")
        response = staff_client.post(
            url,
            {
                "user_id": target_user.id,
                "subject": "Urgent",
                "body": "Urgent message",
                "priority": "urgent",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        notification = Notification.objects.get(user=target_user)
        assert notification.priority == Notification.Priority.URGENT

    def test_send_notification_requires_user(self, staff_client):
        """Test that sending requires at least one user."""
        url = reverse("notifications_api:notification-send")
        response = staff_client.post(
            url,
            {"subject": "Test", "body": "Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# NotificationTemplateViewSet Tests
#
# Issue #58 (RBAC, sub-item A10): esta superficie es "Sistema" (config de
# plantillas admin), gap real cerrado acá — antes cualquier autenticado
# (`authenticated_client`, usuario regular) podía listar/crear/editar/borrar
# plantillas. Ahora exige `rol == ADMINISTRADOR`
# (`apps.notifications.api.permissions.IsAdministrador`). Los tests de éxito
# migran a `admin_client`; se agrega un test explícito de 403 para no-Admin
# por acción (list/create/update/delete).
# =============================================================================


@pytest.mark.django_db
class TestNotificationTemplateList:
    """Tests for listing notification templates."""

    def test_list_templates_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list templates."""
        url = reverse("notifications_api:template-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_templates_forbidden_for_non_admin(self, authenticated_client):
        """RBAC A10: usuario autenticado SIN rol=ADMINISTRADOR -> 403."""
        NotificationTemplateFactory()

        url = reverse("notifications_api:template-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_templates(self, admin_client):
        """Test listing templates."""
        NotificationTemplateFactory()
        NotificationTemplateFactory()

        url = reverse("notifications_api:template-list")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2

    def test_list_templates_filter_by_channel(self, admin_client):
        """Test filtering templates by channel."""
        EmailTemplateFactory()
        EmailTemplateFactory()
        PushTemplateFactory()

        url = reverse("notifications_api:template-list")
        response = admin_client.get(url, {"channel": "email"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2

    def test_list_templates_filter_active(self, admin_client):
        """Test filtering active templates."""
        NotificationTemplateFactory(is_active=True)
        NotificationTemplateFactory(is_active=False)

        url = reverse("notifications_api:template-list")
        response = admin_client.get(url, {"active": "true"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 1

    def test_list_templates_search(self, admin_client):
        """Test searching templates."""
        NotificationTemplateFactory(name="Welcome Email")
        NotificationTemplateFactory(name="Password Reset")

        url = reverse("notifications_api:template-list")
        response = admin_client.get(url, {"search": "Welcome"})

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 1
        assert "Welcome" in results[0]["name"]


@pytest.mark.django_db
class TestNotificationTemplateCreate:
    """Tests for creating notification templates."""

    def test_create_template_forbidden_for_non_admin(self, authenticated_client):
        """RBAC A10: usuario autenticado SIN rol=ADMINISTRADOR -> 403, no crea nada."""
        url = reverse("notifications_api:template-list")
        response = authenticated_client.post(
            url,
            {
                "name": "Intento No Admin",
                "subject": "Subject",
                "body": "Body content",
                "channel": "email",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not NotificationTemplate.objects.filter(name="Intento No Admin").exists()

    def test_create_template(self, admin_client):
        """Test creating a template."""
        url = reverse("notifications_api:template-list")
        response = admin_client.post(
            url,
            {
                "name": "New Template",
                "description": "A new template",
                "subject": "Subject",
                "body": "Body content",
                "channel": "email",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Template"

    def test_create_template_with_html(self, admin_client):
        """Test creating a template with HTML body."""
        url = reverse("notifications_api:template-list")
        response = admin_client.post(
            url,
            {
                "name": "HTML Template",
                "subject": "Subject",
                "body": "Plain text",
                "html_body": "<p>HTML content</p>",
                "channel": "email",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["html_body"] == "<p>HTML content</p>"

    def test_create_template_duplicate_name_fails(self, admin_client):
        """Test that duplicate template names fail."""
        NotificationTemplateFactory(name="Existing Template")

        url = reverse("notifications_api:template-list")
        response = admin_client.post(
            url,
            {
                "name": "Existing Template",
                "subject": "Subject",
                "body": "Body",
                "channel": "in_app",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestNotificationTemplateUpdate:
    """Tests for updating notification templates."""

    def test_update_template_forbidden_for_non_admin(self, authenticated_client):
        """RBAC A10: usuario autenticado SIN rol=ADMINISTRADOR -> 403, no cambia nada."""
        template = NotificationTemplateFactory(subject="Original Subject")

        url = reverse("notifications_api:template-detail", args=[template.id])
        response = authenticated_client.patch(
            url,
            {"subject": "Intento No Admin"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        template.refresh_from_db()
        assert template.subject == "Original Subject"

    def test_update_template(self, admin_client):
        """Test updating a template."""
        template = NotificationTemplateFactory()

        url = reverse("notifications_api:template-detail", args=[template.id])
        response = admin_client.patch(
            url,
            {"subject": "Updated Subject"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        template.refresh_from_db()
        assert template.subject == "Updated Subject"

    def test_deactivate_template(self, admin_client):
        """Test deactivating a template."""
        template = NotificationTemplateFactory(is_active=True)

        url = reverse("notifications_api:template-detail", args=[template.id])
        response = admin_client.patch(
            url,
            {"is_active": False},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        template.refresh_from_db()
        assert template.is_active is False


@pytest.mark.django_db
class TestNotificationTemplateDelete:
    """Tests for deleting notification templates."""

    def test_delete_template_forbidden_for_non_admin(self, authenticated_client):
        """RBAC A10: usuario autenticado SIN rol=ADMINISTRADOR -> 403, no borra nada."""
        template = NotificationTemplateFactory()

        url = reverse("notifications_api:template-detail", args=[template.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert NotificationTemplate.objects.filter(pk=template.pk).exists()

    def test_delete_template(self, admin_client):
        """Test deleting a template."""
        template = NotificationTemplateFactory()

        url = reverse("notifications_api:template-detail", args=[template.id])
        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not NotificationTemplate.objects.filter(pk=template.pk).exists()


# =============================================================================
# UserNotificationPreferenceViewSet Tests
# =============================================================================


@pytest.mark.django_db
class TestUserNotificationPreferences:
    """Tests for user notification preferences."""

    def test_get_preferences_returns_auto_created(self, api_client):
        """Test that getting preferences returns auto-created ones.

        Note: UserNotificationPreference is automatically created by a signal
        when a User is created. This test verifies the API returns those
        preferences correctly.
        """
        # Create a fresh user - signal creates preferences automatically
        new_user = UserFactory()
        api_client.force_authenticate(user=new_user)

        # Preferences should already exist due to signal
        assert UserNotificationPreference.objects.filter(user=new_user).exists()

        url = reverse("notifications_api:preference-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Verify default values from signal
        assert response.data["email_enabled"] is True
        assert response.data["push_enabled"] is True
        assert response.data["sms_enabled"] is False
        assert response.data["in_app_enabled"] is True

    def test_get_preferences_returns_existing(self, api_client):
        """Test that getting preferences returns existing ones."""
        # Create a fresh user and their preferences
        new_user = UserFactory()
        api_client.force_authenticate(user=new_user)
        UserNotificationPreferenceFactory(user=new_user, email_enabled=False)

        url = reverse("notifications_api:preference-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_enabled"] is False

    def test_update_preferences(self, authenticated_client, user):
        """Test updating preferences."""
        UserNotificationPreferenceFactory(user=user)

        url = reverse("notifications_api:preference-update-preferences")
        response = authenticated_client.patch(
            url,
            {
                "email_enabled": False,
                "course_reminders": False,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_enabled"] is False
        assert response.data["course_reminders"] is False

    def test_update_preferences_partial(self, authenticated_client, user):
        """Test partial update of preferences."""
        UserNotificationPreferenceFactory(
            user=user,
            email_enabled=True,
            push_enabled=True,
        )

        url = reverse("notifications_api:preference-update-preferences")
        response = authenticated_client.patch(
            url,
            {"email_enabled": False},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_enabled"] is False
        assert response.data["push_enabled"] is True  # Unchanged

    def test_update_quiet_hours(self, authenticated_client, user):
        """Test updating quiet hours."""
        UserNotificationPreferenceFactory(user=user)

        url = reverse("notifications_api:preference-update-preferences")
        response = authenticated_client.patch(
            url,
            {
                "quiet_hours_start": "22:00:00",
                "quiet_hours_end": "07:00:00",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["quiet_hours_start"] == "22:00:00"
        assert response.data["quiet_hours_end"] == "07:00:00"


# =============================================================================
# PushSubscriptionViewSet Tests
# =============================================================================


@pytest.mark.django_db
class TestPushSubscriptionList:
    """Tests for listing push subscriptions."""

    def test_list_subscriptions(self, authenticated_client, user):
        """Test listing user's push subscriptions."""
        PushSubscriptionFactory(user=user)
        PushSubscriptionFactory(user=user)
        other_user = UserFactory()
        PushSubscriptionFactory(user=other_user)

        url = reverse("notifications_api:push-subscription-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2


@pytest.mark.django_db
class TestPushSubscriptionSubscribe:
    """Tests for subscribing to push notifications."""

    def test_subscribe(self, authenticated_client, user):
        """Test subscribing to push notifications."""
        url = reverse("notifications_api:push-subscription-subscribe")
        response = authenticated_client.post(
            url,
            {
                "endpoint": "https://push.example.com/new-endpoint",
                "p256dh_key": "test_p256dh_key",
                "auth_key": "test_auth_key",
                "device_name": "Chrome on Mac",
                "device_type": "desktop",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert PushSubscription.objects.filter(user=user).count() == 1

    def test_subscribe_updates_existing(self, authenticated_client, user):
        """Test that subscribing with same endpoint updates existing."""
        existing = PushSubscriptionFactory(
            user=user,
            endpoint="https://push.example.com/existing",
            device_name="Old Name",
        )

        url = reverse("notifications_api:push-subscription-subscribe")
        response = authenticated_client.post(
            url,
            {
                "endpoint": "https://push.example.com/existing",
                "p256dh_key": "new_key",
                "auth_key": "new_auth",
                "device_name": "New Name",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        existing.refresh_from_db()
        assert existing.device_name == "New Name"
        assert existing.p256dh_key == "new_key"


@pytest.mark.django_db
class TestPushSubscriptionUnsubscribe:
    """Tests for unsubscribing from push notifications."""

    def test_unsubscribe(self, authenticated_client, user):
        """Test unsubscribing from push notifications."""
        subscription = PushSubscriptionFactory(
            user=user,
            endpoint="https://push.example.com/to-unsubscribe",
        )

        url = reverse("notifications_api:push-subscription-unsubscribe")
        response = authenticated_client.post(
            url,
            {"endpoint": "https://push.example.com/to-unsubscribe"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["unsubscribed"] is True
        subscription.refresh_from_db()
        assert subscription.is_active is False

    def test_unsubscribe_requires_endpoint(self, authenticated_client):
        """Test that unsubscribing requires endpoint."""
        url = reverse("notifications_api:push-subscription-unsubscribe")
        response = authenticated_client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unsubscribe_nonexistent(self, authenticated_client, user):
        """Test unsubscribing from nonexistent subscription."""
        url = reverse("notifications_api:push-subscription-unsubscribe")
        response = authenticated_client.post(
            url,
            {"endpoint": "https://push.example.com/nonexistent"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["unsubscribed"] is False


@pytest.mark.django_db
class TestPushSubscriptionCreate:
    """Tests for creating push subscriptions."""

    def test_create_subscription(self, authenticated_client, user):
        """Test creating a push subscription."""
        url = reverse("notifications_api:push-subscription-list")
        response = authenticated_client.post(
            url,
            {
                "endpoint": "https://push.example.com/create",
                "p256dh_key": "p256dh_key_value",
                "auth_key": "auth_key_value",
                "device_name": "Test Device",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        subscription = PushSubscription.objects.get(user=user)
        assert subscription.endpoint == "https://push.example.com/create"


@pytest.mark.django_db
class TestPushSubscriptionDelete:
    """Tests for deleting push subscriptions."""

    def test_delete_subscription(self, authenticated_client, user):
        """Test deleting a push subscription."""
        subscription = PushSubscriptionFactory(user=user)

        url = reverse(
            "notifications_api:push-subscription-detail",
            args=[subscription.id],
        )
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PushSubscription.objects.filter(pk=subscription.pk).exists()

    def test_cannot_delete_other_user_subscription(self, authenticated_client):
        """Test that users cannot delete other users' subscriptions."""
        other_user = UserFactory()
        subscription = PushSubscriptionFactory(user=other_user)

        url = reverse(
            "notifications_api:push-subscription-detail",
            args=[subscription.id],
        )
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# Permission Tests
# =============================================================================


@pytest.mark.django_db
class TestNotificationPermissions:
    """Tests for notification permission checks."""

    def test_unauthenticated_access_denied(self, api_client):
        """Test that unauthenticated users are denied access."""
        endpoints = [
            reverse("notifications_api:notification-list"),
            reverse("notifications_api:template-list"),
            reverse("notifications_api:preference-list"),
            reverse("notifications_api:push-subscription-list"),
        ]

        for endpoint in endpoints:
            response = api_client.get(endpoint)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_regular_user_cannot_send_notifications(self, authenticated_client, user):
        """Test that regular users cannot send notifications."""
        url = reverse("notifications_api:notification-send")
        response = authenticated_client.post(
            url,
            {"user_id": user.id, "subject": "Test", "body": "Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_access_all_notifications(self, staff_client):
        """Test that staff can see all users' notifications."""
        user1 = UserFactory()
        user2 = UserFactory()
        NotificationFactory(user=user1)
        NotificationFactory(user=user2)

        url = reverse("notifications_api:notification-list")
        response = staff_client.get(url)

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        assert len(results) == 2


# =============================================================================
# Serializer Tests
# =============================================================================


@pytest.mark.django_db
class TestNotificationSerializer:
    """Tests for notification serializers."""

    def test_notification_list_serializer_fields(self, authenticated_client, user):
        """Test that list serializer returns correct fields."""
        NotificationFactory(user=user)

        url = reverse("notifications_api:notification-list")
        response = authenticated_client.get(url)

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        notification = results[0]

        expected_fields = [
            "id",
            "channel",
            "subject",
            "status",
            "priority",
            "action_url",
            "read_at",
            "created_at",
        ]
        for field in expected_fields:
            assert field in notification

    def test_notification_detail_serializer_fields(self, authenticated_client, user):
        """Test that detail serializer returns all fields."""
        notification = NotificationFactory(user=user)

        url = reverse(
            "notifications_api:notification-detail",
            args=[notification.id],
        )
        response = authenticated_client.get(url)

        expected_fields = [
            "id",
            "user",
            "template",
            "channel",
            "subject",
            "body",
            "status",
            "priority",
            "action_url",
            "action_text",
            "metadata",
            "sent_at",
            "delivered_at",
            "read_at",
            "created_at",
        ]
        for field in expected_fields:
            assert field in response.data


@pytest.mark.django_db
class TestTemplateSerializer:
    """Tests for template serializers."""

    def test_template_serializer_fields(self, admin_client):
        """Test that template serializer returns correct fields."""
        NotificationTemplateFactory()

        url = reverse("notifications_api:template-list")
        response = admin_client.get(url)

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        template = results[0]

        expected_fields = [
            "id",
            "name",
            "description",
            "subject",
            "body",
            "html_body",
            "channel",
            "is_active",
            "created_at",
            "updated_at",
        ]
        for field in expected_fields:
            assert field in template


@pytest.mark.django_db
class TestPreferenceSerializer:
    """Tests for preference serializers."""

    def test_preference_serializer_fields(self, authenticated_client, user):
        """Test that preference serializer returns correct fields."""
        UserNotificationPreferenceFactory(user=user)

        url = reverse("notifications_api:preference-list")
        response = authenticated_client.get(url)

        expected_fields = [
            "id",
            "email_enabled",
            "push_enabled",
            "sms_enabled",
            "in_app_enabled",
            "course_reminders",
            "assessment_results",
            "certificate_issued",
            "new_assignments",
            "deadline_reminders",
            "lesson_learned_updates",
            "quiet_hours_start",
            "quiet_hours_end",
            "updated_at",
        ]
        for field in expected_fields:
            assert field in response.data


@pytest.mark.django_db
class TestPushSubscriptionSerializer:
    """Tests for push subscription serializers."""

    def test_subscription_serializer_fields(self, authenticated_client, user):
        """Test that subscription serializer returns correct fields."""
        PushSubscriptionFactory(user=user)

        url = reverse("notifications_api:push-subscription-list")
        response = authenticated_client.get(url)

        results = response.data["results"] if isinstance(response.data, dict) else response.data
        subscription = results[0]

        expected_fields = [
            "id",
            "endpoint",
            "p256dh_key",
            "auth_key",
            "device_name",
            "device_type",
            "is_active",
            "created_at",
            "last_used_at",
        ]
        for field in expected_fields:
            assert field in subscription
