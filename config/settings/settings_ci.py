"""Settings de test rápido para el gate F3 self-verify (/multiagente, /modulo).

SQLite en memoria + hashers rápidos: la suite corre en segundos en vez de
minutos (sin esto, el gate cae al settings de producción — Postgres vía
Cloud SQL — y la creación de la BD de test viaja por red; medido en el
portafolio: 668 migraciones = >30 min vs 28 s). Las migraciones SIGUEN
corriendo (no usar MIGRATION_MODULES=None: CI sin migraciones dejó
data-migrations sin cobertura — gotcha documentado tersaSoft/KOMSA/carnes).

Rollout portafolio 2026-08-08. Este módulo NUNCA se usa en runtime de prod.
"""
import os

os.environ.setdefault('SECRET_KEY', 'ci-only-secret-key-no-prod')
os.environ.setdefault('DJANGO_SECRET_KEY', 'ci-only-secret-key-no-prod')
os.environ.setdefault('DEBUG', 'False')
os.environ.setdefault('ALLOWED_HOSTS', '*')

from .base import *  # noqa: F401,F403,E402

DEBUG = False
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Django >=4.2 usa STORAGES; en repos más viejos el dict extra es inofensivo.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
}
