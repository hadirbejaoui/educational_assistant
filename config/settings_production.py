"""Réglages de production.

Utilisation : DJANGO_SETTINGS_MODULE=config.settings_production
(variable d'environnement, ou ligne du fichier .env).

Ce fichier part des réglages communs (config/settings.py) et ne change que ce
qui diffère en production : pas de DEBUG, hôtes autorisés obligatoires, clé
secrète vérifiée, cookies sécurisés, HTTPS (si activé), fichiers statiques
versionnés, journaux dans un fichier.
"""

import importlib.util
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR, MIDDLEWARE, SECRET_KEY

DEBUG = False

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS doit être renseigné en production.")

if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY trop faible. Générez-en une avec : "
        "python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

# --- HTTPS -------------------------------------------------------------------------
# DJANGO_HTTPS=True quand le site est servi en HTTPS (certificat, reverse proxy).
# Pour une démonstration sur le réseau local en HTTP, laisser False : les cookies
# « Secure » ne seraient sinon jamais envoyés et la connexion serait impossible.
HTTPS = os.getenv("DJANGO_HTTPS", "False") == "True"
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
SECURE_SSL_REDIRECT = HTTPS
# HSTS : le navigateur refusera le HTTP pendant cette durée. Commencer petit (1 h).
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600")) if HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Choix volontaires : étendre HSTS aux sous-domaines ou demander le préchargement dans les
# navigateurs est quasi irréversible (des mois). Inadapté à un projet universitaire.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
if os.getenv("DJANGO_BEHIND_PROXY", "False") == "True":
    # Le reverse proxy (nginx, Caddy...) termine le HTTPS et transmet ce en-tête
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 heures
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# --- Fichiers statiques ---------------------------------------------------------------
# collectstatic copie static/ dans STATIC_ROOT en ajoutant une empreinte au nom
# (style.4f2a9c.css) : un fichier modifié a un nouveau nom, donc aucun cache périmé.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
if importlib.util.find_spec("whitenoise"):
    # WhiteNoise sert les fichiers statiques depuis Django (utile avec waitress, sans nginx)
    MIDDLEWARE = list(MIDDLEWARE)
    MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
                      "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- Journalisation -----------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name} : {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 5 * 1024 * 1024,   # 5 Mo par fichier
            "backupCount": 5,              # 5 anciens fichiers conservés
            "encoding": "utf-8",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        "chatbot": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "llm": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "quizzes": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}
