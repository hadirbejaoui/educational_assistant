import math
import shutil
import tempfile
import zlib
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .models import CourseDocument, DocumentChunk
from .services.embeddings import BaseEmbedder, index_document
from .services.retrieval import lexical_rank, search_chunks

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()
DIM = 384


class FakeEmbedder(BaseEmbedder):
    """Plongement « sac de mots » : deux textes qui partagent des mots sont proches."""

    name = "fake"
    model_name = "fake-bow"

    def _vector(self, text):
        vector = [0.0] * DIM
        for token in text.lower().split():
            vector[zlib.crc32(token.encode()) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_passages(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


TEXTS = [
    "le chat mange des croquettes",
    "la capitale de la France est Paris",
    "le moteur diesel consomme du carburant",
]


def make_document(owner, title="Cours", texts=TEXTS):
    document = CourseDocument.objects.create(
        owner=owner, title=title, file=SimpleUploadedFile("c.txt", b"x"),
        file_type="txt", file_size=1, status=CourseDocument.Status.READY,
    )
    for i, text in enumerate(texts):
        DocumentChunk.objects.create(
            document=document, chunk_index=i, text=text,
            page_start=i + 1, page_end=i + 1, char_count=len(text),
        )
    return document


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class IndexingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.document = make_document(self.alice)
        self.embedder = FakeEmbedder()

    def test_index_fills_every_chunk(self):
        self.assertEqual(index_document(self.document, self.embedder), 3)
        for chunk in self.document.chunks.all():
            self.assertEqual(len(chunk.embedding), DIM)
            self.assertEqual(chunk.embedding_model, "fake-bow")

    def test_second_index_does_nothing_unless_forced(self):
        index_document(self.document, self.embedder)
        self.assertEqual(index_document(self.document, self.embedder), 0)
        self.assertEqual(index_document(self.document, self.embedder, force=True), 3)

    def test_vectors_of_another_model_are_recomputed(self):
        index_document(self.document, self.embedder)
        self.document.chunks.update(embedding_model="ancien-modele")
        self.assertEqual(index_document(self.document, self.embedder), 3)

    def test_hnsw_index_exists(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'chunk_embedding_hnsw'")
            self.assertIsNotNone(cursor.fetchone())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SearchTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.embedder = FakeEmbedder()
        self.document = make_document(self.alice)
        index_document(self.document, self.embedder)

    def test_most_relevant_chunk_comes_first(self):
        hits = search_chunks(self.document, "quelle est la capitale de la France", embedder=self.embedder)
        self.assertEqual(len(hits), 3)
        self.assertIn("Paris", hits[0].chunk.text)
        self.assertGreater(hits[0].score, hits[1].score)

    def test_k_limits_results(self):
        hits = search_chunks(self.document, "chat", k=1, embedder=self.embedder)
        self.assertEqual(len(hits), 1)

    def test_search_stays_inside_the_document(self):
        other = make_document(self.bob, "Cours Bob")
        index_document(other, self.embedder)
        hits = search_chunks(self.document, "capitale France Paris", embedder=self.embedder)
        self.assertTrue(all(hit.chunk.document_id == self.document.id for hit in hits))

    def test_unindexed_document_gives_no_results(self):
        fresh = make_document(self.alice, "Neuf")
        self.assertEqual(search_chunks(fresh, "chat", embedder=self.embedder), [])

    def test_empty_query_gives_no_results(self):
        self.assertEqual(search_chunks(self.document, "   ", embedder=self.embedder), [])

    def test_vectors_of_another_model_are_ignored(self):
        self.document.chunks.update(embedding_model="ancien-modele")
        self.assertEqual(search_chunks(self.document, "chat", embedder=self.embedder), [])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class EmbeddingViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)
        self.document = make_document(self.alice)
        self.bob_doc = make_document(self.bob, "Cours Bob")

    def test_index_requires_post(self):
        response = self.client.get(reverse("courses:index", args=[self.document.pk]))
        self.assertEqual(response.status_code, 405)

    def test_index_view_indexes_chunks(self):
        with patch("courses.views.get_embedder", return_value=FakeEmbedder()):
            self.client.post(reverse("courses:index", args=[self.document.pk]))
        self.assertEqual(self.document.chunks.filter(embedding__isnull=False).count(), 3)

    def test_cannot_index_other_users_document(self):
        with patch("courses.views.get_embedder", return_value=FakeEmbedder()):
            response = self.client.post(reverse("courses:index", args=[self.bob_doc.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.bob_doc.chunks.filter(embedding__isnull=False).count(), 0)

    def test_search_view_shows_results_with_pages(self):
        embedder = FakeEmbedder()
        index_document(self.document, embedder)
        with patch("courses.views.get_embedder", return_value=embedder):
            response = self.client.get(
                reverse("courses:search", args=[self.document.pk]), {"q": "capitale France"}
            )
        self.assertContains(response, "Paris")
        self.assertContains(response, "page 2")

    def test_cannot_search_other_users_document(self):
        response = self.client.get(reverse("courses:search", args=[self.bob_doc.pk]), {"q": "chat"})
        self.assertEqual(response.status_code, 404)


def axis(a, b):
    vector = [0.0] * DIM
    vector[0], vector[1] = a, b
    return vector


class PinnedEmbedder(BaseEmbedder):
    """Plongements imposés : le classement vectoriel est connu à l'avance."""

    name = "pinned"
    model_name = "pinned"

    def __init__(self, vectors):
        self.vectors = vectors

    def embed_passages(self, texts):
        return [self.vectors[text] for text in texts]

    def embed_query(self, text):
        return self.vectors["QUERY"]


class LexicalTests(SimpleTestCase):
    def _chunks(self, *texts):
        return [SimpleNamespace(id=i, text=t) for i, t in enumerate(texts)]

    def test_acronym_is_found(self):
        chunks = self._chunks("la SARL est une forme", "la SNC est une société en nom collectif", "autre sujet")
        self.assertEqual(lexical_rank(chunks, "C est quoi la SNC ?")[0].id, 1)

    def test_sa_is_not_ignored_as_a_stopword(self):
        chunks = self._chunks("la SA exige un capital", "la SARL est simple")
        self.assertEqual(lexical_rank(chunks, "capital d'une SA")[0].id, 0)

    def test_accents_and_case_are_ignored(self):
        chunks = self._chunks("Société anonyme", "autre")
        self.assertEqual(lexical_rank(chunks, "SOCIETE")[0].id, 0)

    def test_no_match_and_stopwords_only_give_nothing(self):
        chunks = self._chunks("texte quelconque")
        self.assertEqual(lexical_rank(chunks, "zorglub"), [])
        self.assertEqual(lexical_rank(chunks, "c est quoi la ?"), [])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class HybridSearchTests(TestCase):
    def setUp(self):
        alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.texts = ["alpha", "beta", "gamma", "le zorglub est un animal"]
        self.embedder = PinnedEmbedder({
            "QUERY": axis(1, 0), "alpha": axis(1, 0), "beta": axis(1, 0.2),
            "gamma": axis(1, 0.5), self.texts[3]: axis(1, 1.0),  # 4e rang vectoriel
        })
        self.document = make_document(alice, "Hybride", texts=self.texts)
        index_document(self.document, self.embedder)

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=1.0)
    def test_keyword_match_is_promoted_when_enabled(self):
        hits = search_chunks(self.document, "zorglub", k=2, embedder=self.embedder)
        self.assertEqual(hits[0].chunk.text, self.texts[3])
        self.assertAlmostEqual(hits[0].score, 0.7071, places=3)  # score = cosinus, pas le rang

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=0)
    def test_default_order_is_pure_vector_order(self):
        hits = search_chunks(self.document, "zorglub", k=4, embedder=self.embedder)
        self.assertEqual([hit.chunk.text for hit in hits], self.texts)