"""Tests complémentaires (phase 10, mesurés avec coverage.py) : chargement du modèle
d'embeddings, extraction PDF/TXT, commandes de gestion."""

import io
import shutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User

from .models import CourseDocument
from .services import embeddings
from .services.data import ExtractionError
from .services.embeddings import EmbeddingError, SentenceTransformerEmbedder, get_embedder
from .services.extraction import extract_pages
from .test_embeddings import FakeEmbedder, make_document

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


class FakeModel:
    """Remplace SentenceTransformer : vecteurs de la dimension demandée, textes mémorisés."""

    instances = []

    def __init__(self, name, dimension=384, fail_encode=False):
        self.name, self.dimension, self.fail_encode = name, dimension, fail_encode
        self.encoded = []
        FakeModel.instances.append(self)

    def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar):
        if self.fail_encode:
            raise RuntimeError("mémoire insuffisante")
        assert normalize_embeddings is True  # cosinus = produit scalaire
        self.encoded.extend(texts)
        return np.ones((len(texts), self.dimension), dtype=np.float32) / np.sqrt(self.dimension)


def fake_library(**kwargs):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda name: FakeModel(name, **kwargs)
    return module


class SentenceTransformerEmbedderTests(SimpleTestCase):
    def setUp(self):
        embeddings._LOADED.clear()
        FakeModel.instances.clear()

    def tearDown(self):
        embeddings._LOADED.clear()

    def test_prefixes_and_dimensions(self):
        with patch.dict(sys.modules, {"sentence_transformers": fake_library()}):
            embedder = SentenceTransformerEmbedder("e5-test")
            vectors = embedder.embed_passages(["texte A", "texte B"])
            query = embedder.embed_query("question")
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(query), 384)
        self.assertEqual(FakeModel.instances[0].encoded, ["passage: texte A", "passage: texte B", "query: question"])

    def test_model_is_loaded_only_once(self):
        with patch.dict(sys.modules, {"sentence_transformers": fake_library()}):
            SentenceTransformerEmbedder("e5-test").embed_query("a")
            SentenceTransformerEmbedder("e5-test").embed_query("b")
        self.assertEqual(len(FakeModel.instances), 1)

    def test_wrong_dimension_is_refused(self):
        with patch.dict(sys.modules, {"sentence_transformers": fake_library(dimension=768)}):
            with self.assertRaisesMessage(EmbeddingError, "768 dimensions, 384 attendues"):
                SentenceTransformerEmbedder("gros-modele").embed_query("a")

    def test_encoding_failure_is_reported(self):
        with patch.dict(sys.modules, {"sentence_transformers": fake_library(fail_encode=True)}):
            with self.assertRaisesMessage(EmbeddingError, "Échec du calcul"):
                SentenceTransformerEmbedder("e5-test").embed_query("a")

    def test_unloadable_model(self):
        module = types.ModuleType("sentence_transformers")

        def broken(name):
            raise OSError("pas de connexion")

        module.SentenceTransformer = broken
        with patch.dict(sys.modules, {"sentence_transformers": module}):
            with self.assertRaisesMessage(EmbeddingError, "Impossible de charger"):
                SentenceTransformerEmbedder("introuvable").embed_query("a")

    def test_missing_library(self):
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with self.assertRaisesMessage(EmbeddingError, "pas installée"):
                SentenceTransformerEmbedder("e5-test").embed_query("a")

    @override_settings(EMBEDDING_MODEL_NAME="mon-modele")
    def test_get_embedder_uses_settings(self):
        self.assertEqual(get_embedder().model_name, "mon-modele")


class ExtractionTests(SimpleTestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _pdf(self, pages, toc=None, password=None):
        doc = pymupdf.open()
        for text in pages:
            doc.new_page().insert_text((72, 72), text)
        if toc:
            doc.set_toc(toc)
        path = self.folder / "c.pdf"
        if password:
            doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password + "!")
        else:
            doc.save(path)
        doc.close()
        return path

    def test_chapters_come_from_the_table_of_contents(self):
        path = self._pdf(["Intro", "Suite", "Autre"], toc=[[1, "Introduction", 1], [1, "Chapitre deux", 3]])
        pages = extract_pages(path, "pdf")
        self.assertEqual([p.chapter for p in pages], ["Introduction", "Introduction", "Chapitre deux"])

    def test_chapters_are_detected_without_table_of_contents(self):
        pages = extract_pages(self._pdf(["Chapitre 1 Les bases\ntexte", "suite du texte", "Partie II : Avancé"]), "pdf")
        self.assertEqual(pages[1].chapter, "Chapitre 1 Les bases")
        self.assertEqual(pages[2].chapter, "Partie II : Avancé")

    def test_password_protected_pdf_is_refused(self):
        with self.assertRaisesMessage(ExtractionError, "mot de passe"):
            extract_pages(self._pdf(["secret"], password="motdepasse"), "pdf")

    def test_txt_in_windows_encoding(self):
        path = self.folder / "c.txt"
        path.write_bytes("Société générale, été".encode("cp1252"))
        self.assertIn("Société générale, été", extract_pages(path, "txt")[0].text)

    def test_txt_form_feed_makes_pages(self):
        path = self.folder / "c.txt"
        path.write_text("Page un\fPage deux\fPage trois", encoding="utf-8")
        self.assertEqual(len(extract_pages(path, "txt")), 3)

    def test_long_txt_is_split_into_virtual_pages(self):
        path = self.folder / "c.txt"
        path.write_text("\n\n".join(["Paragraphe " + "mot " * 200] * 10), encoding="utf-8")
        self.assertGreater(len(extract_pages(path, "txt")), 3)

    def test_unknown_type_and_unreadable_file(self):
        with self.assertRaises(ExtractionError):
            extract_pages(self.folder / "c.docx", "docx")
        with self.assertRaises(ExtractionError):
            extract_pages(self.folder / "absent.txt", "txt")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ManagementCommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)

    def _run(self, *args, **kwargs):
        out = io.StringIO()
        call_command(*args, stdout=out, stderr=io.StringIO(), **kwargs)
        return out.getvalue()

    def test_index_documents(self):
        document = make_document(self.alice)
        with patch("courses.management.commands.index_documents.get_embedder", return_value=FakeEmbedder()):
            self.assertIn("3 passage(s) indexé(s)", self._run("index_documents"))
            self.assertIn("0 passage(s) indexé(s)", self._run("index_documents", document=document.pk))
            self.assertIn("3 passage(s) indexé(s)", self._run("index_documents", force=True))

    def test_rag_grep(self):
        document = make_document(self.alice)
        output = self._run("rag_grep", document.pk, "capitale")
        self.assertIn("1 passage(s)", output)
        self.assertIn("p.2", output)

    def test_reprocess_documents(self):
        document = CourseDocument.objects.create(
            owner=self.alice, title="Cours", file=SimpleUploadedFile("c.txt", "Bonjour le monde.\n\nDeuxième paragraphe.".encode()),
            file_type="txt", file_size=40, status=CourseDocument.Status.READY,
        )
        with patch("courses.management.commands.reprocess_documents.get_embedder", return_value=FakeEmbedder()):
            output = self._run("reprocess_documents", document=document.pk)
        self.assertIn("Cours : 0 -> 1 passage(s) indexé(s)", output)
        self.assertTrue(document.chunks.filter(embedding__isnull=False).exists())
