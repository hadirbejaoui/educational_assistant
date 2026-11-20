"""En-têtes de sécurité complémentaires à ceux de Django.

Django (SecurityMiddleware, XFrameOptionsMiddleware) envoie déjà :
X-Content-Type-Options: nosniff, Referrer-Policy, X-Frame-Options: DENY,
Cross-Origin-Opener-Policy. Django 5.2 n'a pas de Content-Security-Policy
intégrée : ce middleware l'ajoute.

La CSP est stricte car l'interface n'utilise aucun script ni style inline et
aucune ressource externe : tout vient de 'self'. Seule exception : img-src
autorise data: pour le chevron SVG des listes déroulantes (components.css).
Conséquence utile : si un texte de cours ou une réponse du modèle contenait du
HTML qui échappait par erreur à l'échappement, le navigateur refuserait
d'exécuter le script injecté.
"""

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
