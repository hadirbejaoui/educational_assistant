from django.conf import settings

from ..errors import SummaryProviderError


def get_provider():
    """Choisit le fournisseur selon SUMMARY_PROVIDER dans .env."""
    name = settings.SUMMARY_PROVIDER
    if name == "extractive":
        from .extractive import ExtractiveProvider

        return ExtractiveProvider()
    if name == "huggingface":
        from .huggingface import HuggingFaceProvider

        return HuggingFaceProvider(settings.SUMMARY_MODEL_NAME)
    raise SummaryProviderError(f"Fournisseur de résumé inconnu : « {name} ».")