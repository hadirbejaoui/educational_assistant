import shutil
import tempfile
from unittest.mock import patch

import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .models import CourseDocument, DocumentChunk
from .services.chunking import chunk_pages
from .services.cleaning import clean_text
from .services.data import PageData
from .services.processing import process_document
from .test_embeddings import FakeEmbedder

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


def make_pdf(pages_text):
    """Fabrique un vrai PDF en mémoire (une chaîne par page)."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class CleaningTests(SimpleTestCase):
    def test_hyphenated_word_is_rejoined(self):
        self.assertEqual(clean_text("une informa-\ntion utile"), "une information utile")

    def test_spaces_and_single_newlines_are_collapsed(self):
        self.assertEqual(clean_text("Bonjour   le\nmonde"), "Bonjour le monde")

    def test_paragraphs_are_kept(self):
        self.assertEqual(clean_text("Para un.\n\nPara deux."), "Para un.\n\nPara deux.")

    def test_control_characters_are_removed(self):
        self.assertEqual(clean_text("abc\x00def"), "abcdef")

    def test_ligature_is_normalized(self):
        self.assertEqual(clean_text("ﬁnal"), "final")


class ChunkingTests(SimpleTestCase):
    def setUp(self):
        text = ("mot " * 100).strip()  # 399 caractères
        self.pages = [
            PageData(1, text, "Chapitre 1"),
            PageData(2, text, "Chapitre 2"),
        ]

    def test_chunks_respect_max_size(self):
        chunks = chunk_pages(self.pages, 300, 50)
        self.assertTrue(len(chunks) > 1)
        self.assertTrue(all(len(c.text) <= 300 for c in chunks))

    def test_indexes_are_consecutive(self):
        chunks = chunk_pages(self.pages, 300, 50)
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))

    def test_page_numbers_are_kept(self):
        chunks = chunk_pages(self.pages, 300, 50)
        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[-1].page_end, 2)
        self.assertTrue(all(c.page_start <= c.page_end for c in chunks))

    def test_chapter_follows_the_pages(self):
        chunks = chunk_pages(self.pages, 300, 50)
        self.assertEqual(chunks[0].chapter, "Chapitre 1")
        self.assertEqual(chunks[-1].chapter, "Chapitre 2")

    def test_consecutive_chunks_overlap(self):
        chunks = chunk_pages(self.pages, 300, 50)
        # Le début du passage suivant doit apparaître dans la fin du précédent
        start_of_next = chunks[1].text[:20]
        self.assertIn(start_of_next, chunks[0].text)

    def test_invalid_overlap_raises(self):
        with self.assertRaises(ValueError):
            chunk_pages(self.pages, 100, 100)

    def test_empty_pages_give_no_chunks(self):
        self.assertEqual(chunk_pages([PageData(1, "")], 300, 50), [])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ProcessingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)

    def _make_doc(self, name, data, file_type, owner=None):
        return CourseDocument.objects.create(
            owner=owner or self.alice,
            title=name,
            file=SimpleUploadedFile(name, data),
            file_type=file_type,
            file_size=len(data),
        )

    def test_pdf_is_processed(self):
        data = make_pdf(["Chapitre 1\nBonjour le monde.", "Deuxieme page avec du contenu."])
        doc = process_document(self._make_doc("c.pdf", data, "pdf"))
        self.assertEqual(doc.status, "ready")
        self.assertEqual(doc.page_count, 2)
        self.assertEqual(doc.pages.count(), 2)
        self.assertTrue(doc.chunks.exists())
        self.assertEqual(doc.chunks.first().chapter, "Chapitre 1")

    def test_txt_is_processed(self):
        data = "Bonjour.\n\nDeuxième paragraphe avec accents éàù.".encode("utf-8")
        doc = process_document(self._make_doc("c.txt", data, "txt"))
        self.assertEqual(doc.status, "ready")
        self.assertIn("éàù", doc.chunks.first().text)

    def test_pdf_without_text_fails_cleanly(self):
        doc = process_document(self._make_doc("vide.pdf", make_pdf([""]), "pdf"))
        self.assertEqual(doc.status, "failed")
        self.assertIn("texte", doc.error_message)

    def test_corrupted_pdf_fails_cleanly(self):
        doc = process_document(self._make_doc("casse.pdf", b"%PDF-1.4 abc", "pdf"))
        self.assertEqual(doc.status, "failed")
        self.assertTrue(doc.error_message)

    def test_reprocessing_does_not_duplicate_chunks(self):
        data = make_pdf(["Bonjour le monde."])
        doc = process_document(self._make_doc("c.pdf", data, "pdf"))
        first_count = doc.chunks.count()
        process_document(doc)
        self.assertEqual(doc.chunks.count(), first_count)

    def test_delete_removes_pages_and_chunks(self):
        data = make_pdf(["Bonjour le monde."])
        doc = process_document(self._make_doc("c.pdf", data, "pdf"))
        doc.delete()
        self.assertEqual(DocumentChunk.objects.count(), 0)


# L'import indexe le cours : faux modèle d'embeddings (ni téléchargement ni calcul réel)
@patch("courses.views.get_embedder", new=FakeEmbedder)
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ProcessingViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)

    def test_upload_triggers_processing(self):
        pdf = SimpleUploadedFile("c.pdf", make_pdf(["Bonjour le monde."]))
        self.client.post(reverse("courses:upload"), {"title": "Cours", "file": pdf})
        doc = CourseDocument.objects.get(title="Cours")
        self.assertEqual(doc.status, "ready")
        self.assertTrue(doc.chunks.exists())
        self.assertFalse(doc.chunks.filter(embedding__isnull=True).exists())  # indexé dès l'import

    def test_reprocess_requires_post(self):
        doc = CourseDocument.objects.create(
            owner=self.alice, title="x", file=SimpleUploadedFile("c.pdf", make_pdf(["Salut."])),
            file_type="pdf", file_size=10,
        )
        response = self.client.get(reverse("courses:reprocess", args=[doc.pk]))
        self.assertEqual(response.status_code, 405)

    def test_cannot_reprocess_other_users_document(self):
        doc = CourseDocument.objects.create(
            owner=self.bob, title="x", file=SimpleUploadedFile("c.pdf", make_pdf(["Salut."])),
            file_type="pdf", file_size=10,
        )
        response = self.client.post(reverse("courses:reprocess", args=[doc.pk]))
        self.assertEqual(response.status_code, 404)