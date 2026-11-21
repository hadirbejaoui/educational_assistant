import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from core.templatetags.ui import rich_text
from courses.models import CourseDocument, DocumentPage
from courses.services.data import PageData

from .models import Summary
from .services.errors import SummaryError, SummaryProviderError
from .services.providers.base import BaseSummaryProvider
from .services.providers.extractive import ExtractiveProvider
from .services.sections import Section, build_sections
from .services.summarization import build_summary, generate_summary, section_limit, target_words

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()
LEVEL_ORDER = ("short", "medium", "detailed")


def word_count(text):
    return len(text.split())


class FakeProvider(BaseSummaryProvider):
    """Fournisseur de test : garde les N premiers mots et note chaque appel."""

    name = "fake"
    model_name = "fake-1"

    def __init__(self):
        self.calls = []
        self.levels = []

    def summarize(self, text, max_words, level="medium"):
        self.calls.append((text, max_words))
        self.levels.append(level)
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


class TargetLengthTests(SimpleTestCase):
    def test_longer_level_means_longer_summary(self):
        for source in (500, 3000, 20000):
            targets = [target_words(level, source) for level in LEVEL_ORDER]
            self.assertLess(targets[0], targets[1], source)
            self.assertLess(targets[1], targets[2], source)

    def test_length_grows_with_the_course(self):
        for level in LEVEL_ORDER:
            self.assertLess(target_words(level, 2000), target_words(level, 8000))

    def test_summary_is_never_longer_than_the_course(self):
        self.assertEqual([target_words(level, 13) for level in LEVEL_ORDER], [13, 13, 13])

    def test_unknown_level_raises(self):
        with self.assertRaises(SummaryError):
            target_words("nope", 100)

    def test_detailed_level_uses_shorter_sections(self):
        provider = FakeProvider()
        provider.section_chars = 6000
        self.assertEqual(section_limit(provider, "medium"), 6000)
        self.assertEqual(section_limit(provider, "detailed"), 3000)


class HierarchyTests(SimpleTestCase):
    """Les six combinaisons document court/long × niveau court/moyen/détaillé, et les cas limites."""

    def _sections(self, count, words=20):
        return [
            Section(" ".join(f"m{n}_{i}" for i in range(words)), n, n)
            for n in range(1, count + 1)
        ]

    def _summaries(self, sections, limit=6000):
        results = {}
        for level in LEVEL_ORDER:
            provider = FakeProvider()
            results[level] = (build_summary(sections, level, provider, limit), provider)
        return results

    def test_short_document_three_levels(self):
        results = self._summaries(self._sections(1, words=500))
        lengths = [word_count(results[level][0]) for level in LEVEL_ORDER]
        self.assertEqual(lengths, [40, 120, 250])  # bornes minimales de chaque niveau
        for level in LEVEL_ORDER:
            provider = results[level][1]
            self.assertEqual(len(provider.calls), 1)  # une seule section : un seul appel
            self.assertEqual(provider.levels, [level])  # le style du niveau est transmis

    def test_long_document_three_levels(self):
        results = self._summaries(self._sections(10, words=600))  # 6 000 mots
        short, medium, detailed = (word_count(results[level][0]) for level in LEVEL_ORDER)
        self.assertLess(short, medium)
        self.assertLess(medium, detailed)
        self.assertEqual(short, target_words("short", 6000))
        self.assertEqual(medium, target_words("medium", 6000))
        self.assertGreaterEqual(detailed, target_words("detailed", 6000) * 0.9)

    def test_long_document_medium_ends_with_a_final_synthesis(self):
        provider = FakeProvider()
        build_summary(self._sections(10, words=600), "medium", provider, 6000)
        target = target_words("medium", 6000)
        self.assertEqual(len(provider.calls), 11)  # 10 sections + synthèse finale
        self.assertEqual(provider.calls[-1][1], target)
        # chaque section garde plus de matière que sa part finale (SUMMARY_MAP_EXPANSION)
        self.assertGreater(provider.calls[0][1], target / 10)

    def test_detailed_keeps_every_part_in_course_order(self):
        provider = FakeProvider()
        result = build_summary(self._sections(3, words=600), "detailed", provider, 6000)
        self.assertEqual(len(provider.calls), 3)  # pas de synthèse finale qui perdrait des détails
        positions = [result.index(f"## Page {n}") for n in (1, 2, 3)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("m3_0", result)  # le contenu de la dernière section est conservé

    def test_sections_get_a_budget_proportional_to_their_size(self):
        provider = FakeProvider()
        sections = [Section(" ".join(["a"] * 900), 1, 1), Section(" ".join(["b"] * 300), 2, 2)]
        build_summary(sections, "detailed", provider, 6000)
        big, small = provider.calls[0][1], provider.calls[1][1]
        self.assertAlmostEqual(big / small, 3, delta=0.1)

    def test_many_sections_trigger_intermediate_rounds(self):
        provider = FakeProvider()
        sections = self._sections(20, words=40)
        result = build_summary(sections, "short", provider, 300)
        self.assertGreater(len(provider.calls), len(sections) + 1)
        self.assertLessEqual(word_count(result), target_words("short", 800))

    def test_text_beyond_the_context_is_never_sent_at_once(self):
        provider = FakeProvider()
        sections = build_sections([PageData(n, "mot " * 400) for n in range(1, 31)], 1800)
        build_summary(sections, "medium", provider, 1800)
        self.assertGreater(len(sections), 1)
        self.assertTrue(all(len(text) <= 1800 for text, _ in provider.calls))

    def test_text_without_punctuation(self):
        sections = [Section("mot " * 3000, 1, 4), Section("autre " * 3000, 5, 8)]
        for level in LEVEL_ORDER:
            result = build_summary(sections, level, ExtractiveProvider(), 6000)
            self.assertTrue(result)
            self.assertLessEqual(word_count(result), target_words(level, 6000) + 10)

    def test_unknown_level_raises(self):
        with self.assertRaises(SummaryError):
            build_summary(self._sections(1), "nope", FakeProvider(), 1800)

    def test_provider_returning_nothing(self):
        class Empty(FakeProvider):
            def summarize(self, text, max_words, level="medium"):
                return "  "

        with self.assertRaisesMessage(SummaryError, "aucun résumé"):
            build_summary(self._sections(2), "short", Empty(), 1800)


class RichTextTests(SimpleTestCase):
    def test_headings_lists_bold_and_paragraphs(self):
        html = rich_text(
            "## Pages 1 à 2\n\n### La SARL\nUne **société** commerciale.\n"
            "- capital libre\n- 2 à 50 associés"
        )
        self.assertIn("<h3>Pages 1 à 2</h3>", html)
        self.assertIn("<h4>La SARL</h4>", html)
        self.assertIn("<p>Une <strong>société</strong> commerciale.</p>", html)
        self.assertIn("<ul><li>capital libre</li><li>2 à 50 associés</li></ul>", html)

    def test_generated_text_is_escaped(self):
        html = rich_text("### <script>alert(1)</script>\n<img src=x onerror=alert(1)>")
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_doubled_heading_marks_are_tolerated(self):
        self.assertEqual(rich_text("### ### La SNC"), "<h4>La SNC</h4>")

    def test_old_plain_summaries_still_display(self):
        self.assertEqual(rich_text("Pages 1 à 4 :\nTexte."), "<p>Pages 1 à 4 :<br>Texte.</p>")


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
        with self.assertRaisesMessage(SummaryError, "aucun texte à résumer"):
            generate_summary(document, "short", FakeProvider())

    def test_three_levels_stored_with_growing_length(self):
        pages = tuple("Le cours explique une notion importante. " * 80 for _ in range(4))
        document = make_document(self.alice, pages=pages)
        lengths = [
            word_count(generate_summary(document, level, FakeProvider()).content)
            for level in LEVEL_ORDER
        ]
        self.assertLess(lengths[0], lengths[1])
        self.assertLess(lengths[1], lengths[2])


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

    def test_cannot_open_or_generate_on_other_users_document(self):
        bob_doc = make_document(self.bob)
        self.assertEqual(self.client.get(reverse("summaries:document", args=[bob_doc.pk])).status_code, 404)
        response = self.client.post(reverse("summaries:generate", args=[bob_doc.pk, "detailed"]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Summary.objects.filter(document=bob_doc).exists())

    def test_summary_of_one_account_never_overwrites_another(self):
        # Même titre, même niveau : chaque résumé reste attaché au cours de son propriétaire
        alice_doc = make_document(self.alice, "Cours", pages=("Le cours d'Alice parle de chimie.",))
        bob_doc = make_document(self.bob, "Cours", pages=("Le cours de Bob parle d'histoire.",))
        bob_summary = generate_summary(bob_doc, "short", FakeProvider())
        self.client.post(reverse("summaries:generate", args=[alice_doc.pk, "short"]))
        bob_summary.refresh_from_db()
        self.assertIn("histoire", bob_summary.content)
        self.assertIn("chimie", Summary.objects.get(document=alice_doc, level="short").content)
        self.assertEqual(Summary.objects.count(), 2)

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

    def test_unavailable_llm_gives_a_clear_message(self):
        doc = make_document(self.alice)
        with patch("summaries.services.summarization.get_provider",
                   side_effect=SummaryProviderError("Impossible de joindre le LLM.")):
            response = self.client.post(
                reverse("summaries:generate", args=[doc.pk, "detailed"]), follow=True
            )
        self.assertContains(response, "Impossible de joindre le LLM.")
        self.assertFalse(Summary.objects.exists())

    def test_empty_document_gives_an_explicit_message(self):
        doc = make_document(self.alice, pages=("   ",))
        response = self.client.post(reverse("summaries:generate", args=[doc.pk, "medium"]), follow=True)
        self.assertContains(response, "aucun texte à résumer")

    def test_invalid_level_gives_404(self):
        doc = make_document(self.alice)
        response = self.client.post(reverse("summaries:generate", args=[doc.pk, "enorme"]))
        self.assertEqual(response.status_code, 404)
