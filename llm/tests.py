"""Tests de la couche LLM : traduction des erreurs, choix du fournisseur, format des requêtes.

Aucun appel réseau : requests.post est remplacé par un faux.
"""

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from . import LLMError, get_llm_client
from .anthropic import AnthropicClient
from .gemini import GeminiClient
from .ollama import OllamaClient


def fake_response(status=200, payload=None, text=""):
    response = MagicMock(status_code=status, text=text)
    if isinstance(payload, Exception):
        response.json.side_effect = payload
    else:
        response.json.return_value = payload if payload is not None else {}
    return response


class PostErrorTests(SimpleTestCase):
    """Chaque panne devient un message compréhensible par l'étudiant."""

    def _post(self, response=None, error=None):
        client = GeminiClient("cle", "modele", timeout=5)
        with patch("requests.post", return_value=response, side_effect=error):
            return client._post("https://exemple.test", {}, {})

    def assertLLMError(self, fragment, **kwargs):
        with self.assertRaises(LLMError) as context:
            self._post(**kwargs)
        self.assertIn(fragment, str(context.exception))

    def test_connection_refused(self):
        self.assertLLMError("Impossible de joindre le LLM", error=requests.ConnectionError())

    def test_timeout(self):
        self.assertLLMError("n'a pas répondu à temps", error=requests.Timeout())

    def test_rejected_key(self):
        self.assertLLMError("Clé API refusée", response=fake_response(401, {"error": {"message": "invalid"}}))

    def test_billing_required(self):
        self.assertLLMError("facturation", response=fake_response(403, {"error": {"message": "Free tier not available"}}))

    def test_quota(self):
        self.assertLLMError("Quota", response=fake_response(429))

    def test_unknown_model(self):
        self.assertLLMError("Modèle introuvable", response=fake_response(404))

    def test_server_error(self):
        self.assertLLMError("(500)", response=fake_response(500, text="boom"))

    def test_unreadable_json(self):
        self.assertLLMError("illisible", response=fake_response(200, ValueError("pas du JSON")))

    def test_success_returns_json(self):
        self.assertEqual(self._post(response=fake_response(200, {"ok": True})), {"ok": True})


class ProviderSelectionTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="")
    def test_no_provider(self):
        with self.assertRaisesMessage(LLMError, "Aucun LLM configuré"):
            get_llm_client()

    @override_settings(LLM_PROVIDER="gemini", LLM_API_KEY="")
    def test_cloud_provider_needs_a_key(self):
        with self.assertRaisesMessage(LLMError, "LLM_API_KEY"):
            get_llm_client()

    @override_settings(LLM_PROVIDER="mistral", LLM_API_KEY="x", LLM_MODEL="m")
    def test_unknown_provider(self):
        with self.assertRaisesMessage(LLMError, "inconnu"):
            get_llm_client()

    @override_settings(LLM_PROVIDER="gemini", LLM_API_KEY="x", LLM_MODEL="")
    def test_gemini_needs_a_model_name(self):
        with self.assertRaisesMessage(LLMError, "LLM_MODEL"):
            get_llm_client()

    @override_settings(LLM_PROVIDER="anthropic", LLM_API_KEY="x", LLM_MODEL="")
    def test_each_provider_builds_its_client(self):
        self.assertIsInstance(get_llm_client(), AnthropicClient)
        with self.settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini-x"):
            self.assertIsInstance(get_llm_client(), GeminiClient)
        with self.settings(LLM_PROVIDER="ollama", LLM_API_KEY="", LLM_MODEL=""):
            client = get_llm_client()
            self.assertIsInstance(client, OllamaClient)
            self.assertEqual(client.model_name, "qwen3:4b")


class ClientFormatTests(SimpleTestCase):
    """Le même appel generate() produit la requête attendue par chaque fournisseur."""

    def test_gemini_request_and_answer(self):
        client = GeminiClient("cle", "gemini-x")
        answer = {"candidates": [{"content": {"parts": [{"text": "Bon"}, {"text": "jour"}]}}]}
        with patch.object(client, "_post", return_value=answer) as post:
            self.assertEqual(client.generate("Q", system="S", json_mode=True), "Bonjour")
        url, payload = post.call_args.args[0], post.call_args.kwargs["payload"]
        self.assertIn("gemini-x", url)
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "S")
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "cle")

    def test_gemini_blocked_content(self):
        client = GeminiClient("cle", "gemini-x")
        with patch.object(client, "_post", return_value={"candidates": []}):
            with self.assertRaisesMessage(LLMError, "bloqué"):
                client.generate("Q")

    def test_anthropic_request_and_answer(self):
        client = AnthropicClient("cle", "claude-x")
        answer = {"content": [{"type": "text", "text": "Réponse"}, {"type": "tool_use"}]}
        with patch.object(client, "_post", return_value=answer) as post:
            self.assertEqual(client.generate("Q", system="S"), "Réponse")
        payload = post.call_args.kwargs["payload"]
        self.assertEqual(payload["system"], "S")
        self.assertEqual(payload["model"], "claude-x")
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "cle")

    def test_anthropic_unexpected_answer(self):
        client = AnthropicClient("cle", "claude-x")
        with patch.object(client, "_post", return_value={"pas": "de contenu"}):
            with self.assertRaises(LLMError):
                client.generate("Q")

    def test_ollama_request_disables_thinking_and_strips_reasoning(self):
        client = OllamaClient(model_name="qwen3:4b", num_ctx=4096)
        answer = {"message": {"content": "raisonnement...</think>\nRéponse finale"}}
        with patch.object(client, "_post", return_value=answer) as post:
            self.assertEqual(client.generate("Q", system="S", json_mode=True), "Réponse finale")
        payload = post.call_args.kwargs["payload"]
        self.assertFalse(payload["think"])
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertTrue(payload["messages"][-1]["content"].endswith("/no_think"))

    def test_ollama_unexpected_answer(self):
        client = OllamaClient(model_name="qwen3:4b")
        with patch.object(client, "_post", return_value={"rien": 1}):
            with self.assertRaisesMessage(LLMError, "inattendue"):
                client.generate("Q")
