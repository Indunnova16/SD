"""
ViewSets for notifications API.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User
from apps.notifications.models import (
    Notification,
    NotificationTemplate,
    PushSubscription,
    UserNotificationPreference,
)

from .permissions import IsAdministrador
from .serializers import (
    MarkReadSerializer,
    NotificationCreateSerializer,
    NotificationListSerializer,
    NotificationSerializer,
    NotificationTemplateSerializer,
    PushSubscriptionSerializer,
    UserNotificationPreferenceSerializer,
)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing notification templates.

    Superficie "Sistema" (config admin) — issue #58 (A10): CRUD de plantillas
    exige `rol == ADMINISTRADOR` (antes `IsAuthenticated`, gap real de API
    abierto a cualquier autenticado). Ver `apps/notifications/api/permissions.py`.
    """

    permission_classes = [IsAdministrador]
    serializer_class = NotificationTemplateSerializer

    def get_queryset(self):
        queryset = NotificationTemplate.objects.all()

        # Filter by channel
        channel = self.request.query_params.get("channel")
        if channel:
            queryset = queryset.filter(channel=channel)

        # Filter by active
        is_active = self.request.query_params.get("active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.order_by("name")


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing notifications."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.select_related("template")

        # Non-staff users see only their own notifications
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        else:
            # Staff can filter by user
            user_id = self.request.query_params.get("user")
            if user_id:
                queryset = queryset.filter(user_id=user_id)

        # Filter by status
        notification_status = self.request.query_params.get("status")
        if notification_status:
            queryset = queryset.filter(status=notification_status)

        # Filter by channel
        channel = self.request.query_params.get("channel")
        if channel:
            queryset = queryset.filter(channel=channel)

        # Filter by unread
        unread = self.request.query_params.get("unread")
        if unread and unread.lower() == "true":
            queryset = queryset.filter(read_at__isnull=True)

        # Filter by priority
        priority = self.request.query_params.get("priority")
        if priority:
            queryset = queryset.filter(priority=priority)

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return NotificationListSerializer
        return NotificationSerializer

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = Notification.objects.filter(
            user=request.user,
            read_at__isnull=True,
        ).count()
        return Response({"count": count})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()

        if notification.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "No autorizado"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.status = Notification.Status.READ
            notification.save()

        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        updated = Notification.objects.filter(
            user=request.user,
            read_at__isnull=True,
        ).update(
            read_at=timezone.now(),
            status=Notification.Status.READ,
        )
        return Response({"updated": updated})

    @action(detail=False, methods=["post"])
    def mark_selected_read(self, request):
        """Mark selected notifications as read."""
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("mark_all"):
            updated = Notification.objects.filter(
                user=request.user,
                read_at__isnull=True,
            ).update(
                read_at=timezone.now(),
                status=Notification.Status.READ,
            )
        else:
            notification_ids = serializer.validated_data.get("notification_ids", [])
            updated = Notification.objects.filter(
                user=request.user,
                id__in=notification_ids,
                read_at__isnull=True,
            ).update(
                read_at=timezone.now(),
                status=Notification.Status.READ,
            )

        return Response({"updated": updated})

    @action(detail=False, methods=["post"])
    def send(self, request):
        """Send a notification (staff only)."""
        if not request.user.is_staff:
            return Response(
                {"error": "Solo personal autorizado puede enviar notificaciones"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = NotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Get target users
        user_ids = data.get("user_ids", [])
        user_id = data.get("user_id")
        if user_id:
            user_ids.append(user_id)

        if not user_ids:
            return Response(
                {"error": "Debe especificar al menos un usuario"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = User.objects.filter(id__in=user_ids, is_active=True)

        # Get template if specified
        template = None
        if data.get("template_id"):
            template = get_object_or_404(NotificationTemplate, pk=data["template_id"])

        # Create notifications
        notifications = []
        for user in users:
            notification = Notification.objects.create(
                user=user,
                template=template,
                channel=data.get("channel", template.channel if template else "in_app"),
                subject=data["subject"],
                body=data["body"],
                priority=data.get("priority", Notification.Priority.NORMAL),
                action_url=data.get("action_url", ""),
                action_text=data.get("action_text", ""),
                metadata=data.get("metadata", {}),
                status=Notification.Status.SENT,
                sent_at=timezone.now(),
            )
            notifications.append(notification)

        return Response(
            {"created": len(notifications)},
            status=status.HTTP_201_CREATED,
        )


class UserNotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user notification preferences."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserNotificationPreferenceSerializer

    def get_queryset(self):
        return UserNotificationPreference.objects.filter(user=self.request.user)

    def get_object(self):
        """Get or create preferences for current user."""
        obj, created = UserNotificationPreference.objects.get_or_create(user=self.request.user)
        return obj

    def list(self, request, *args, **kwargs):
        """Return the user's preferences."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["put", "patch"])
    def update_preferences(self, request):
        """Update user's notification preferences."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PushSubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing push subscriptions."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PushSubscriptionSerializer

    def get_queryset(self):
        return PushSubscription.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        """Subscribe to push notifications."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check for existing subscription with same endpoint
        endpoint = serializer.validated_data["endpoint"]
        existing = PushSubscription.objects.filter(
            user=request.user,
            endpoint=endpoint,
        ).first()

        if existing:
            # Update existing
            for key, value in serializer.validated_data.items():
                setattr(existing, key, value)
            existing.is_active = True
            existing.save()
            return Response(PushSubscriptionSerializer(existing).data)

        # Create new
        instance = serializer.save(user=request.user)
        return Response(
            PushSubscriptionSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def unsubscribe(self, request):
        """Unsubscribe from push notifications."""
        endpoint = request.data.get("endpoint")
        if not endpoint:
            return Response(
                {"error": "Endpoint requerido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = PushSubscription.objects.filter(
            user=request.user,
            endpoint=endpoint,
        ).update(is_active=False)

        return Response({"unsubscribed": updated > 0})
