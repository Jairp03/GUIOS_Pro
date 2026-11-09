"""Configuración de GUIOS PRO (Django + Supabase/PostgreSQL)."""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-solo-para-desarrollo-cambiar-en-produccion")
DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "guios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "guios.context.globales",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos -------------------------------------------------------
# Con DATABASE_URL (cadena de conexión de Supabase) usa PostgreSQL.
# Sin DATABASE_URL usa SQLite local, para poder probar sin internet.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    _local = any(h in DATABASE_URL for h in ("@localhost", "@127.0.0.1", "@/", "host=/"))
    # conn_max_age=0 porque se usa un pool de conexiones (psycopg 3): las conexiones se reutilizan
    # entre solicitudes y no se paga el apretón de manos TLS contra Supabase en cada página.
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0, ssl_require=not _local)}
    DATABASES["default"].setdefault("OPTIONS", {})
    if os.getenv("DB_POOL", "True").lower() in ("1", "true", "yes"):
        DATABASES["default"]["OPTIONS"]["pool"] = {"min_size": 1, "max_size": int(os.getenv("DB_POOL_MAX", "3")), "timeout": 20}
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
    if ":6543" in DATABASE_URL:  # pooler en modo transacción de Supabase
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
        DATABASES["default"]["OPTIONS"]["prepare_threshold"] = None  # el pooler de transacción no admite sentencias preparadas
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# Sesiones firmadas en una cookie: evita una consulta a la base de datos por cada página.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_AGE = 60 * 60 * 12
AUTHENTICATION_BACKENDS = ["guios.backends.UsuarioConPerfil"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "guios"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# --- IA opcional (propuesta de importancia sugerida con un modelo de lenguaje)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
