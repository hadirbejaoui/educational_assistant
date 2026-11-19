
import re

from .base import BaseLLMClient, LLMError


_THINK_BLOCK = re.compile(
    r"<think>.*?</think>",
    re.DOTALL | re.IGNORECASE
)


def _strip_reasoning(text):
    """Retire le raisonnement de Qwen3, avec ou sans balise ouvrante."""

    text = _THINK_BLOCK.sub("", text)

    if "</think>" in text.lower():
        text = re.split(
            r"</think>",
            text,
            flags=re.IGNORECASE
        )[-1]

    return text.strip()


class OllamaClient(BaseLLMClient):

    name = "ollama"

    def __init__(
        self,
        api_key="",
        model_name="",
        timeout=90,
        base_url=""
    ):
        super().__init__(api_key, model_name, timeout)

        self.base_url = (
            base_url or "http://localhost:11434"
        ).rstrip("/")

    def generate(
        self,
        prompt,
        system="",
        json_mode=False,
        temperature=0.4
    ):

        # Construction des messages
        messages = []

        if system:
            messages.append({
                "role": "system",
                "content": system
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        # Désactiver le raisonnement pour Qwen3
        if self.model_name.lower().startswith("qwen3"):
            messages[-1]["content"] += " /no_think"

        # Préparation de la requête
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192
            }
        }

        # Mode JSON
        if json_mode:
            payload["format"] = "json"

        # Appel API Ollama
        data = self._post(
            f"{self.base_url}/api/chat",
            headers={
                "Content-Type": "application/json"
            },
            payload=payload
        )

        # Récupération de la réponse
        try:
            text = data["message"]["content"]

        except (KeyError, TypeError) as exc:
            raise LLMError(
                "Réponse inattendue d'Ollama."
            ) from exc

        return _strip_reasoning(text)
