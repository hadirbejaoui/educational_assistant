import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.services.embeddings import index_document
from courses.test_embeddings import FakeEmbedder, make_document
from llm import LLMError
from llm.base import BaseLLMClient

from .models import ChatMessage, Conversation
from .services.rag import (
    NOT_FOUND_TOKEN,
    REFUSAL_MESSAGE,
    _clean_citations,
    _retrieval_query,
    answer_question,
)

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()
# Le faux embedder donne des scores bien plus bas que e5 : seuil adapté
TEST_SETTINGS = dict(MEDIA_ROOT=TEMP_MEDIA, RAG_MIN_SCORE=0.3)


class FakeLLM(BaseLLMClient):
    name = "fake"

    def __init__(self, reply="Réponse [1]."):
        self.model_name = "fake-1"
        self.reply = reply
        self.prompts = []

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class HelperTests(SimpleTestCase):
    def test_short_question_is_completed_by_previous_one(self):
        history = [
            SimpleNamespace(role="user", content="Parle du SNC"),
            SimpleNamespace(role="assistant", content="..."),
        ]
        self.assertEqual(_retrieval_query("et la SARL ?", history), "Parle du SNC et la SARL ?")

    def test_long_question_is_kept_as_is(self):
        history = [SimpleNamespace(role="user", content="Parle du SNC")]
        question = "Quelle est la capitale de la France exactement"
        self.assertEqual(_retrieval_query(question, history), question)

    def test_short_question_without_history(self):
        self.assertEqual(_retrieval_query("et la SARL ?", []), "et la SARL ?")

    def test_unknown_citations_are_removed(self):
        text, cited = _clean_citations("A [1] B [3] C [9].", 3)
        self.assertNotIn("[9]", text)
        self.assertIn("[1]", text)
        self.assertEqual(cited, {1, 3})


@override_settings(**TEST_SETTINGS)
class RagTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.embedder = FakeEmbedder()
        self.document = make_document(self.alice)
        index_document(self.document, self.embedder)
        self.conversation = Conversation.objects.create(document=self.document, title="t")

    def _ask(self, question, reply="La capitale est Paris [1]."):
        llm = FakeLLM(reply)
        answer = answer_question(self.conversation, question, embedder=self.embedder, client=llm)
        return answer, llm

    def test_answer_is_grounded_with_real_sources(self):
        answer, llm = self._ask("capitale France")
        self.assertTrue(answer.grounded)
        self.assertEqual(len(answer.sources), 1)
        self.assertEqual(answer.sources[0]["page_start"], 2)
        self.assertTrue(answer.sources[0]["cited"])
        self.assertIn("Paris", llm.prompts[0])
        self.assertIn("capitale France", llm.prompts[0])

    def test_below_threshold_refuses_without_calling_llm(self):
        answer, llm = self._ask("recette tarte pommes")
        self.assertFalse(answer.grounded)
        self.assertEqual(answer.content, REFUSAL_MESSAGE)
        self.assertEqual(llm.prompts, [])

    def test_model_saying_not_found_is_a_refusal(self):
        answer, _ = self._ask("capitale France", reply=NOT_FOUND_TOKEN)
        self.assertFalse(answer.grounded)
        self.assertEqual(answer.content, REFUSAL_MESSAGE)
        self.assertEqual(answer.sources, [])

    def test_invented_citation_is_removed(self):
        answer, _ = self._ask("capitale France", reply="Paris [1] et ailleurs [9].")
        self.assertNotIn("[9]", answer.content)
        self.assertIn("[1]", answer.content)

    def test_history_is_given_to_the_model(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Parle-moi de la capitale")
        ChatMessage.objects.create(conversation=self.conversation, role="assistant", content="Voici.")
        _, llm = self._ask("capitale France")
        self.assertIn("Parle-moi de la capitale", llm.prompts[0])


@override_settings(**TEST_SETTINGS)
class ChatViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)
        self.embedder = FakeEmbedder()
        self.document = make_document(self.alice, "Cours Alice")
        self.bob_doc = make_document(self.bob, "Cours Bob")
        index_document(self.document, self.embedder)
        index_document(self.bob_doc, self.embedder)
        self.conversation = Conversation.objects.create(document=self.document, title="Conv Alice")
        self.bob_conversation = Conversation.objects.create(document=self.bob_doc, title="Conv Bob")

    def _send(self, message, reply="Paris [1].", conversation=None):
        conversation = conversation or self.conversation
        with patch("chatbot.services.rag.get_embedder", return_value=self.embedder), \
             patch("chatbot.services.rag.get_llm_client", return_value=FakeLLM(reply)):
            return self.client.post(
                reverse("chatbot:send", args=[conversation.pk]), {"message": message}
            )

    def test_pages_require_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("chatbot:list")).status_code, 302)

    def test_list_shows_only_own_conversations(self):
        response = self.client.get(reverse("chatbot:list"))
        self.assertContains(response, "Conv Alice")
        self.assertNotContains(response, "Conv Bob")

    def test_cannot_open_send_or_delete_other_users_conversation(self):
        pk = self.bob_conversation.pk
        self.assertEqual(self.client.get(reverse("chatbot:detail", args=[pk])).status_code, 404)
        self.assertEqual(self._send("capitale France", conversation=self.bob_conversation).status_code, 404)
        self.assertEqual(self.client.post(reverse("chatbot:delete", args=[pk])).status_code, 404)
        self.assertTrue(Conversation.objects.filter(pk=pk).exists())
        self.assertEqual(self.bob_conversation.messages.count(), 0)

    def test_create_requires_post(self):
        self.assertEqual(self.client.get(reverse("chatbot:create")).status_code, 405)

    def test_create_indexes_document_and_redirects(self):
        fresh = make_document(self.alice, "Neuf")
        with patch("chatbot.views.get_embedder", return_value=self.embedder):
            response = self.client.post(reverse("chatbot:create"), {"document": fresh.pk})
        conversation = Conversation.objects.get(document=fresh)
        self.assertRedirects(response, reverse("chatbot:detail", args=[conversation.pk]))
        self.assertEqual(fresh.chunks.filter(embedding__isnull=False).count(), 3)

    def test_cannot_create_on_other_users_document(self):
        before = Conversation.objects.count()
        with patch("chatbot.views.get_embedder", return_value=self.embedder):
            self.client.post(reverse("chatbot:create"), {"document": self.bob_doc.pk})
        self.assertEqual(Conversation.objects.count(), before)

    def test_send_saves_both_messages_with_sources(self):
        response = self._send("capitale France")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["grounded"])
        self.assertEqual(data["sources"][0]["page_start"], 2)
        roles = list(self.conversation.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(self.conversation.messages.last().sources[0]["n"], 1)

    def test_first_question_becomes_the_title(self):
        self._send("capitale France")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "capitale France")

    def test_out_of_scope_question_is_refused_and_saved(self):
        data = self._send("recette tarte pommes").json()
        self.assertFalse(data["grounded"])
        self.assertEqual(data["answer"], REFUSAL_MESSAGE)
        self.assertEqual(self.conversation.messages.count(), 2)

    def test_empty_message_is_rejected(self):
        self.assertEqual(self._send("   ").status_code, 400)
        self.assertEqual(self.conversation.messages.count(), 0)

    @override_settings(RAG_MAX_QUESTION_CHARS=10)
    def test_too_long_message_is_rejected(self):
        self.assertEqual(self._send("x" * 11).status_code, 400)

    def test_llm_failure_returns_error_and_saves_nothing(self):
        response = self._send("capitale France", reply=LLMError("Panne du LLM."))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Panne du LLM.")
        self.assertEqual(self.conversation.messages.count(), 0)

    def test_send_requires_post(self):
        response = self.client.get(reverse("chatbot:send", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 405)

    def test_detail_shows_history_and_escapes_html(self):
        ChatMessage.objects.create(
            conversation=self.conversation, role="assistant", content="<script>alert(1)</script>"
        )
        response = self.client.get(reverse("chatbot:detail", args=[self.conversation.pk]))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_delete_conversation(self):
        self.client.post(reverse("chatbot:delete", args=[self.conversation.pk]))
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())

    def test_deleting_document_deletes_conversations_and_messages(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="x")
        self.document.delete()
        self.assertFalse(Conversation.objects.filter(title="Conv Alice").exists())
        self.assertEqual(ChatMessage.objects.count(), 0)