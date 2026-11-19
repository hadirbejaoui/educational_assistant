from .base import BaseLLMClient, LLMError

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient(BaseLLMClient):
    name = "gemini"

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        data = self._post(
            URL.format(model=self.model_name),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            payload=payload,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Réponse inattendue du modèle (contenu bloqué ?).") from exc