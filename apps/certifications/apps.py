from django.apps import AppConfig


class CertificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.certifications"
    verbose_name = "Certificaciones"

    def ready(self):
        # Connect signals (B1 will populate signals.py)
        from . import signals  # noqa: F401
