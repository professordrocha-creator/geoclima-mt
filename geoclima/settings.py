# geoclima/settings.py
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-geoclima-mt-secret-key-2026')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis', # Motor espacial PostGIS
    'rest_framework',

    # Nossos Apps do GeoClima MT
    'core',
    'accounts',
    'farms',
    'stations',
    'climate',
    'spi',
    'alerts',
    'dashboard',
    'maps',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'geoclima.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'geoclima.wsgi.application'
ASGI_APPLICATION = 'geoclima.asgi.application'

# Database
# Configuração apontando para o backend espacial do PostGIS
DB_NAME = os.environ.get('DB_NAME', 'geoclima')
DB_USER = os.environ.get('DB_USER', 'geoclima_user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'geoclima_password')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Cuiaba'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Cache do Django — backend Redis nativo (disponível desde o Django 4.0,
# sem lib nova: usa o mesmo pacote `redis` já instalado pro Celery). Sem
# isso, o padrão é LocMemCache (por processo) — não é compartilhado entre
# múltiplos workers do Gunicorn em produção, o que quebra qualquer lock/
# debounce baseado em cache (ver stations/signals.py e docs/DECISOES.md).
# Banco Redis separado do usado pelo Celery (db 1, não db 0) — só pra não
# misturar chave de cache de aplicação com dado operacional do broker.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/1'),
    }
}

# Google Earth Engine (Etapa 3 — integração CHIRPS). Autenticação via
# conta de serviço; chave montada em secrets/gee-key.json (não
# versionada — ver .gitignore) e apontada pela variável abaixo.
GEE_PROJECT_ID = os.environ.get('GEE_PROJECT_ID')
GEE_SERVICE_ACCOUNT_KEY_PATH = os.environ.get('GEE_SERVICE_ACCOUNT_KEY_PATH')

# Autenticação (Etapa 4). LOGIN_URL é para onde @login_required manda
# quem não está logado (com ?next= de volta pra página pedida).
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:painel'
LOGOUT_REDIRECT_URL = 'home'

# E-mail (recuperação de senha). Backend "console" em desenvolvimento —
# o e-mail não é enviado de verdade, só impresso no log do container
# `web` (docker compose logs web). Trocar para um backend SMTP real
# antes de qualquer ambiente de produção/beta público.
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'naoresponda@geoclima.mt')
