import logging
import re

from .base import BaseLLMClient, LLMError

logger = logging.getLogger(__name__)

# Qwen3 peut écrire son raisonnement avant </think> : on ne garde que la réponse
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text):
    """Retire le raisonnement de Qwen3, avec ou sans balise ouvrante."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    return text.strip()


class OllamaClient(BaseLLMClient):
    name = "ollama"

    def __init__(self, api_key="", model_name="", timeout=90, base_url="", num_ctx=8192):
        super().__init__(api_key, model_name, timeout)
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.num_ctx = num_ctx

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        # Les variantes « instruct » de Qwen3 ne raisonnent jamais : aucun interrupteur à envoyer.
        # Les autres (dont la variante « thinking ») reçoivent think=false et « /no_think ».
        instruct = "instruct" in self.model_name.lower()
        if self.model_name.lower().startswith("qwen3") and not instruct:
            messages[-1]["content"] += " /no_think"  # interrupteur propre à Qwen3

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        if not instruct:
            payload["think"] = False
        if json_mode:
            payload["format"] = "json"

        data = self._post(
            f"{self.base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            payload=payload,
        )
        logger.info(
            "Ollama : chargement %.1f s | prompt %s tokens | génération %s tokens en %.1f s",
            data.get("load_duration", 0) / 1e9,
            data.get("prompt_eval_count", "?"),
            data.get("eval_count", "?"),
            data.get("eval_duration", 0) / 1e9,
        )
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("Réponse inattendue d'Ollama.") from exc
        return _strip_reasoning(text)