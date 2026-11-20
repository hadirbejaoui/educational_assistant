"""Tests des commandes d'évaluation et des réglages de production (phase 10)."""

import csv
import importlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User
from courses.services.embeddings import index_document
from courses.test_embeddings import FakeEmbedder, make_document

from .tests import FakeLLM

PASSWORD = "Str0ng-Pass!2026"
TEMP_DIR = tempfile.mkdtemp()


def run(*args, **kwargs):
    out = io.StringIO()
    call_command(*args, stdout=out, stderr=io.StringIO(), **kwargs)
    return out.getvalue()


@override_settings(MEDIA_ROOT=TEMP_DIR, RAG_MIN_SCORE=0.3)
class EvaluationCommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self):
        alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.embedder = FakeEmbedder()
        self.document = make_document(alice)  # pages 1 à 3 : chat, capitale, moteur
        index_document(self.document, self.embedder)
        self.file = Path(TEMP_DIR) / "questions.json"
        self.file.write_text(json.dumps({"courses": [{
            "document_id": self.document.pk,
            "questions": [
                {"question": "la capitale de la France", "expected_pages": [2]},
                {"question": "le chat mange", "expected_pages": [1], "expected_text": "croquettes"},
            ],
            "out_of_scope": ["recette de tarte aux pommes"],
        }]}), encoding="utf-8")

    def test_rag_eval_courses_reports_and_warns_on_small_samples(self):
        with patch("chatbot.management.commands.rag_eval_courses.get_embedder", return_value=self.embedder):
            output = run("rag_eval_courses", file=str(self.file), details=True)
        self.assertIn("2 questions avec réponse | 1 hors cours", output)
        self.assertIn("=== Recommandation ===", output)
        self.assertIn("ÉCHANTILLON TROP PETIT", output)
        self.assertIn("rang 1", output)

    def test_rag_eval_courses_rejects_an_invalid_file(self):
        self.file.write_text(json.dumps({"courses": [{"document_id": "x"}]}), encoding="utf-8")
        with self.assertRaises(CommandError):
            run("rag_eval_courses", file=str(self.file))

    def test_rag_eval_courses_requires_an_indexed_document(self):
        self.document.chunks.update(embedding_model="autre")
        with patch("chatbot.management.commands.rag_eval_courses.get_embedder", return_value=self.embedder):
            with self.assertRaisesMessage(CommandError, "n'est pas indexé"):
                run("rag_eval_courses", file=str(self.file))

    def test_faithfulness_sheet_then_score(self):
        sheet = Path(TEMP_DIR) / "fidelite.csv"
        with patch("chatbot.management.commands.rag_faithfulness.get_embedder", return_value=self.embedder), \
             patch("chatbot.management.commands.rag_faithfulness.get_llm_client", return_value=FakeLLM("Réponse [1].")):
            output = run("rag_faithfulness", file=str(self.file), sample=2, out=str(sheet))
        self.assertIn("Grille écrite", output)
        with open(sheet, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["sources_citees"])
        rows[0]["appuyee"], rows[1]["appuyee"] = "oui", "non"
        with open(sheet, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        score = run("rag_faithfulness", score=str(sheet))
        self.assertIn("2 réponses relues", score)
        self.assertIn("50.0%", score)

    def test_faithfulness_score_refuses_unknown_values(self):
        sheet = Path(TEMP_DIR) / "mauvais.csv"
        sheet.write_text("id;appuyee\n1;peut-être\n", encoding="utf-8-sig")
        with self.assertRaisesMessage(CommandError, "Valeurs inconnues"):
            run("rag_faithfulness", score=str(sheet))

    def test_rag_diagnose(self):
        with patch("chatbot.management.commands.rag_diagnose.get_embedder", return_value=self.embedder):
            output = run("rag_diagnose", self.document.pk, "capitale France", find="Paris")
        self.assertIn("REPONSE", output)
        self.assertIn("rang final", output)


class SyntheticEvaluationCommandTests(SimpleTestCase):
    def test_rag_evaluate_compares_three_modes(self):
        with patch("chatbot.management.commands.rag_evaluate.get_embedder", return_value=FakeEmbedder()):
            output = run("rag_evaluate", k=3, weights="1", pooled=True)
        for mode in ("dense", "bm25", "hybrid"):
            self.assertIn(mode, output)
        self.assertIn("Refus par seuil", output)


class ProductionSettingsTests(SimpleTestCase):
    """config.settings_production refuse de démarrer avec une configuration dangereuse."""

    STRONG_KEY = "k" * 60

    def _load(self, **env):
        values = {"DJANGO_SECRET_KEY": self.STRONG_KEY, "DJANGO_ALLOWED_HOSTS": "exemple.tn", "DJANGO_HTTPS": "False"}
        values.update(env)
        with patch.dict(os.environ, values):
            import config.settings as base
            importlib.reload(base)  # relit DJANGO_SECRET_KEY
            try:
                import config.settings_production as production
                return importlib.reload(production)
            finally:
                importlib.reload(base)

    def test_secure_defaults(self):
        production = self._load()
        self.assertFalse(production.DEBUG)
        self.assertEqual(production.ALLOWED_HOSTS, ["exemple.tn"])
        self.assertEqual(production.STORAGES["staticfiles"]["BACKEND"].rsplit(".", 1)[-1],
                         "ManifestStaticFilesStorage" if "whitenoise" not in production.STORAGES["staticfiles"]["BACKEND"]
                         else "CompressedManifestStaticFilesStorage")
        self.assertFalse(production.SESSION_COOKIE_SECURE)  # HTTP local : cookies non « Secure »
        self.assertEqual(production.LOGGING["handlers"]["file"]["class"], "logging.handlers.RotatingFileHandler")

    def test_https_turns_on_secure_cookies_and_hsts(self):
        production = self._load(DJANGO_HTTPS="True")
        self.assertTrue(production.SESSION_COOKIE_SECURE)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
        self.assertTrue(production.SECURE_SSL_REDIRECT)
        self.assertEqual(production.SECURE_HSTS_SECONDS, 3600)

    def test_missing_hosts_or_weak_key_are_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS"):
            self._load(DJANGO_ALLOWED_HOSTS="")
        with self.assertRaisesMessage(ImproperlyConfigured, "trop faible"):
            self._load(DJANGO_SECRET_KEY="django-insecure-courte")
