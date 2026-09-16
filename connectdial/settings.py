import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ======================
# SECURITY & CORE
# ======================
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [
    '192.168.100.107',
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    '10.126.232.156',
    '192.168.100.108',
    '10.199.198.201',
    '10.199.198.22',
    'api.dataforgeprism.com',
    'api.connectdial.com',
    '16.16.95.218',          
]

AUTH_USER_MODEL = 'users.User'
SITE_ID = 1

GOOGLE_CLIENT_ID = os.getenv(
    'GOOGLE_CLIENT_ID',
    '597689072930-lf6o7j50lqv8ro2qc4lluq06gribo16h.apps.googleusercontent.com',
)
GOOGLE_ANDROID_CLIENT_ID = os.getenv(
    'GOOGLE_ANDROID_CLIENT_ID',
    '597689072930-67d9a06t10l30gi1rdtm5o0lr7sb2g06.apps.googleusercontent.com',
)
GOOGLE_IOS_CLIENT_ID = os.getenv('GOOGLE_IOS_CLIENT_ID', '')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ======================
# APPLICATION DEFINITION
# ======================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third Party
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',
    'corsheaders',
    'django_extensions',
    'storages',

    # Local apps
    'users',
    'leagues',
    'posts',
    'notifications',
    'search',
    'trending',
    'short_videos',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serves static files directly (added for /static fix)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'connectdial.urls'
WSGI_APPLICATION = 'connectdial.wsgi.application'

# ======================
# DATABASE
# ======================
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     'connectdial_db',  # Changed from 'db' to match standard database setups
        'USER':     'gilly',
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST':     os.getenv('DB_HOST', 'db'),
        'PORT':     os.getenv('DB_PORT', '5432'),
    }
}
# ======================
# STATIC & MEDIA — Firebase Storage / Google Cloud Storage
# ======================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
PUBLIC_API_BASE_URL = os.getenv('PUBLIC_API_BASE_URL', 'https://api.connectdial.com').rstrip('/')

# Firebase/GCS is the permanent media store. Keep the service-account JSON
# outside Git and outside the mobile application; mount it into web/Celery.
FIREBASE_CREDENTIALS_PATH = os.getenv(
    'FIREBASE_CREDENTIALS_PATH',
    str(BASE_DIR / 'firebase-service-account.json'),
)
GS_BUCKET_NAME = os.getenv(
    'GS_BUCKET_NAME',
    'agrieldo-bc336.firebasestorage.app',
)
FIREBASE_SIGNED_URL_TTL_SECONDS = int(
    os.getenv('FIREBASE_SIGNED_URL_TTL_SECONDS', '21600')
)

STORAGES = {
    "default": {
        "BACKEND": "connectdial.firebase_storage.FirebaseMediaStorage"
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Compatibility path for old app builds. New serializers return signed GCS
# URLs directly; /api/media/<key> redirects to a fresh signed URL.
MEDIA_URL = f"{PUBLIC_API_BASE_URL}/api/media/"

# ======================
# LEGACY MINIO — migration/rollback only
# ======================
# Do not use these settings for new uploads. They remain only so the
# migrate_to_firebase command can copy existing objects without deleting them.
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'connectdial-media')
AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL', 'http://minio:9000')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
# ======================
# TEMPLATES
# ======================
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

# ======================
# CORS & CSRF
# ======================
CORS_ALLOWED_ORIGINS = [
    'http://16.16.95.218',
    'https://16.16.95.218',
    'http://api.dataforgeprism.com',
    'https://api.dataforgeprism.com',
    'https://api.connectdial.com',
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    'http://16.16.95.218',
    'https://16.16.95.218',
    'http://api.dataforgeprism.com',
    'https://api.dataforgeprism.com',
    'https://api.connectdial.com',
]

# ======================
# AUTHENTICATION BACKENDS
# ======================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ======================
# ALLAUTH — headless / API mode
# ======================
ACCOUNT_EMAIL_VERIFICATION    = 'none'    
ACCOUNT_EMAIL_REQUIRED        = True
ACCOUNT_UNIQUE_EMAIL          = True
ACCOUNT_USERNAME_REQUIRED     = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'

SOCIALACCOUNT_AUTO_SIGNUP                       = True
SOCIALACCOUNT_EMAIL_REQUIRED                    = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION              = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': GOOGLE_CLIENT_ID,
            'secret':    os.getenv('GOOGLE_CLIENT_SECRET'),
            'key':       '',
        },
        'SCOPE':          ['profile', 'email'],
        'AUTH_PARAMS':    {'access_type': 'online'},
        'FETCH_USERINFO': True,
        'VERIFIED_EMAIL': True,
    }
}

# ======================
# REST FRAMEWORK
# ======================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS':        'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS':    'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon':           '60/min',
        'user':           '300/min',
        'login':          '10/min',
        'otp':            '5/min',
        'password_reset': '5/min',
    },
}

# ======================
# DJ-REST-AUTH
# ======================
REST_AUTH = {
    'USE_JWT':                   False,
    'TOKEN_MODEL':               'rest_framework.authtoken.models.Token',
    'OLD_PASSWORD_FIELD_ENABLED': True,
    'REGISTER_SERIALIZER':       'dj_rest_auth.registration.serializers.RegisterSerializer',
}

# ======================
# DRF SPECTACULAR
# ======================
SPECTACULAR_SETTINGS = {
    'TITLE':                'SportTribe API',
    'DESCRIPTION':          'SportTribe Backend API Documentation',
    'VERSION':              '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'COMPONENT_SPLIT_PATCH':   True,
}

# ======================
# EMAIL (Gmail SMTP)
# ======================
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT          = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS       = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@connectdial.com')

# ======================
# CELERY
# ======================
CELERY_BROKER_URL     = os.environ.get('CELERY_BROKER', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_BROKER', 'redis://redis:6379/0')
CELERY_TIMEZONE       = 'UTC'

CELERY_BEAT_SCHEDULE = {
    'trigger-bot-engagement-every-12h': {
        'task':     'posts.tasks.coordinate_bot_engagement',
        'schedule': crontab(hour='*/12'),
    },
    'check-unread-every-2-minutes': {
        'task': 'notifications.tasks.check_unread_notifications_periodic',
        'schedule': 120.0,  
    },
    'bot-social-expansion': {
        'task':     'posts.tasks.expand_bot_social_graph',
        'schedule': crontab(hour='*/8'),
        'args':     (15,),
    },
    'sync-premier-league': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=0, hour='*/4'),
        'args':     ('Premier League', 5),
    },
    'sync-nba': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=5, hour='*/4'),
        'args':     ('NBA', 6),
    },
    'sync-champions-league': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=10, hour='*/4'),
        'args':     ('Champions League', 5),
    },
    'sync-nfl': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=15, hour='*/4'),
        'args':     ('NFL', 6),
    },
    'sync-la-liga': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=20, hour='*/4'),
        'args':     ('La Liga', 4),
    },
    'sync-f1': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=25, hour='*/4'),
        'args':     ('F1', 4),
    },
    'sync-kenya-premier-league': {
        'task':     'posts.tasks.sync_bots_with_live_sports',
        'schedule': crontab(minute=30, hour='*/4'),
        'args':     ('Kenya Premier League', 3),
    },
    'post-premier-league-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=30, hour='*/8'),
        'args':     ('Premier League',),
    },
    'post-nba-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=35, hour='*/8'),
        'args':     ('NBA',),
    },
    'post-nfl-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=40, hour='*/8'),
        'args':     ('NFL',),
    },
    'post-champions-league-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=45, hour='*/8'),
        'args':     ('Champions League',),
    },
    'post-f1-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=50, hour='*/8'),
        'args':     ('F1',),
    },
    'post-kenya-premier-league-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=55, hour='*/8'),
        'args':     ('Kenya Premier League',),
    },
    'post-la-liga-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=0, hour='*/12'),
        'args':     ('La Liga',),
    },
    'post-serie-a-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=5, hour='*/12'),
        'args':     ('Serie A',),
    },
    'post-bundesliga-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=10, hour='*/12'),
        'args':     ('Bundesliga',),
    },
    'post-ligue-1-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=15, hour='*/12'),
        'args':     ('Ligue 1',),
    },
    'post-mlb-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=20, hour='*/12'),
        'args':     ('MLB',),
    },
    'post-nhl-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=25, hour='*/12'),
        'args':     ('NHL',),
    },
    'post-afcon-shorts': {
        'task':     'posts.tasks.fetch_and_post_youtube_shorts',
        'schedule': crontab(minute=30, hour='*/12'),
        'args':     ('Afcon',),
    },
}

# ======================
# EXTERNAL API KEYS
# ======================
GEMINI_API_KEY  = os.getenv('GEMINI_API_KEY')
NEWS_API_KEY    = os.getenv('NEWS_API_KEY')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
HIGHLIGHTLY_API_KEY = os.getenv("HIGHLIGHTLY_API_KEY")
HIGHLIGHTLY_SPORT   = os.getenv("HIGHLIGHTLY_SPORT", default="football")

# ======================
# OTP SETTINGS
# ======================
OTP_EXPIRY_SECONDS  = 300
OTP_MAX_ATTEMPTS    = 5
OTP_RESEND_COOLDOWN = 30

# ======================
# PROXY / AWS CONFIG
# ======================
TRUSTED_PROXY_COUNT     = 1
USE_X_FORWARDED_HOST    = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ======================
# APP NAME
# ======================
APP_NAME = 'SportTribe'

# ======================
# CACHES — Redis
# ======================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "connectdial",
    }
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 2147483648
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]