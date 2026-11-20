from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Éléments transversaux : tableau de bord, pagination, pages d'erreur."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Tronc commun"
