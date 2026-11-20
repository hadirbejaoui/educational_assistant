import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Nos applications
    "core",
    "accounts",
    "courses",
    "summaries",
    "quizzes",
    "chatbot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Pages privées
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# Documents et découpage (phases 3 et 4)
MAX_UPLOAD_SIZE_MB = 20
ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".txt"]
CHUNK_SIZE = 800        # caractères par chunk
CHUNK_OVERLAP = 100     # chevauchement entre chunks

# Résumés (phase 5)
SUMMARY_PROVIDER = os.getenv("SUMMARY_PROVIDER", "extractive")
SUMMARY_MODEL_NAME = os.getenv("SUMMARY_MODEL_NAME", "csebuetnlp/mT5_multilingual_XLSum")
SUMMARY_SECTION_CHARS = 1800   # taille d'une section envoyée au modèle
SUMMARY_MAX_SECTIONS = 80      # garde-fou pour les modèles lents

# LLM et quiz (phase 6)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "90"))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "8192"))
QUIZ_MAX_QUESTIONS = 20

# Embeddings et recherche (phase 7)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 16
EMBEDDING_QUERY_PREFIX = "query: "      # propre à e5 ; vide pour d'autres modèles
EMBEDDING_PASSAGE_PREFIX = "passage: "
RETRIEVAL_TOP_K = 8
# Recherche hybride (vectorielle + BM25, fusion RRF).
# Poids de la liste BM25 dans la fusion (la liste vectorielle a le poids 1) :
# 0 = ordre vectoriel pur ; 1 = RRF standard, les deux méthodes à égalité.
RETRIEVAL_LEXICAL_WEIGHT = float(os.getenv("RETRIEVAL_LEXICAL_WEIGHT", "1"))
# Nombre de candidats de chaque méthode pris en compte par la fusion (même profondeur)
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "50"))

# Chatbot RAG (phase 8)
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.83"))
RAG_SCORE_WINDOW = float(os.getenv("RAG_SCORE_WINDOW", "0.08"))
RAG_MAX_CONTEXT_CHARS = 6500
RAG_HISTORY_MESSAGES = 4
RAG_MAX_QUESTION_CHARS = 1000

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "chatbot": {"handlers": ["console"], "level": "INFO"},
        "llm": {"handlers": ["console"], "level": "INFO"},
    },
}

# Sécurité et limites (phase 10)
# Traitements d'IA coûteux : (nombre de requêtes, fenêtre en secondes) par utilisateur ; 0 = pas de limite
RATE_LIMITS = {
    "chat": (int(os.getenv("RATE_LIMIT_CHAT", "6")), 60),
    "quiz": (int(os.getenv("RATE_LIMIT_QUIZ", "10")), 3600),
    "summary": (int(os.getenv("RATE_LIMIT_SUMMARY", "10")), 3600),
}
# Taille maximale d'une requête hors fichiers (formulaires) ; les fichiers sont limités
# par MAX_UPLOAD_SIZE_MB dans courses/validators.py
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # le JavaScript du chat lit le jeton CSRF dans le formulaire, pas dans le cookie
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

