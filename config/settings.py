import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-development-key-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [v.strip() for v in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if v.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "rest_framework_simplejwt", "drf_spectacular", "accounts", "factories", "assets", "maintenance", "api", "dashboard",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DB_ENGINE = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")
DATABASES = {"default": {"ENGINE": DB_ENGINE, "NAME": os.getenv("DB_NAME", BASE_DIR / "db.sqlite3")}}
if DB_ENGINE != "django.db.backends.sqlite3":
    DATABASES["default"].update(USER=os.getenv("DB_USER", ""), PASSWORD=os.getenv("DB_PASSWORD", ""), HOST=os.getenv("DB_HOST", "localhost"), PORT=os.getenv("DB_PORT", "5432"))
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ar"; TIME_ZONE = "Africa/Cairo"; USE_I18N = True; USE_TZ = True
STATIC_URL = "static/"; STATIC_ROOT = BASE_DIR / "staticfiles"; STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"; AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"; LOGIN_REDIRECT_URL = "dashboard:home"; LOGOUT_REDIRECT_URL = "login"
CORS_ALLOWED_ORIGINS = [v.strip() for v in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if v.strip()]
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"], "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"], "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema", "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination", "PAGE_SIZE": 25, "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"], "DEFAULT_THROTTLE_RATES": {"anon": os.getenv("LOGIN_THROTTLE", "10/minute")}, "EXCEPTION_HANDLER": "api.exceptions.safe_exception_handler"}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "30"))), "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))), "ROTATE_REFRESH_TOKENS": True}
SPECTACULAR_SETTINGS = {"TITLE": "نظام إدارة الصيانة", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
SESSION_COOKIE_SECURE = not DEBUG; CSRF_COOKIE_SECURE = not DEBUG; SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
LOGGING = {"version": 1, "disable_existing_loggers": False, "formatters": {"standard": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}}, "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}}, "loggers": {"maintenance": {"handlers": ["console"], "level": "INFO", "propagate": False}, "api": {"handlers": ["console"], "level": "INFO", "propagate": False}}}
