from django.conf import settings

from .base import BaseLLMClient, LLMError

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "ollama": "qwen3:4b"}


def get_llm_client():
    """Choisit le fournisseur selon LLM_PROVIDER dans .env."""
    provider = settings.LLM_PROVIDER
    if not provider:
        raise LLMError("Aucun LLM configuré. Renseignez LLM_PROVIDER dans .env.")

    # Ollama tourne en local : aucune clé n'est nécessaire
    if provider != "ollama" and not settings.LLM_API_KEY:
        raise LLMError("La clé API du LLM (LLM_API_KEY) est absente de .env.")

    model = settings.LLM_MODEL or DEFAULT_MODELS.get(provider, "")
    if not model:
        raise LLMError("Renseignez LLM_MODEL dans .env (nom du modèle à utiliser).")

    if provider == "ollama":
        from .ollama import OllamaClient

        return OllamaClient(
            settings.LLM_API_KEY,
            model,
            settings.LLM_TIMEOUT,
            settings.LLM_BASE_URL,
            settings.LLM_NUM_CTX,
        )
    if provider == "gemini":
        from .gemini import GeminiClient

        return GeminiClient(settings.LLM_API_KEY, model, settings.LLM_TIMEOUT)
    if provider == "anthropic":
        from .anthropic import AnthropicClient

        return AnthropicClient(settings.LLM_API_KEY, model, settings.LLM_TIMEOUT)
    raise LLMError(f"Fournisseur LLM inconnu : « {provider} ».")