"""Tests de la commande de démonstration `python manage.py demo` (faux modèles, aucun accès réseau)."""

import io
import shutil
import tempfile
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from accounts.models import User
from chatbot.tests import FakeLLM as ChatLLM
from courses.models import CourseDocument
from courses.test_embeddings import FakeEmbedder
from quizzes.models import Quiz
from quizzes.tests import FakeLLM as QuizLLM
from quizzes.tests import questions_json

TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA, RAG_MIN_SCORE=0.05, RAG_SCORE_WINDOW=1.0, SUMMARY_PROVIDER="extractive")
@patch("core.management.commands.demo.get_embedder", new=FakeEmbedder)
@patch("chatbot.services.rag.get_embedder", new=FakeEmbedder)
class DemoCommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def run_demo(self, *args):
        out = io.StringIO()
        call_command("demo", *args, stdout=out)
        return out.getvalue()

    def test_without_llm_runs_the_pipeline_and_cleans_up(self):
        output = self.run_demo("--sans-llm")
        for step in ("1. Import", "2. Indexation", "3. Recherche hybride", "Résumé court", "Résumé moyen",
                     "Résumé détaillé", "Données de démonstration supprimées"):
            self.assertIn(step, output)
        self.assertNotIn("5. QCM", output)
        self.assertFalse(User.objects.exists())
        self.assertFalse(CourseDocument.objects.exists())

    def test_with_llm_generates_quiz_and_chat_answers(self):
        with patch("quizzes.services.generation.get_llm_client", return_value=QuizLLM([questions_json(3)])), \
             patch("chatbot.services.rag.get_llm_client", return_value=ChatLLM("Pour éviter d'improviser [1].")):
            output = self.run_demo()
        self.assertIn("5. QCM", output)
        self.assertIn("<- bonne réponse", output)
        self.assertIn("Pour éviter d'improviser", output)
        self.assertIn("Chatbot : Quelle est la capitale de l'Australie ?", output)
        self.assertFalse(Quiz.objects.exists())  # supprimé avec le cours
        self.assertFalse(User.objects.exists())

    def test_keep_option_preserves_the_demo_account(self):
        output = self.run_demo("--sans-llm", "--garder")
        self.assertIn("conservés", output)
        self.assertEqual(CourseDocument.objects.count(), 1)
        CourseDocument.objects.get().delete()

    def test_unknown_file_is_refused(self):
        with self.assertRaisesMessage(CommandError, "Fichier introuvable"):
            self.run_demo("--fichier", "inexistant.docx")
