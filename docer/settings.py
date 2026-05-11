"""Django settings for docer.

Tuned for local dev with SQLite. Production deployment is out of scope for v1.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-secret-key-change-me-in-production",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "huey.contrib.djhuey",
    "apps.accounts",
    "apps.files",
    "apps.scanners",
    "apps.scans",
    "apps.extraction",
    "apps.web",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.AccountResolverMiddleware",
]

ROOT_URLCONF = "docer.urls"

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
                "apps.web.context.brand",
            ],
        },
    },
]

WSGI_APPLICATION = "docer.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / os.environ.get("DOCER_SQLITE_PATH", "db.sqlite3"),
    }
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "auth:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / os.environ.get("DOCER_MEDIA_ROOT", "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Docer-specific settings ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DOCER_DEFAULT_MODEL = os.environ.get("DOCER_DEFAULT_MODEL", "gemma4:31b")
DOCER_OLLAMA_TIMEOUT = float(os.environ.get("DOCER_OLLAMA_TIMEOUT", "600"))
DOCER_PDF_RENDER_DPI = int(os.environ.get("DOCER_PDF_RENDER_DPI", "180"))

# --- Huey ---
# In tests we run Huey immediately (synchronous) so we don't need a worker process.
HUEY_IMMEDIATE = os.environ.get("DOCER_HUEY_IMMEDIATE", "0") == "1"
HUEY = {
    "huey_class": "huey.SqliteHuey",
    "name": "docer",
    "filename": str(BASE_DIR / "huey.sqlite3"),
    "immediate": HUEY_IMMEDIATE,
    "consumer": {
        "workers": 1,
        "worker_type": "thread",
    },
}

# REST framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.auth.ApiKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}
