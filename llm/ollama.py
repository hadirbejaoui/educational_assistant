import re

from .base import BaseLLMClient, LLMError

# Qwen3 peut écrire son raisonnement entre <think>...</think> : on le retire
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OllamaClient(BaseLLMClient):
    name = "ollama"

    def __init__(self, api_key="", model_name="", timeout=90, base_url=""):
        super().__init__(api_key, model_name, timeout)
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "think": False,  # pas de bloc de réflexion : plus rapide, JSON plus propre
            "options": {"temperature": temperature, "num_ctx": 8192},
        }
        if json_mode:
            payload["format"] = "json"

        data = self._post(
            f"{self.base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            payload=payload,
        )
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("Réponse inattendue d'Ollama.") from exc
        return _THINK.sub("", text).strip()