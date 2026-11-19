from .base import BaseLLMClient, LLMError

URL = "https://api.anthropic.com/v1/messages"


class AnthropicClient(BaseLLMClient):
    name = "anthropic"

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        data = self._post(
            URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload=payload,
        )
        try:
            return "".join(
                block.get("text", "")
                for block in data["content"]
                if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise LLMError("Réponse inattendue du modèle.") from exc