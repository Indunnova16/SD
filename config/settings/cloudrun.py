"""
Django settings for Google Cloud Run environment.
"""

from decouple import config

from .base import *  # noqa: F403, F401

DEBUG = False

# Security settings for Cloud Run (behind load balancer)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Cloud Run handles SSL termination at the load balancer level.
# Django should NOT redirect HTTP->HTTPS because Cloud Run's internal
# health checks use HTTP without X-Forwarded-Proto header, causing
# redirect loops that prevent the container from starting.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS settings (tells browsers to always use HTTPS)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Other security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Storage backends (Django 5.1+ uses STORAGES instead of deprecated
# DEFAULT_FILE_STORAGE / STATICFILES_STORAGE)
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# GCP Cloud Storage settings
GS_BUCKET_NAME = config("GS_BUCKET_NAME", default="sd-lms-media")
GS_DEFAULT_ACL = "publicRead"
GS_QUERYSTRING_AUTH = False
GS_FILE_OVERWRITE = False

# Database - Cloud SQL via Unix socket
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="sd_lms"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config(
            "DB_HOST", default="/cloudsql/appsindunnova:us-central1:postgres-consolidated"
        ),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# Cache - Local memory (sin Redis por ahora)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Session using database (sin Redis por ahora)
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Disable Celery for now (async tasks disabled)
# Use memory broker to avoid Redis connection attempts on startup
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Logging for Cloud Run
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Axes - reduce lockout for cloud environment
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 10
