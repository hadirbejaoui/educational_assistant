import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import CourseDocument, DocumentPage
from courses.services.data import PageData

from .models import Summary
from .services.errors import SummaryError
from .services.providers.base import BaseSummaryProvider
from .services.providers.extractive import ExtractiveProvider
from .services.sections import Section, build_sections
from .services.summarization import build_summary, generate_summary

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


class FakeProvider(BaseSummaryProvider):
    """Fournisseur de test : garde les N premiers mots et note chaque appel."""

    name = "fake"
    model_name = "fake-1"

    def __init__(self):
        self.calls = []

    def summarize(self, text, max_words):
        self.calls.append((text, max_words))
        return " ".join(text.split()[:max_words])


class SectionTests(SimpleTestCase):
    def test_small_pages_are_merged_until_limit(self):
        pages = [PageData(n, "x" * 40) for n in (1, 2, 3)]
        sections = build_sections(pages, 100)
        self.assertEqual(len(sections), 2)
        self.assertEqual((sections[0].page_start, sections[0].page_end), (1, 2))
        self.assertEqual((sections[1].page_start, sections[1].page_end), (3, 3))

    def test_long_page_is_split(self):
        pages = [PageData(1, ("mot " * 63).strip())]
        sections = build_sections(pages, 100)
        self.assertGreaterEqual(len(sections), 3)
        self.assertTrue(all(len(s.text) <= 100 for s in sections))
        self.assertTrue(all(s.page_start == 1 for s in sections))

    def test_empty_pages_are_ignored(self):
        pages = [PageData(1, ""), PageData(2, "   "), PageData(3, "texte")]
        sections = build_sections(pages, 100)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].page_start, 3)


class HierarchyTests(SimpleTestCase):
    def _sections(self, count, words=20):
        text = " ".join(["mot"] * words)
        return [Section(text, n, n) for n in range(1, count + 1)]

    def test_short_summary_ends_with_final_reduction(self):
        provider = FakeProvider()
        result = build_summary(self._sections(4), "short", provider, 1800)
        self.assertTrue(all(words == 30 for _, words in provider.calls[:4]))
        self.assertEqual(provider.calls[-1][1], 70)
        self.assertLessEqual(len(result.split()), 70)

    def test_detailed_summary_has_no_final_reduction(self):
        provider = FakeProvider()
        result = build_summary(self._sections(2), "detailed", provider, 1800)
        self.assertTrue(all(words == 120 for _, words in provider.calls))
        self.assertIn("Page 1", result)
        self.assertIn("Page 2", result)

    def test_many_sections_trigger_intermediate_rounds(self):
        provider = FakeProvider()
        sections = self._sections(20, words=40)
        result = build_summary(sections, "short", provider, 300)
        self.assertGreater(len(provider.calls), len(sections) + 1)
        self.assertLessEqual(len(result.split()), 70)

    def test_unknown_level_raises(self):
        with self.assertRaises(SummaryError):
            build_summary(self._sections(1), "nope", FakeProvider(), 1800)


class ExtractiveTests(SimpleTestCase):
    def test_respects_word_budget(self):
        text = " ".join(
            f"Phrase numéro {i} qui parle de physique quantique et d'énergie." for i in range(10)
        )
        result = ExtractiveProvider().summarize(text, 25)
        self.assertTrue(result)
        self.assertLessEqual(len(result.split()), 25)

    def test_short_text_is_returned_as_is(self):
        self.assertEqual(ExtractiveProvider().summarize("Un texte court.", 50), "Un texte court.")


def make_document(owner, title="Cours", status=CourseDocument.Status.READY,
                  pages=("Premier paragraphe du cours sur les maths.", "Deuxième page.")):
    document = CourseDocument.objects.create(
        owner=owner, title=title, file=SimpleUploadedFile("c.txt", b"x"),
        file_type="txt", file_size=1, status=status, page_count=len(pages),
    )
    for number, text in enumerate(pages, start=1):
        DocumentPage.objects.create(document=document, page_number=number, text=text)
    return document


@override_settings(MEDIA_ROOT=TEMP_MEDIA, SUMMARY_PROVIDER="extractive")
class GenerationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)

    def test_generate_creates_summary(self):
        document = make_document(self.alice)
        summary = generate_summary(document, "medium", FakeProvider())
        self.assertEqual(summary.level, "medium")
        self.assertEqual(summary.provider, "fake")
        self.assertTrue(summary.content)

    def test_regenerate_replaces_existing(self):
        document = make_document(self.alice)
        generate_summary(document, "short", FakeProvider())
        generate_summary(document, "short", FakeProvider())
        self.assertEqual(Summary.objects.filter(document=document).count(), 1)

    def test_empty_document_raises(self):
        document = make_document(self.alice, pages=("",))
        with self.assertRaises(SummaryError):
            generate_summary(document, "short", FakeProvider())


@override_settings(MEDIA_ROOT=TEMP_MEDIA, SUMMARY_PROVIDER="extractive")
class SummaryViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)

    def test_pages_require_login(self):
        self.client.logout()
        response = self.client.get(reverse("summaries:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_only_own_summaries(self):
        mine = make_document(self.alice, "Cours Alice")
        theirs = make_document(self.bob, "Cours Bob")
        generate_summary(mine, "short", FakeProvider())
        generate_summary(theirs, "short", FakeProvider())
        response = self.client.get(reverse("summaries:list"))
        self.assertContains(response, "Cours Alice")
        self.assertNotContains(response, "Cours Bob")

    def test_cannot_open_other_users_document(self):
        bob_doc = make_document(self.bob)
        response = self.client.get(reverse("summaries:document", args=[bob_doc.pk]))
        self.assertEqual(response.status_code, 404)

    def test_generate_requires_post(self):
        doc = make_document(self.alice)
        response = self.client.get(reverse("summaries:generate", args=[doc.pk, "short"]))
        self.assertEqual(response.status_code, 405)

    def test_generate_creates_summary(self):
        doc = make_document(self.alice)
        self.client.post(reverse("summaries:generate", args=[doc.pk, "medium"]))
        self.assertTrue(Summary.objects.filter(document=doc, level="medium").exists())

    def test_generate_refused_when_document_not_ready(self):
        doc = make_document(self.alice, status=CourseDocument.Status.FAILED)
        self.client.post(reverse("summaries:generate", args=[doc.pk, "short"]))
        self.assertEqual(Summary.objects.count(), 0)

    def test_invalid_level_gives_404(self):
        doc = make_document(self.alice)
        response = self.client.post(reverse("summaries:generate", args=[doc.pk, "enorme"]))
        self.assertEqual(response.status_code, 404)