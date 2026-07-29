"""
Django settings for production environment.
"""

from .base import *  # noqa: F403, F401
from .csp import CSP_DIRECTIVES

DEBUG = False

# Security settings - strict for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Content Security Policy (SD#76).
# Antes esto eran variables planas CSP_DEFAULT_SRC / CSP_SCRIPT_SRC / ... que
# django-csp 4.0 (la version instalada) NO lee: quedaron en
# csp.checks.OUTDATED_SETTINGS, que solo alimenta el check csp.E001. Y como
# "csp" tampoco estaba en INSTALLED_APPS, ese check ni siquiera se registraba:
# cero header y cero aviso. Ahora la app esta instalada (ver base.py), asi que
# reintroducir una CSP_* plana rompe `manage.py check` en vez de ignorarse.
# La politica real vive en config/settings/csp.py y la comparte cloudrun.py,
# que es el settings que efectivamente corre en produccion (deploy.yml).
CSP_ENFORCE = config("CSP_ENFORCE", default=False, cast=bool)  # noqa: F405
if CSP_ENFORCE:
    CONTENT_SECURITY_POLICY = {"DIRECTIVES": CSP_DIRECTIVES}
else:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = {"DIRECTIVES": CSP_DIRECTIVES}

# Storage backends (Django 5.1+ STORAGES)
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# GCP Cloud Storage settings
GS_BUCKET_NAME = config("GS_BUCKET_NAME", default="sd-lms-media")  # noqa: F405
GS_DEFAULT_ACL = "projectPrivate"
GS_QUERYSTRING_AUTH = True
GS_FILE_OVERWRITE = False

# Email via SendGrid
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "apikey"
EMAIL_HOST_PASSWORD = config("SENDGRID_API_KEY", default="")  # noqa: F405

# Sentry for error tracking
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

SENTRY_DSN = config("SENTRY_DSN", default="")  # noqa: F405

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        environment="production",
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# Logging configuration for production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Cache with Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),  # noqa: F405
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Session with Redis
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Django cachalot for query caching
INSTALLED_APPS += ["cachalot"]  # noqa: F405
CACHALOT_ENABLED = True
