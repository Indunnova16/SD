"""
Minimal dev settings using SQLite (no PostgreSQL required).
Usage: python manage.py runserver --settings=config.settings.dev
"""

from .base import *  # noqa: F403, F401

DEBUG = True

ALLOWED_HOSTS = ["*"]

# SQLite for quick local dev
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Remove postgres-only app
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django.contrib.postgres"]  # noqa: F405

# Disable apps that need extra infra
INSTALLED_APPS = [  # noqa: F811
    app
    for app in INSTALLED_APPS
    if app
    not in ("django_celery_beat", "django_celery_results", "channels", "channels_redis", "axes")
]

# Simplified middleware — remove axes (needs cache) and CSP
MIDDLEWARE = [  # noqa: F405
    m
    for m in MIDDLEWARE  # noqa: F405
    if m not in ("axes.middleware.AxesMiddleware", "csp.middleware.CSPMiddleware")
]

# Auth backends without axes (but keep document number login)
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrDocumentBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Disable secure cookies
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Console email
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Local memory cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Celery in eager mode (sync, no broker needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Static files
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Disable axes
AXES_ENABLED = False

CORS_ALLOW_ALL_ORIGINS = True
