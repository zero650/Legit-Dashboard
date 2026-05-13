from pathlib import Path
import os
import socket

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes", "on"}


def default_allowed_hosts():
    hosts = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "192.168.20.12",
        "mac",
    }
    if DEBUG:
        hosts.add("*")

    try:
        hostname = socket.gethostname().strip()
    except OSError:
        hostname = ""

    if hostname:
        hosts.add(hostname)
        hosts.add(f"{hostname}.local")

    return ",".join(sorted(hosts))


def configured_allowed_hosts():
    hosts = {
        host.strip()
        for host in default_allowed_hosts().split(",")
        if host.strip()
    }

    extra_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
    hosts.update(host.strip() for host in extra_hosts.split(",") if host.strip())

    return sorted(hosts)


def configured_csrf_trusted_origins():
    origins = {
        origin.strip()
        for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
        if origin.strip()
    }

    if DEBUG:
        origins.update(
            {
                "http://localhost",
                "http://127.0.0.1",
                "https://localhost",
                "https://127.0.0.1",
            }
        )

    return sorted(origins)


ALLOWED_HOSTS = configured_allowed_hosts()
CSRF_TRUSTED_ORIGINS = configured_csrf_trusted_origins()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "staff_users",
    "auth_management",
    "work_tasks",
    "trips",
    "crm",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "legit_dashboard.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "legit_dashboard.wsgi.application"

if os.getenv("DJANGO_DATABASE", "postgres").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "legit_dashboard"),
            "USER": os.getenv("POSTGRES_USER", "legit"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "legit"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Denver"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "False").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "False").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "False").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "staff_users.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "trip_dashboard"
LOGOUT_REDIRECT_URL = "login"
