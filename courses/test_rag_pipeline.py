"""Tests du pipeline RAG générique : nettoyage, découpage, BM25, RRF, évaluation.

Les données couvrent plusieurs matières (droit, informatique, mathématiques,
data science) en français et en anglais : aucun test ne dépend d'un seul cours,
et aucun dictionnaire de sigles propre à une matière n'est utilisé.
"""

import math
import shutil
import tempfile
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User

from .models import CourseDocument
from .services import eval_corpus, retrieval
from .services.chunking import _sentence_ends, chunk_pages
from .services.cleaning import clean_text, strip_repeated_lines
from .services.data import PageData
from .services.embeddings import index_document
from .services.evaluation import (
    build_chunks,
    evaluate,
    index_chunks,
    ndcg_at_k,
    pool_documents,
    precision_at_k,
    rank,
    recall_at_k,
    reciprocal_rank,
    relevant_ids,
)
from .services.processing import process_document
from .services.retrieval import (
    _analyze,
    hybrid_order,
    lexical_rank,
    lexical_scores,
    rrf_fuse,
    search_chunks,
)
from .test_embeddings import FakeEmbedder, PinnedEmbedder, axis, make_document
from .test_services import make_pdf

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


def _chunks(*texts):
    return [SimpleNamespace(id=i, text=t) for i, t in enumerate(texts)]


# --- Nettoyage -------------------------------------------------------------------

class GenericCleaningTests(SimpleTestCase):
    def test_invisible_characters_are_removed(self):
        self.assertEqual(clean_text("infor­mation​ utile﻿"), "information utile")

    def test_accents_and_non_breaking_spaces(self):
        self.assertEqual(clean_text("Éléments : çà où œuvre"), "Éléments : çà où œuvre")

    def test_numbers_formulas_and_symbols_are_kept(self):
        text = "P(A ∩ B) = 0,5 × 10³ ; x ≥ 2 % ; C++ et C# ; E(X) = np ; σ²"
        self.assertEqual(clean_text(text), text)

    def test_heading_stays_on_its_own_line(self):
        raw = (
            "Chapitre 1 : La société en nom collectif\n"
            "La société en nom collectif est une société commerciale dans laquelle tous\n"
            "les associés ont la qualité de commerçant."
        )
        cleaned = clean_text(raw)
        self.assertIn("collectif\nLa société", cleaned)
        self.assertIn("dans laquelle tous les associés", cleaned)

    def test_list_items_are_kept_on_separate_lines(self):
        raw = "Les méthodes HTTP sont :\n- GET pour lire ;\n- POST pour créer ;\n- DELETE pour supprimer."
        self.assertEqual(clean_text(raw).count("\n"), 3)

    def test_wrapped_english_sentence_is_joined(self):
        raw = "Logistic regression is a linear classifier that outputs a\nprobability through the sigmoid function."
        self.assertEqual(
            clean_text(raw),
            "Logistic regression is a linear classifier that outputs a probability through the sigmoid function.",
        )

    def test_hyphenation_with_accents_and_capitals(self):
        self.assertEqual(clean_text("la probabi-\nlité"), "la probabilité")
        self.assertEqual(clean_text("Jean-\nPierre"), "Jean-Pierre")

    def test_repeated_headers_and_page_numbers_are_removed(self):
        bodies = ["La SNC.", "La SARL.", "La SA.", "La SAS."]
        pages = [
            f"Université X - Licence 2 - Droit\n{body}\nDroit des sociétés - {n + 10}\nPage {n} / 4"
            for n, body in enumerate(bodies, start=1)
        ]
        self.assertEqual(strip_repeated_lines(pages), bodies)

    def test_numbered_headings_at_the_top_of_pages_are_kept(self):
        pages = [f"Exercice {n}\nÉnoncé {chr(64 + n)}.\nSuite.\nFin {n}." for n in (1, 2, 4, 7)]
        cleaned = strip_repeated_lines(pages)
        self.assertTrue(all(text.startswith("Exercice") for text in cleaned))

    def test_repeated_line_inside_the_page_is_kept(self):
        pages = [
            f"Titre {n}\nIntro {n}.\nRappel : la loi binomiale.\nCorps {n}.\nfin du texte {n}."
            for n in range(1, 5)
        ]
        self.assertTrue(all("Rappel" in text for text in strip_repeated_lines(pages)))

    def test_short_documents_keep_their_headers(self):
        pages = ["En-tête\nTexte un.", "En-tête\nTexte deux."]
        self.assertEqual(strip_repeated_lines(pages), pages)


# --- Découpage ---------------------------------------------------------------------

SENTENCES = (
    "La variable aléatoire X suit une loi binomiale. Son espérance vaut np. "
    "Sa variance vaut np(1 - p). M. Dupont a démontré ce résultat en cours. "
    "Une API REST est sans état. Chaque requête contient toutes les informations. "
    "La SNC impose une responsabilité indéfinie. Les associés sont solidaires. "
)


class GenericChunkingTests(SimpleTestCase):
    def test_abbreviation_is_not_a_sentence_end(self):
        text = "Selon M. Dupont, la loi est claire. Elle s'applique."
        ends = _sentence_ends(text, 0, len(text))
        self.assertEqual([text[:e].rstrip()[-7:] for e in ends], ["claire."])

    def test_chunks_end_on_sentence_boundaries(self):
        chunks = chunk_pages([PageData(1, SENTENCES * 3)], 300, 60)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks[:-1]:
            self.assertTrue(chunk.text.endswith((".", "!", "?")), chunk.text[-30:])
        self.assertTrue(all(len(c.text) <= 300 for c in chunks))

    def test_overlap_starts_at_a_sentence(self):
        chunks = chunk_pages([PageData(1, SENTENCES * 3)], 300, 60)
        for previous, chunk in zip(chunks, chunks[1:]):
            self.assertTrue(chunk.text[0].isupper(), chunk.text[:30])
            self.assertIn(chunk.text[:15], previous.text)  # le chevauchement existe

    def test_heading_is_kept_with_its_content(self):
        body = "Le contenu du premier chapitre est assez long pour remplir le passage. " * 3
        text = body + "\nChapitre 2 : Loi normale\nLa loi normale est symétrique autour de sa moyenne."
        chunks = chunk_pages([PageData(1, text)], 260, 40)
        for chunk in chunks:
            self.assertFalse(chunk.text.endswith("Chapitre 2 : Loi normale"))
        self.assertTrue(any("Chapitre 2 : Loi normale\nLa loi" in c.text for c in chunks))

    def test_no_tiny_last_chunk(self):
        chunks = chunk_pages([PageData(1, (SENTENCES * 2)[:330].strip())], 300, 50)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(75 <= len(c.text) <= 300 for c in chunks))

    def test_pages_and_chapters_follow_the_text(self):
        pages = [
            PageData(1, "Premier sujet. " * 15, "Chapitre A"),
            PageData(2, "Second sujet. " * 15, "Chapitre B"),
            PageData(3, "Troisième sujet. " * 15, "Chapitre C"),
        ]
        chunks = chunk_pages(pages, 200, 30)
        self.assertEqual((chunks[0].page_start, chunks[0].chapter), (1, "Chapitre A"))
        self.assertEqual((chunks[-1].page_end, chunks[-1].chapter), (3, "Chapitre C"))
        for chunk in chunks:
            self.assertLessEqual(chunk.page_start, chunk.page_end)
            if "Second" in chunk.text and "Premier" not in chunk.text:
                self.assertEqual(chunk.page_start, 2)

    def test_text_without_any_separator_is_still_cut(self):
        chunks = chunk_pages([PageData(1, "x" * 1000)], 300, 50)
        self.assertTrue(all(len(c.text) <= 300 for c in chunks))
        self.assertEqual(sum(len(c.text) for c in chunks) >= 1000, True)


# --- BM25 générique ------------------------------------------------------------------

class GenericLexicalTests(SimpleTestCase):
    def test_no_subject_specific_dictionary(self):
        self.assertFalse(hasattr(retrieval, "_ACRONYM_EXPANSIONS"))

    def test_acronyms_with_and_without_dots(self):
        chunks = _chunks("La S.N.C. est une société de personnes.", "La SARL limite la responsabilité.")
        self.assertEqual(lexical_rank(chunks, "Qu'est-ce que la SNC ?")[0].id, 0)
        chunks = _chunks("La SNC est une société de personnes.", "La SARL limite la responsabilité.")
        self.assertEqual(lexical_rank(chunks, "Qu'est-ce que la S.N.C. ?")[0].id, 0)

    def test_uppercase_acronym_is_not_a_stopword(self):
        chunks = _chunks("Il a vendu sa voiture.", "La SA exige un conseil d'administration.")
        self.assertEqual([c.id for c in lexical_rank(chunks, "Comment fonctionne une SA ?")], [1])
        chunks = _chunks("The IT department manages servers.", "It is a sunny day.")
        self.assertEqual([c.id for c in lexical_rank(chunks, "role of the IT department")], [0])

    def test_all_caps_heading_does_not_turn_stopwords_into_acronyms(self):
        words, _ = _analyze("LA SOCIÉTÉ ANONYME EN DROIT")
        self.assertEqual(words, ("societe", "anonyme", "droit"))

    def test_short_terms_are_kept(self):
        chunks = _chunks(
            "Le langage C donne accès aux pointeurs.",
            "Le C++ ajoute les objets.",
            "Le langage R sert aux statistiques.",
        )
        self.assertEqual(lexical_rank(chunks, "langage C")[0].id, 0)
        self.assertEqual(lexical_rank(chunks, "C++")[0].id, 1)
        self.assertEqual(lexical_rank(chunks, "langage R")[0].id, 2)
        chunks = _chunks("On note n le nombre d'essais et p la probabilité.", "Autre chose.")
        self.assertEqual([c.id for c in lexical_rank(chunks, "que vaut n ?")], [0])

    def test_french_elisions_and_plurals(self):
        chunks = _chunks("Les sociétés et leurs associés.", "L'entreprise individuelle.")
        self.assertEqual(lexical_rank(chunks, "société associé")[0].id, 0)
        self.assertEqual(lexical_rank(chunks, "entreprise")[0].id, 1)

    def test_english_stopwords_are_ignored(self):
        chunks = _chunks("What is it? It is what it is.", "The sigmoid function outputs a probability.")
        self.assertEqual([c.id for c in lexical_rank(chunks, "What is the sigmoid function?")], [1])

    def test_compound_terms(self):
        chunks = _chunks("L'algorithme k-NN vote.", "Le TF IDF pondère les mots.", "Autre.")
        self.assertEqual(lexical_rank(chunks, "algorithme kNN")[0].id, 0)
        self.assertEqual(lexical_rank(chunks, "TF-IDF")[0].id, 1)

    def test_decimal_numbers(self):
        chunks = _chunks("Le seuil vaut 0,5 en général.", "Le seuil vaut 5 parfois.")
        self.assertEqual(lexical_rank(chunks, "seuil 0.5")[0].id, 0)

    def test_exact_expression_beats_scattered_words(self):
        chunks = _chunks(
            "Le nom de la société est collectif dans ce cas précis.",
            "La société en nom collectif est une société commerciale.",
        )
        self.assertEqual(lexical_rank(chunks, "société en nom collectif")[0].id, 1)

    def test_scores_decrease_and_are_positive(self):
        chunks = _chunks("loi binomiale", "loi normale", "loi binomiale et loi binomiale", "rien")
        scores = [score for score, _ in lexical_scores(chunks, "loi binomiale")]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(score > 0 for score in scores))
        self.assertEqual(len(scores), 3)

    def test_rare_term_weighs_more_than_frequent_term(self):
        chunks = _chunks("modèle modèle", "modèle", "modèle régularisation", "modèle")
        self.assertEqual(lexical_rank(chunks, "modèle régularisation")[0].id, 2)

    def test_lexical_search_on_every_subject(self):
        """Questions avec termes exacts, sigles, termes courts ou sans accents : le
        passage attendu est dans les 3 premiers, pour chaque matière du corpus."""
        lexical_kinds = {
            eval_corpus.ACRONYM, eval_corpus.DOTTED, eval_corpus.SHORT, eval_corpus.NO_ACCENT,
        }
        for spec in eval_corpus.DOCUMENTS:
            chunks = build_chunks(eval_corpus.raw_pages(spec), chunk_size=300, overlap=50)
            for item in eval_corpus.questions(spec):
                if item["kind"] not in lexical_kinds:
                    continue
                relevant = relevant_ids(chunks, item["needles"])
                top = [c.id for c in lexical_rank(chunks, item["question"], limit=3)]
                self.assertTrue(relevant & set(top), f"{spec['key']} : {item['question']}")


# --- Fusion RRF -------------------------------------------------------------------------

class RrfTests(SimpleTestCase):
    def test_formula(self):
        fused = rrf_fuse([["a", "b"], ["b", "c"]], [1.0, 1.0], k=60)
        self.assertAlmostEqual(fused["a"], 1 / 61)
        self.assertAlmostEqual(fused["b"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(fused["c"], 1 / 62)

    def test_weights(self):
        fused = rrf_fuse([["a"], ["b"]], [1.0, 0.5], k=60)
        self.assertAlmostEqual(fused["b"], 0.5 / 61)
        self.assertNotIn("b", rrf_fuse([["a"], ["b"]], [1.0, 0.0]))

    def test_same_depth_for_both_lists(self):
        dense = ["d1", "d2", "d3", "x"]
        lexical = ["l1", "l2", "l3", "x"]
        cosine = {key: 0.5 for key in dense + lexical}
        ordered, fused = hybrid_order(dense, lexical, cosine, weight=1.0, depth=3)
        self.assertNotIn("x", fused)  # 4e dans les deux listes : hors profondeur
        self.assertEqual(set(ordered), {"d1", "d2", "d3", "l1", "l2", "l3"})

    def test_equal_weights_do_not_favour_one_method(self):
        ordered, fused = hybrid_order(["d"], ["l"], {"d": 0.9, "l": 0.1}, 1.0, 10)
        self.assertAlmostEqual(fused["d"], fused["l"])
        self.assertEqual(ordered, ["d", "l"])  # égalité : départage par le cosinus

    def test_consensus_wins(self):
        # « b » est 2e en vectoriel et 1er en BM25 : il passe devant « a » (1er vectoriel seulement)
        fused = rrf_fuse([["a", "b"], ["b", "z"]], [1.0, 1.0])
        self.assertEqual(max(fused, key=fused.get), "b")


# --- Recherche hybride en base ------------------------------------------------------------

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class HybridSearchDbTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.texts = ["alpha", "beta", "gamma", "la loi binomiale B(n, p)"]
        self.embedder = PinnedEmbedder({
            "QUERY": axis(1, 0), "alpha": axis(1, 0), "beta": axis(1, 0.2),
            "gamma": axis(1, 0.5), self.texts[3]: axis(1, 1.0),
        })
        self.document = make_document(alice, "Hybride", texts=self.texts)
        index_document(self.document, self.embedder)

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=1.0)
    def test_scores_are_kept_separate(self):
        hits = search_chunks(self.document, "loi binomiale", k=4, embedder=self.embedder)
        top = hits[0]
        self.assertEqual(top.chunk.text, self.texts[3])
        self.assertAlmostEqual(top.score, 1 / math.sqrt(2), places=3)  # cosinus
        self.assertAlmostEqual(top.rrf_score, 1 / 64 + 1 / 61)        # fusion
        self.assertEqual((top.dense_rank, top.lexical_rank), (4, 1))
        self.assertIsNone(hits[1].lexical_rank)

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=1.0, RETRIEVAL_CANDIDATES=2)
    def test_depth_is_never_smaller_than_k(self):
        hits = search_chunks(self.document, "zorglub", k=4, embedder=self.embedder)
        self.assertEqual(len(hits), 4)

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=1.0, RETRIEVAL_CANDIDATES=2)
    def test_lexical_match_outside_dense_candidates_is_still_found(self):
        hits = search_chunks(self.document, "binomiale", k=2, embedder=self.embedder)
        self.assertIn(self.texts[3], [hit.chunk.text for hit in hits])

    @override_settings(RETRIEVAL_LEXICAL_WEIGHT=1.0)
    def test_both_methods_search_the_same_chunks(self):
        # Un passage sans vecteur du modèle courant n'est trouvé par aucune des deux méthodes
        self.document.chunks.filter(text=self.texts[3]).update(embedding_model="ancien")
        hits = search_chunks(self.document, "loi binomiale", k=4, embedder=self.embedder)
        self.assertNotIn(self.texts[3], [hit.chunk.text for hit in hits])


# --- Évaluation ----------------------------------------------------------------------------

class MetricTests(SimpleTestCase):
    def test_metrics_on_a_known_ranking(self):
        ranked, relevant = ["a", "b", "c", "d"], {"b", "d", "z"}
        self.assertAlmostEqual(precision_at_k(ranked, relevant, 2), 0.5)
        self.assertAlmostEqual(recall_at_k(ranked, relevant, 4), 2 / 3)
        self.assertAlmostEqual(reciprocal_rank(ranked, relevant), 0.5)
        dcg = 1 / math.log2(3) + 1 / math.log2(5)
        ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)
        self.assertAlmostEqual(ndcg_at_k(ranked, relevant, 4), dcg / ideal)

    def test_perfect_and_empty_rankings(self):
        self.assertEqual(ndcg_at_k(["a"], {"a"}, 5), 1.0)
        self.assertEqual(reciprocal_rank(["a"], {"b"}), 0.0)
        self.assertEqual(recall_at_k(["a"], set(), 5), 0.0)


class EvaluationCorpusTests(SimpleTestCase):
    def test_every_answer_is_found_in_the_chunks(self):
        for spec in eval_corpus.DOCUMENTS:
            chunks = build_chunks(eval_corpus.raw_pages(spec))
            for item in eval_corpus.questions(spec):
                if item["needles"]:
                    self.assertTrue(relevant_ids(chunks, item["needles"]), item["question"])

    def test_headers_do_not_reach_the_chunks(self):
        for spec in eval_corpus.DOCUMENTS:
            for chunk in build_chunks(eval_corpus.raw_pages(spec)):
                self.assertNotIn(spec["header"], chunk.text)
                self.assertNotRegex(chunk.text, r"Page \d+ / \d+")

    def test_corpus_covers_subjects_languages_and_unanswerable_questions(self):
        self.assertGreaterEqual(len(eval_corpus.DOCUMENTS), 5)
        self.assertEqual({d["language"] for d in eval_corpus.DOCUMENTS}, {"fr", "en"})
        kinds = {q["kind"] for d in eval_corpus.DOCUMENTS for q in eval_corpus.questions(d)}
        self.assertIn(eval_corpus.UNANSWERABLE, kinds)
        self.assertIn(eval_corpus.CROSS_LINGUAL, kinds)

    def test_evaluate_compares_the_three_modes(self):
        embedder = FakeEmbedder()
        documents = [
            (index_chunks(s["key"], build_chunks(eval_corpus.raw_pages(s)), embedder),
             eval_corpus.questions(s))
            for s in eval_corpus.DOCUMENTS
        ]
        reports = evaluate(documents, embedder, k=3)
        answerable = sum(1 for _, qs in documents for q in qs if q["needles"])
        for mode in ("dense", "bm25", "hybrid"):
            self.assertEqual(len(reports[mode].per_question), answerable)
            for name in ("precision", "recall", "mrr", "ndcg"):
                self.assertTrue(0 <= reports[mode].mean(name) <= 1)
        # Le mode BM25 seul retrouve la majorité des réponses en tête
        self.assertGreater(reports["bm25"].mean("mrr"), 0.8)

        pooled = pool_documents(documents)
        self.assertEqual(len(pooled[0].chunks), sum(len(d.chunks) for d, _ in documents))
        ranked, _ = rank(pooled[0], "loi binomiale", "hybrid", embedder)
        self.assertEqual(len(set(ranked)), len(ranked))


# --- Intégration : import d'un PDF multi-pages -----------------------------------------------

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfPipelineTests(TestCase):
    def test_pdf_headers_are_removed_and_pages_kept(self):
        owner = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        pages = [
            "Cours de probabilites - L2\nLa loi binomiale compte les succes.\nPage 1",
            "Cours de probabilites - L2\nLa loi normale est symetrique.\nPage 2",
            "Cours de probabilites - L2\nLe theoreme central limite.\nPage 3",
        ]
        data = make_pdf(pages)
        document = CourseDocument.objects.create(
            owner=owner, title="Proba", file=SimpleUploadedFile("p.pdf", data),
            file_type="pdf", file_size=len(data),
        )
        document = process_document(document)
        self.assertEqual(document.status, "ready")
        self.assertEqual(document.page_count, 3)
        text = " ".join(document.chunks.values_list("text", flat=True))
        self.assertNotIn("Cours de probabilites", text)
        self.assertIn("loi binomiale", text)
        self.assertIn("theoreme central limite", text)
