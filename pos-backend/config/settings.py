"""
Django settings for config project.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'core',
    'tenants',
    'audit',
    'sales',
    'catalog',
    'customers',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# Instancia única de PostgreSQL compartida entre todos los tenants
# (aislamiento a nivel de aplicación vía TenantScopedQuerySet, no schema-per-tenant).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Custom user: login por email, no username (ver documentacion/decisiones_post_auditoria.md #5).
AUTH_USER_MODEL = 'tenants.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

# Local dev usa filesystem storage. En producción esto se cambia a Azure
# Blob vía django-storages (ver documentacion/brief_infraestructura_carlos.md
# §3) — es un cambio de settings, no de modelo (catalog.Product.image ya
# genera el prefijo por tenant que ese backend espera).
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Correo transaccional (punto 6: ticket por correo; punto 7: resumen diario
# de stock bajo) — sin proveedor decidido todavía (SendGrid, Azure
# Communication Services, o cualquier SMTP real, ver
# documentacion/brief_infraestructura_carlos.md). Sin EMAIL_HOST configurado
# cae al backend de consola de Django (imprime el correo en logs en vez de
# enviarlo) — así dev funciona sin credenciales reales desde el día 1.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend' if not config('EMAIL_HOST', default='') else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@arkdev-pos.local')


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'EXCEPTION_HANDLER': 'core.exceptions.api_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    # Separado de SECRET_KEY a propósito: brief_infraestructura_carlos.md §3
    # ya lo nombra como su propio secret en Key Vault (rotar uno sin afectar
    # el otro). Si no se define, cae al default de SimpleJWT (SECRET_KEY) —
    # así no rompe entornos que todavía no lo configuraron.
    'SIGNING_KEY': config('JWT_SIGNING_KEY', default=SECRET_KEY),
}

# Vida del token de autorización de supervisor (PIN/reautenticación para
# can_authorize_exceptions, punto 6 del orden de construcción) — corto a
# propósito: es para autorizar una acción puntual, no una sesión.
SUPERVISOR_AUTHORIZATION_TTL_MINUTES = config('SUPERVISOR_AUTHORIZATION_TTL_MINUTES', default=5, cast=int)

# El frontend (Vite) corre en otro puerto durante desarrollo — sin esto el
# navegador bloquea las llamadas a la API por CORS. Puertos default de
# `vite dev` (5173) y `vite preview` (4173) habilitados de fábrica, más
# 5174/5175 (Vite cae ahí si 5173 ya está ocupado por otro proyecto en la
# misma máquina — pasó en desarrollo). En producción el frontend se sirve
# desde Azure Static Web App, se agrega ese origin real vía
# CORS_ALLOWED_ORIGINS cuando exista.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default=(
        'http://localhost:5173,http://127.0.0.1:5173,'
        'http://localhost:5174,http://127.0.0.1:5174,'
        'http://localhost:5175,http://127.0.0.1:5175,'
        'http://localhost:4173,http://127.0.0.1:4173'
    ),
    cast=Csv(),
)
