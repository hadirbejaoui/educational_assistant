"""Tests de bout en bout : le parcours complet d'un étudiant, à travers les vraies vues.

Seuls le modèle d'embeddings et le LLM sont remplacés par des faux (déterministes et
rapides) : base de données, extraction PDF, découpage, recherche hybride, RAG,
génération/correction de quiz, résumé extractif et tableau de bord sont les vrais.
"""

import json
import os
import shutil
import tempfile
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from chatbot.models import Conversation
from chatbot.tests import FakeLLM
from courses.models import CourseDocument, DocumentChunk
from courses.test_embeddings import FakeEmbedder
from courses.test_services import make_pdf
from quizzes.models import Quiz, QuizAttempt

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()

COURSE_PAGES = [
    "Chapitre 1 La societe en nom collectif\nLa SNC est une societe commerciale.\n"
    "Les associes repondent indefiniment et solidairement des dettes sociales.",
    "Chapitre 2 La societe anonyme\nLa SA compte au moins sept actionnaires.\n"
    "Le capital minimum est de cinq mille dinars sans appel public a l'epargne.",
]
QUIZ_JSON = json.dumps({"questions": [
    {"question": f"Question {i} sur la SNC ?", "choices": ["Limitee", "Indefinie", "Nulle", "Variable"],
     "correct_index": 1, "explanation": "Page 1 du cours.", "difficulty": "easy"}
    for i in range(3)
]})


class QuizLLM(FakeLLM):
    """Faux LLM qui répond toujours par le même lot de questions."""

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        self.prompts.append(prompt)
        return QUIZ_JSON


# L'import indexe le cours : faux modèle d'embeddings (ni téléchargement ni calcul réel)
@patch("courses.views.get_embedder", new=FakeEmbedder)
@override_settings(
    MEDIA_ROOT=TEMP_MEDIA, RAG_MIN_SCORE=0.05, RAG_SCORE_WINDOW=1.0, SUMMARY_PROVIDER="extractive",
    RATE_LIMITS={"chat": (0, 60), "quiz": (0, 60), "summary": (0, 60)},
)
class StudentJourneyTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.embedder = FakeEmbedder()

    def _register_and_login(self, username):
        response = self.client.post(reverse("accounts:register"), {
            "username": username, "email": f"{username}@example.com",
            "first_name": username.title(), "last_name": "Test",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertRedirects(response, reverse("accounts:login"))
        response = self.client.post(reverse("accounts:login"), {"username": username, "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard"))

    def _upload_course(self):
        pdf = SimpleUploadedFile("droit.pdf", make_pdf(COURSE_PAGES), content_type="application/pdf")
        response = self.client.post(reverse("courses:upload"), {"title": "Droit des sociétés", "file": pdf}, follow=True)
        document = CourseDocument.objects.get(title="Droit des sociétés")
        self.assertEqual(document.status, "ready")
        self.assertEqual(document.page_count, 2)
        self.assertContains(response, "2 page(s)")
        return document

    def test_full_journey(self):
        self._register_and_login("hadir")

        # 1. Import d'un vrai PDF : extraction, nettoyage, découpage
        document = self._upload_course()
        self.assertTrue(DocumentChunk.objects.filter(document=document).exists())

        # 2. Résumé extractif
        response = self.client.post(reverse("summaries:generate", args=[document.pk, "short"]), follow=True)
        self.assertContains(response, "Résumé généré.")
        self.assertEqual(document.summaries.count(), 1)

        # 3. Chatbot : création (indexation), question, réponse avec sources
        with patch("chatbot.views.get_embedder", return_value=self.embedder):
            response = self.client.post(reverse("chatbot:create"), {"document": document.pk})
        conversation = Conversation.objects.get(document=document)
        self.assertRedirects(response, reverse("chatbot:detail", args=[conversation.pk]))
        self.assertFalse(document.chunks.filter(embedding__isnull=True).exists())

        llm = FakeLLM("Les associés répondent indéfiniment et solidairement [1].")
        with patch("chatbot.services.rag.get_embedder", return_value=self.embedder), \
             patch("chatbot.services.rag.get_llm_client", return_value=llm):
            response = self.client.post(
                reverse("chatbot:send", args=[conversation.pk]),
                {"message": "Les associes repondent des dettes sociales comment ?"},
            )
        data = response.json()
        self.assertTrue(data["grounded"])
        self.assertTrue(any(source["cited"] and source["page_start"] == 1 for source in data["sources"]))
        self.assertIn("indefiniment et solidairement", llm.prompts[0])

        # 4. Quiz : génération, passage avec toutes les bonnes réponses, note sur 20
        with patch("quizzes.services.generation.get_llm_client", return_value=QuizLLM("")):
            response = self.client.post(reverse("quizzes:create"),
                                        {"document": document.pk, "count": 3, "difficulty": "easy"}, follow=True)
        quiz = Quiz.objects.get(document=document)
        self.assertContains(response, "Quiz généré : 3 question(s).")
        answers = {
            f"question_{q.pk}": q.choices.get(is_correct=True).pk for q in quiz.questions.all()
        }
        response = self.client.post(reverse("quizzes:take", args=[quiz.pk]), answers, follow=True)
        attempt = QuizAttempt.objects.get(quiz=quiz)
        self.assertEqual((attempt.score, attempt.total), (3, 3))
        self.assertContains(response, "20,0/20")

        # 5. Tableau de bord, historique et fichier original
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.context["counts"],
                         {"documents": 1, "summaries": 1, "quizzes": 1, "conversations": 1})
        self.assertEqual(dashboard.context["average_grade"], 20.0)
        self.assertContains(self.client.get(reverse("quizzes:history")), "Droit des sociétés")
        file_response = self.client.get(reverse("courses:file", args=[document.pk]))
        self.assertEqual(b"".join(file_response.streaming_content)[:5], b"%PDF-")

    def test_another_student_sees_nothing_and_deletion_cascades(self):
        self._register_and_login("hadir")
        document = self._upload_course()
        path = document.file.path
        with patch("chatbot.views.get_embedder", return_value=self.embedder):
            self.client.post(reverse("chatbot:create"), {"document": document.pk})
        conversation = Conversation.objects.get(document=document)

        # Un deuxième étudiant : aucune donnée visible, 404 partout
        self.client.logout()
        self._register_and_login("sami")
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.context["counts"]["documents"], 0)
        self.assertNotContains(dashboard, "Droit des sociétés")
        for url in (
            reverse("courses:detail", args=[document.pk]),
            reverse("courses:file", args=[document.pk]),
            reverse("summaries:document", args=[document.pk]),
            reverse("chatbot:detail", args=[conversation.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        response = self.client.post(reverse("courses:delete", args=[document.pk]))
        self.assertEqual(response.status_code, 404)

        # Le propriétaire supprime : base ET fichier disparaissent
        self.client.logout()
        self.client.login(username="hadir", password=PASSWORD)
        self.client.post(reverse("courses:delete", args=[document.pk]))
        self.assertFalse(CourseDocument.objects.exists())
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(DocumentChunk.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_invalid_upload_is_refused_by_the_server(self):
        self._register_and_login("hadir")
        fake_pdf = SimpleUploadedFile("cours.pdf", b"ceci n'est pas un PDF")
        response = self.client.post(reverse("courses:upload"), {"title": "x", "file": fake_pdf})
        self.assertContains(response, "pas un PDF valide")
        self.assertEqual(User.objects.get(username="hadir").documents.count(), 0)
