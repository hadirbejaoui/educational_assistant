
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Erreur lisible par l'étudiant (clé refusée, quota, réseau...)."""


class BaseLLMClient(ABC):
    """Interface commune : changer de fournisseur = changer une classe."""

    name = "base"

    def __init__(self, api_key="", model_name="", timeout=90):
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout

    @abstractmethod
    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        """Retourne le texte généré par le modèle."""

    def _post(self, url, headers, payload):
        import requests

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

        except requests.ConnectionError as exc:
            raise LLMError(
                "Impossible de joindre le LLM. Si vous utilisez Ollama, "
                "vérifiez qu'il est lancé (icône dans la barre des tâches)."
            ) from exc

        except requests.Timeout as exc:
            raise LLMError(
                "Le LLM n'a pas répondu à temps. Un modèle local peut être lent : "
                "augmentez LLM_TIMEOUT dans .env."
            ) from exc

        except requests.RequestException as exc:
            raise LLMError(
                "Une erreur réseau est survenue lors de la communication avec le LLM."
            ) from exc

        # Vérifier si le modèle demandé existe
        if response.status_code == 404:
            raise LLMError(
                "Modèle introuvable. Vérifiez LLM_MODEL "
                "(pour Ollama : `ollama list`)."
            )

        if response.status_code in (401, 403):
            raise LLMError(
                "Clé API refusée par le fournisseur LLM."
            )

        if response.status_code == 429:
            raise LLMError(
                "Quota ou limite de requêtes atteint. Réessayez plus tard."
            )

        if response.status_code >= 400:
            logger.warning(
                "Erreur LLM %s : %s",
                response.status_code,
                response.text[:300]
            )
            raise LLMError(
                f"Le fournisseur LLM a répondu par une erreur "
                f"({response.status_code}). Vérifiez le nom du modèle "
                "dans LLM_MODEL."
            )

        try:
            return response.json()

        except ValueError as exc:
            raise LLMError(
                "Réponse illisible du fournisseur LLM."
            ) from exc
