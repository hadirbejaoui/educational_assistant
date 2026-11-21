"""Espaces privés : deux comptes A et B ne voient, ne modifient et ne récupèrent jamais
les données l'un de l'autre, même en forgeant un identifiant dans une URL ou un formulaire.
Le RAG ne cherche que dans les passages des cours du compte connecté."""

import shutil
import tempfile
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from chatbot.models import Conversation
from chatbot.services.rag import answer_question
from chatbot.tests import FakeLLM
from courses.models import CourseDocument
from courses.services.embeddings import index_document
from courses.test_embeddings import FakeEmbedder, make_document
from quizzes.models import Quiz
from quizzes.services.generation import generate_quiz
from quizzes.services.grading import grade_attempt
from quizzes.tests import questions_json
from summaries.models import Summary

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()

# Les deux comptes ont des cours au contenu voisin : une fuite de recherche serait visible
ALICE_TEXTS = ["la capitale de la France est Paris", "Paris compte vingt arrondissements"]
BOB_TEXTS = ["la capitale de la France selon Bob est Lyon", "Lyon secret de Bob"]


@override_settings(MEDIA_ROOT=TEMP_MEDIA, RAG_MIN_SCORE=0.05, RAG_SCORE_WINDOW=1.0,
                   RATE_LIMITS={"chat": (0, 60), "quiz": (0, 60), "summary": (0, 60)})
class AccountIsolationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.embedder = FakeEmbedder()
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.alice_doc = make_document(self.alice, "Cours d'Alice", ALICE_TEXTS)
        self.bob_doc = make_document(self.bob, "Cours secret de Bob", BOB_TEXTS)
        for document in (self.alice_doc, self.bob_doc):
            index_document(document, self.embedder)
            Summary.objects.create(document=document, level="short", provider="fake",
                                   content=f"Résumé de {document.title}")
        self.bob_quiz = generate_quiz(self.bob_doc, 2, "easy", FakeLLM(questions_json(2)))
        self.bob_attempt = grade_attempt(self.bob_quiz, {})
        self.bob_conversation = Conversation.objects.create(
            document=self.bob_doc, owner=self.bob, title="Conversation secrète de Bob"
        )
        self.client.login(username="alice", password=PASSWORD)

    # --- Ce que voit chaque compte ----------------------------------------------------

    def test_each_account_only_lists_its_own_data(self):
        for name in ("courses:list", "summaries:list", "quizzes:list", "quizzes:history",
                     "chatbot:list", "dashboard"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "secret")
        # Et réciproquement : Bob ne voit pas le cours d'Alice
        self.client.login(username="bob", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("courses:list")), "Cours d&#x27;Alice")
        self.assertNotContains(self.client.get(reverse("summaries:list")), "Cours d&#x27;Alice")

    def test_forged_identifiers_in_urls_give_404(self):
        doc, quiz, attempt, conv = self.bob_doc.pk, self.bob_quiz.pk, self.bob_attempt.pk, self.bob_conversation.pk
        gets = [
            reverse("courses:detail", args=[doc]), reverse("courses:file", args=[doc]),
            reverse("courses:search", args=[doc]), reverse("courses:delete", args=[doc]),
            reverse("summaries:document", args=[doc]),
            reverse("quizzes:detail", args=[quiz]), reverse("quizzes:take", args=[quiz]),
            reverse("quizzes:result", args=[attempt]), reverse("chatbot:detail", args=[conv]),
        ]
        posts = [
            reverse("courses:index", args=[doc]), reverse("courses:reprocess", args=[doc]),
            reverse("courses:delete", args=[doc]), reverse("summaries:generate", args=[doc, "short"]),
            reverse("quizzes:take", args=[quiz]), reverse("quizzes:delete", args=[quiz]),
            reverse("chatbot:send", args=[conv]), reverse("chatbot:delete", args=[conv]),
        ]
        for url in gets:
            with self.subTest(get=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        for url in posts:
            with self.subTest(post=url):
                self.assertEqual(self.client.post(url, {"message": "Lyon ?"}).status_code, 404)
        # Rien n'a été modifié chez Bob
        self.assertTrue(CourseDocument.objects.filter(pk=doc).exists())
        self.assertTrue(Quiz.objects.filter(pk=quiz).exists())
        self.assertEqual(self.bob_quiz.attempts.count(), 1)
        self.assertEqual(self.bob_conversation.messages.count(), 0)
        self.assertEqual(Summary.objects.get(document=self.bob_doc).content, "Résumé de Cours secret de Bob")

    def test_forged_course_in_forms_is_refused(self):
        llm = FakeLLM(questions_json(2))
        with patch("quizzes.services.generation.get_llm_client", return_value=llm), \
             patch("chatbot.views.get_embedder", return_value=self.embedder):
            self.client.post(reverse("quizzes:create"), {"document": self.bob_doc.pk, "count": 2, "difficulty": "easy"})
            self.client.post(reverse("chatbot:create"), {"document": self.bob_doc.pk})
        self.assertEqual(llm.prompts, [])  # le LLM n'a jamais reçu le cours de Bob
        self.assertFalse(Quiz.objects.filter(document=self.bob_doc).exclude(pk=self.bob_quiz.pk).exists())
        self.assertFalse(Conversation.objects.filter(document=self.bob_doc, owner=self.alice).exists())

    def test_admin_has_a_private_space_too(self):
        User.objects.create_user("prof", "prof@example.com", PASSWORD, is_staff=True, is_superuser=True)
        self.client.login(username="prof", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.bob_doc.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("courses:list")), "secret")
        self.assertEqual(self.client.get("/admin/").status_code, 200)  # gestion des comptes

    def test_django_admin_is_refused_to_ordinary_accounts(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    # --- Gestion de ses propres cours ----------------------------------------------------

    def test_every_account_manages_its_own_courses(self):
        pdf = SimpleUploadedFile("c.txt", b"La photosynthese produit du glucose.", content_type="text/plain")
        with patch("courses.views.get_embedder", return_value=self.embedder):
            self.client.post(reverse("courses:upload"), {"title": "Biologie", "file": pdf})
            document = CourseDocument.objects.get(title="Biologie")
            self.assertEqual(document.owner, self.alice)
            self.assertEqual(document.status, "ready")
            self.assertFalse(document.chunks.filter(embedding__isnull=True).exists())  # indexé à l'import

            document.chunks.update(embedding=None)
            self.client.post(reverse("courses:index", args=[document.pk]))
            self.assertFalse(document.chunks.filter(embedding__isnull=True).exists())

            self.client.post(reverse("courses:reprocess", args=[document.pk]))
            document.refresh_from_db()
            self.assertEqual(document.status, "ready")

        path = document.file.path
        self.client.post(reverse("courses:delete", args=[document.pk]))
        self.assertFalse(CourseDocument.objects.filter(pk=document.pk).exists())
        self.assertFalse(Summary.objects.filter(document_id=document.pk).exists())
        import os
        self.assertFalse(os.path.exists(path))

    # --- RAG -------------------------------------------------------------------------------

    def test_rag_only_retrieves_and_cites_the_accounts_own_course(self):
        conversation = Conversation.objects.create(document=self.alice_doc, owner=self.alice, title="t")
        llm = FakeLLM("Paris [1] [2].")
        answer = answer_question(conversation, "Quelle est la capitale de la France ?",
                                 embedder=self.embedder, client=llm)
        alice_chunks = set(self.alice_doc.chunks.values_list("id", flat=True))
        self.assertTrue(answer.sources)
        self.assertTrue({source["chunk_id"] for source in answer.sources} <= alice_chunks)
        self.assertNotIn("Lyon", llm.prompts[0])  # aucun passage de Bob dans le contexte
        self.assertNotIn("secret", llm.prompts[0])

    def test_rag_through_the_view_stays_in_the_conversation_course(self):
        conversation = Conversation.objects.create(document=self.alice_doc, owner=self.alice, title="t")
        with patch("chatbot.services.rag.get_embedder", return_value=self.embedder), \
             patch("chatbot.services.rag.get_llm_client", return_value=FakeLLM("Paris [1].")):
            data = self.client.post(reverse("chatbot:send", args=[conversation.pk]),
                                    {"message": "la capitale selon Bob est Lyon ?"}).json()
        bob_chunks = set(self.bob_doc.chunks.values_list("id", flat=True))
        self.assertFalse({source["chunk_id"] for source in data["sources"]} & bob_chunks)
