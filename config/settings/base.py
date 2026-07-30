"""
Django base settings for SD LMS project.

This file contains settings common to all environments.
For environment-specific settings, see local.py, staging.py, production.py
"""

from pathlib import Path

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "axes",
    "allauth",
    "allauth.account",
    "crispy_forms",
    "crispy_tailwind",
    "widget_tweaks",
    "django_htmx",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.courses",
    "apps.learning_paths",
    "apps.assessments",
    "apps.certifications",
    "apps.lessons_learned",
    "apps.preop_talks",
    "apps.notifications",
    "apps.sync",
    "apps.reports",
    "apps.integrations",
    "apps.gamification",
    "apps.occupational_profiles",
    "apps.inspections",
    "apps.feedback",
    "pagos",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "apps.core.middleware.SessionInactivityMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pagos.context_processors.alertas_pago",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="sdlms"),
        "USER": config("DB_USER", default="sdlms"),
        "PASSWORD": config("DB_PASSWORD", default="sdlms"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.EmailOrDocumentBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Django Allauth settings (updated for v0.63+)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# Internationalization
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
    }
}

# Session configuration
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = (
    2592000  # 30 days (increased from 24 hours to prevent session loss when creating courses)
)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session on every request to prevent silent expiry

# Inactivity timeout (seconds) — logout after 20 minutes of no activity for regular users
# NOTE: Administrators (is_staff=True) have infinite session timeout
SESSION_INACTIVITY_TIMEOUT = 20 * 60  # 20 minutes (for regular workers/users)

# CSRF configuration
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://127.0.0.1:8000",
    cast=Csv(),
)

# Celery Configuration
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# JWT Configuration
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# DRF Spectacular (OpenAPI) configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "SD LMS API",
    "DESCRIPTION": "API para el Sistema de Gestión de Capacitaciones de S.D. S.A.S.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
}

# Django Axes (brute force protection)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_LOCKOUT_TEMPLATE = "accounts/lockout.html"
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "username"
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]

# CORS Configuration
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:8000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "filters": ["require_debug_true"],
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
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
            "handlers": ["mail_admins", "console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Email configuration (override in production)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@sd-lms.com")

# Portal público de feedback/tickets (apps.feedback) — sincronización con GitHub
GITHUB_FEEDBACK_TOKEN = config("GITHUB_FEEDBACK_TOKEN", default="")
GITHUB_FEEDBACK_REPO = config("GITHUB_FEEDBACK_REPO", default="Indunnova16/SD")
FEEDBACK_MAX_ATTACHMENTS = config("FEEDBACK_MAX_ATTACHMENTS", default=10, cast=int)
# 30 MB: desde #71 ronda 2 el portal acepta audio/video grabados desde el
# navegador, que pesan mucho más que una captura de pantalla. El techo real
# no es este número sino el límite de request de Cloud Run (32 MiB), así que
# subirlo más no serviría.
FEEDBACK_MAX_ATTACHMENT_BYTES = config(
    "FEEDBACK_MAX_ATTACHMENT_BYTES", default=30 * 1024 * 1024, cast=int
)

# Portal de pagos (apps pagos) -- WOMPI + Alegra, issue #85 sub-item A5.
# CRITICO: TODAS las config() de este bloque llevan default seguro
# (default=""/0/True) -- Sprint B (los 6 GCP Secrets reales de WOMPI/Alegra)
# esta bloqueado hoy, y este sub-item se deploya ANTES de que existan. Sin
# default, UndefinedValueError tumbaria el arranque de TODO el repo (no solo
# /pagos/) apenas Django intente importar settings.
WOMPI_PUBLIC_KEY = config("WOMPI_PUBLIC_KEY", default="")
WOMPI_PRIVATE_KEY = config("WOMPI_PRIVATE_KEY", default="")
WOMPI_EVENTS_KEY = config("WOMPI_EVENTS_KEY", default="")
WOMPI_INTEGRITY_KEY = config("WOMPI_INTEGRITY_KEY", default="")
WOMPI_SANDBOX = config("WOMPI_SANDBOX", default=True, cast=bool)
WOMPI_REFERENCE_PREFIX = config("WOMPI_REFERENCE_PREFIX", default="SD")

ALEGRA_EMAIL = config("ALEGRA_EMAIL", default="")
ALEGRA_API_TOKEN = config("ALEGRA_API_TOKEN", default="")
ALEGRA_API_URL = config("ALEGRA_API_URL", default="https://api.alegra.com/api/v1")
ALEGRA_NUMBER_TEMPLATE_ID = config("ALEGRA_NUMBER_TEMPLATE_ID", default="")
ALEGRA_ITEM_ID = config("ALEGRA_ITEM_ID", default="")
ALEGRA_BANK_ACCOUNT_ID = config("ALEGRA_BANK_ACCOUNT_ID", default="")

# Plan de servicio -- valores placeholder seguros. El precio REAL de la
# propuesta comercial se provisiona en Sprint B1 (bloqueado, HITL: escribe
# BD prod). NO usar este default para crear el PlanServicio en produccion.
PAGOS_PLAN_NAME = config("PAGOS_PLAN_NAME", default="Plan SaaS")
PAGOS_PLAN_PRICE = config("PAGOS_PLAN_PRICE", default=150000, cast=int)
PAGOS_PLAN_DESCRIPTION = config(
    "PAGOS_PLAN_DESCRIPTION", default="Plataforma SaaS + Hosting + Soporte"
)
