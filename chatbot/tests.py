import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.services.embeddings import index_document
from courses.services import eval_corpus
from courses.services.evaluation import build_chunks
from courses.test_embeddings import FakeEmbedder, make_document
from llm import LLMError
from llm.base import BaseLLMClient

from .models import ChatMessage, Conversation
from .services.rag import (
    NOT_FOUND_TOKEN,
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    _clean_citations,
    _retrieval_query,
    _select_hits,
    answer_question,
)

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()
# Le faux embedder donne des scores bien plus bas que e5 : seuil adapté
TEST_SETTINGS = dict(MEDIA_ROOT=TEMP_MEDIA, RAG_MIN_SCORE=0.3, RAG_SCORE_WINDOW=0.08)


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


@override_settings(RAG_MIN_SCORE=0.83, RAG_SCORE_WINDOW=0.04)
class SelectionTests(SimpleTestCase):
    def _hits(self, *scores):
        return [SimpleNamespace(score=s) for s in scores]

    def test_questions_measured_as_relevant_are_answered(self):
        for top in (0.866, 0.851, 0.848):
            self.assertTrue(_select_hits(self._hits(top)))

    def test_questions_measured_as_out_of_scope_are_refused(self):
        for top in (0.825, 0.803, 0.758):
            self.assertEqual(_select_hits(self._hits(top, top - 0.01)), [])

    def test_weak_tail_is_dropped(self):
        kept = _select_hits(self._hits(0.866, 0.841, 0.828, 0.825, 0.816))
        self.assertEqual([hit.score for hit in kept], [0.866, 0.841, 0.828])

    def test_empty_list(self):
        self.assertEqual(_select_hits([]), [])

    @override_settings(RAG_SCORE_WINDOW=0.08)
    def test_promoted_passage_below_the_best_score_is_kept(self):
        # 0,819 est à 0,047 du meilleur : gardé avec une fenêtre de 0,08
        kept = _select_hits(self._hits(0.841, 0.866, 0.819, 0.700))
        self.assertEqual(sorted(hit.score for hit in kept), [0.819, 0.841, 0.866])

    def test_refusal_uses_the_best_score_not_the_first_one(self):
        self.assertEqual(_select_hits(self._hits(0.70, 0.80)), [])


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

@override_settings(RAG_MIN_SCORE=0.83, RAG_SCORE_WINDOW=0.04)
class HybridSelectionTests(SimpleTestCase):
    def test_best_keyword_passage_is_kept_below_the_window(self):
        hits = [
            SimpleNamespace(score=0.88, lexical_rank=None),
            SimpleNamespace(score=0.80, lexical_rank=1),  # terme exact de la question
            SimpleNamespace(score=0.80, lexical_rank=2),
        ]
        self.assertEqual(_select_hits(hits), hits[:2])

    def test_keyword_match_alone_does_not_bypass_the_threshold(self):
        hits = [SimpleNamespace(score=0.70, lexical_rank=1)]
        self.assertEqual(_select_hits(hits), [])


class PromptTests(SimpleTestCase):
    def test_prompt_handles_language_partial_answers_and_refusal(self):
        self.assertIn("langue de la question", SYSTEM_PROMPT)
        self.assertIn("une partie de la question", SYSTEM_PROMPT)
        self.assertIn(NOT_FOUND_TOKEN, SYSTEM_PROMPT)


# Chunks réels (~600 caractères) : le faux embedder « sac de mots » donne des
# cosinus bas, d'où un seuil plus bas que pour les phrases courtes des autres tests.
@override_settings(**{**TEST_SETTINGS, "RAG_MIN_SCORE": 0.05, "RAG_SCORE_WINDOW": 0.2})
class MultiSubjectRagTests(TestCase):
    """Le même pipeline répond sur des cours de matières et de langues différentes."""

    def setUp(self):
        self.owner = User.objects.create_user("carol", "carol@example.com", PASSWORD)
        self.embedder = FakeEmbedder()
        self.conversations = {}
        for spec in eval_corpus.DOCUMENTS:
            chunks = build_chunks(eval_corpus.raw_pages(spec))
            document = make_document(self.owner, spec["title"], texts=[c.text for c in chunks])
            for stored, chunk in zip(document.chunks.order_by("chunk_index"), chunks):
                stored.page_start, stored.page_end = chunk.page_start, chunk.page_end
                stored.save(update_fields=["page_start", "page_end"])
            index_document(document, self.embedder)
            self.conversations[spec["key"]] = Conversation.objects.create(document=document, title="t")

    def _ask(self, key, question):
        llm = FakeLLM("Réponse [1].")
        answer = answer_question(
            self.conversations[key], question, embedder=self.embedder, client=llm
        )
        return answer, llm

    def test_each_subject_gets_the_right_passage_and_pages(self):
        cases = [
            ("droit", "responsabilité des associés SNC dettes", "indéfiniment et solidairement", 1),
            ("informatique", "méthode HTTP DELETE supprimer ressource", "DELETE pour supprimer", 1),
            ("mathematiques", "espérance loi binomiale", "E(X) = np", 3),
            ("data_science", "régression logistique fonction sigmoïde", "fonction sigmoïde", 2),
            ("english", "logistic regression sigmoid function", "sigmoid function", 1),
        ]
        for key, question, needle, page in cases:
            with self.subTest(key=key):
                answer, llm = self._ask(key, question)
                self.assertTrue(answer.grounded)
                self.assertIn(needle, llm.prompts[0])
                pages = {(s["page_start"], s["page_end"]) for s in answer.sources}
                self.assertTrue(any(start <= page <= end for start, end in pages))

    def test_question_outside_the_course_is_refused(self):
        answer, llm = self._ask("mathematiques", "recette tarte pommes cannelle")
        self.assertFalse(answer.grounded)
        self.assertEqual(llm.prompts, [])
