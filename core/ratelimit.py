"""Limitation de fréquence des traitements coûteux (chat, quiz, résumés).

Principe (« fenêtre fixe ») : pour chaque utilisateur et chaque action, un
compteur est stocké dans le cache de Django avec une durée de vie égale à la
fenêtre. Au-delà de la limite, la requête est refusée avec le code HTTP 429
(« Too Many Requests ») jusqu'à la fenêtre suivante.

Les limites se règlent dans settings.RATE_LIMITS : {"chat": (6, 60), ...}
= 6 requêtes par tranche de 60 secondes. Limite 0 = désactivé.

Limite connue : le cache par défaut (LocMemCache) est propre à un processus.
Avec un seul processus (waitress, multi-thread), c'est exact ; avec plusieurs
processus, il faudrait un cache partagé (base de données ou Redis).
"""

import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render


def _hit(scope, user_id):
    """Compte une requête ; retourne (autorisée, secondes avant la prochaine fenêtre)."""
    limit, window = settings.RATE_LIMITS.get(scope, (0, 60))
    if not limit:
        return True, 0
    now = time.time()
    bucket = int(now // window)
    key = f"ratelimit:{scope}:{user_id}:{bucket}"
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:  # clé expirée entre add et incr
        cache.set(key, 1, timeout=window)
        count = 1
    retry_after = int(window - (now % window)) + 1
    return count <= limit, retry_after


def rate_limit(scope, json_response=False):
    """Décorateur de vue : limite le nombre de requêtes d'un utilisateur pour `scope`.

    À placer sous @login_required (l'utilisateur est alors connu).
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method != "POST":  # afficher un formulaire ne coûte rien
                return view(request, *args, **kwargs)
            allowed, retry_after = _hit(scope, request.user.pk)
            if allowed:
                return view(request, *args, **kwargs)
            message = (
                "Trop de demandes en peu de temps. "
                f"Réessayez dans {retry_after} seconde(s)."
            )
            if json_response:
                response = JsonResponse({"error": message}, status=429)
            else:
                response = render(request, "429.html", {"message": message}, status=429)
            response["Retry-After"] = str(retry_after)
            return response

        return wrapper

    return decorator
