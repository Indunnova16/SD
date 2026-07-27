"""Feedback app configuration."""

from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    """Configuration for feedback app (portal público de tickets)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.feedback"
    verbose_name = "Portal de Feedback"
