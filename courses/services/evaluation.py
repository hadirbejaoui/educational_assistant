"""Évaluation de la recherche : vectorielle seule, BM25 seule, hybride RRF.

Les passages sont produits par le vrai pipeline (strip_repeated_lines, clean_text,
chunk_pages) et classés par les vraies fonctions de retrieval.py (lexical_rank,
hybrid_order). Seul le calcul de similarité se fait en mémoire au lieu de pgvector :
avec des vecteurs normalisés, le produit scalaire donne exactement l'ordre de
CosineDistance.
"""

import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from types import SimpleNamespace

from django.conf import settings

from .chunking import chunk_pages
from .cleaning import clean_text, strip_repeated_lines
from .retrieval import hybrid_order, lexical_rank

MODES = ("dense", "bm25", "hybrid")


# --- Métriques (pertinence binaire) -----------------------------------------

def precision_at_k(ranked, relevant, k):
    return sum(1 for item in ranked[:k] if item in relevant) / k


def recall_at_k(ranked, relevant, k):
    if not relevant:
        return 0.0
    return sum(1 for item in ranked[:k] if item in relevant) / len(relevant)


def reciprocal_rank(ranked, relevant):
    for rank, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1 / rank
    return 0.0


def ndcg_at_k(ranked, relevant, k):
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, item in enumerate(ranked[:k], start=1)
        if item in relevant
    )
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


# --- Préparation du corpus ---------------------------------------------------

def _plain(text):
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text)


def build_chunks(pages, chunk_size=None, overlap=None):
    """Pages brutes -> passages, avec le même traitement que process_document()."""
    texts = strip_repeated_lines([page.text for page in pages])
    cleaned = [
        SimpleNamespace(page_number=page.page_number, text=clean_text(text), chapter=page.chapter)
        for page, text in zip(pages, texts)
    ]
    chunks = chunk_pages(
        cleaned,
        chunk_size or settings.CHUNK_SIZE,
        settings.CHUNK_OVERLAP if overlap is None else overlap,
    )
    return [
        SimpleNamespace(
            id=chunk.index, chunk_index=chunk.index, text=chunk.text,
            page_start=chunk.page_start, page_end=chunk.page_end, chapter=chunk.chapter,
        )
        for chunk in chunks
    ]


def relevant_ids(chunks, needles):
    wanted = [_plain(needle) for needle in needles]
    return {chunk.id for chunk in chunks if any(n in _plain(chunk.text) for n in wanted)}


# --- Classement ---------------------------------------------------------------

@dataclass
class IndexedDocument:
    key: str
    chunks: list
    vectors: list  # vecteurs normalisés, dans l'ordre de `chunks`


def index_chunks(key, chunks, embedder):
    return IndexedDocument(key, chunks, embedder.embed_passages([c.text for c in chunks]))


def pool_documents(documents):
    """Réunit plusieurs (IndexedDocument, questions) en une seule collection."""
    chunks, vectors, all_questions = [], [], []
    for document, document_questions in documents:
        offset = len(chunks)
        for chunk in document.chunks:
            chunks.append(SimpleNamespace(**{**vars(chunk), "id": offset + chunk.id}))
        vectors.extend(document.vectors)
        all_questions.extend(document_questions)
    return IndexedDocument("tous", chunks, vectors), all_questions


def rank(document, query, mode, embedder, weight=1.0, depth=None):
    """Identifiants des passages, du plus au moins pertinent, et similarités cosinus."""
    depth = depth or getattr(settings, "RETRIEVAL_CANDIDATES", 50)
    cosine = {}
    if mode in ("dense", "hybrid"):
        query_vector = embedder.embed_query(query)
        for chunk, vector in zip(document.chunks, document.vectors):
            cosine[chunk.id] = sum(a * b for a, b in zip(query_vector, vector))
    dense_ids = sorted(cosine, key=lambda item: -cosine[item])  # tri stable

    if mode == "dense":
        return dense_ids, cosine
    lexical_ids = [c.id for c in lexical_rank(document.chunks, query, limit=len(document.chunks))]
    if mode == "bm25":
        return lexical_ids, cosine
    ordered, _ = hybrid_order(dense_ids, lexical_ids, cosine, weight, depth)
    return ordered, cosine


# --- Évaluation ----------------------------------------------------------------

@dataclass
class ModeReport:
    mode: str
    k: int
    per_question: list = field(default_factory=list)
    search_seconds: list = field(default_factory=list)

    def mean(self, name, kind=None):
        rows = [r for r in self.per_question if kind is None or r["kind"] == kind]
        return sum(r[name] for r in rows) / len(rows) if rows else 0.0


def evaluate(documents, embedder, k=5, weight=1.0, modes=MODES):
    """Évalue chaque mode sur des documents préparés.

    `documents` : liste de (IndexedDocument, questions) où chaque question est un
    dictionnaire {question, needles, kind}. Les questions sans aiguille (hors cours)
    ne comptent pas dans les métriques de classement : elles servent à mesurer le
    refus (meilleure similarité cosinus, voir `refusal_stats`).
    """
    reports = {mode: ModeReport(mode, k) for mode in modes}
    for document, document_questions in documents:
        for item in document_questions:
            relevant = relevant_ids(document.chunks, item["needles"])
            if item["needles"] and not relevant:
                raise ValueError(f"Aucun passage ne contient les aiguilles de : {item['question']}")
            for mode in modes:
                started = time.perf_counter()
                ranked, cosine = rank(document, item["question"], mode, embedder, weight)
                elapsed = time.perf_counter() - started
                if not relevant:
                    continue
                reports[mode].search_seconds.append(elapsed)
                reports[mode].per_question.append({
                    "document": document.key,
                    "question": item["question"],
                    "kind": item["kind"],
                    "precision": precision_at_k(ranked, relevant, k),
                    "recall": recall_at_k(ranked, relevant, k),
                    "mrr": reciprocal_rank(ranked, relevant),
                    "ndcg": ndcg_at_k(ranked, relevant, k),
                    "first_rank": next(
                        (r for r, i in enumerate(ranked, start=1) if i in relevant), None
                    ),
                })
    return reports


def refusal_stats(documents, embedder, threshold):
    """Meilleure similarité cosinus des questions avec et sans réponse.

    Indique combien de questions avec réponse passeraient le seuil RAG_MIN_SCORE
    et combien de questions hors cours seraient refusées par la recherche
    (le LLM peut encore refuser ensuite avec NON_TROUVE).
    """
    answerable, unanswerable = [], []
    for document, document_questions in documents:
        for item in document_questions:
            _, cosine = rank(document, item["question"], "dense", embedder)
            best = max(cosine.values()) if cosine else 0.0
            (answerable if item["needles"] else unanswerable).append(best)
    return {
        "answerable": answerable,
        "unanswerable": unanswerable,
        "answered_rate": sum(s >= threshold for s in answerable) / max(len(answerable), 1),
        "refused_rate": sum(s < threshold for s in unanswerable) / max(len(unanswerable), 1),
    }


# --- Évaluation sur les cours réels (fichier evaluation/rag_questions.json) ----------

def load_course_questions(path):
    """Lit et vérifie le fichier d'évaluation ; retourne la liste des cours."""
    import json

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    courses = data.get("courses") if isinstance(data, dict) else None
    if not isinstance(courses, list) or not courses:
        raise ValueError("Le fichier doit contenir une liste « courses » non vide.")
    for course in courses:
        if not isinstance(course.get("document_id"), int):
            raise ValueError("Chaque cours doit avoir un « document_id » entier.")
        for item in course.get("questions", []):
            if not item.get("question") or not (item.get("expected_pages") or item.get("expected_text")):
                raise ValueError(
                    f"Question incomplète dans le cours {course['document_id']} : "
                    "il faut « question » et « expected_pages » ou « expected_text »."
                )
        course.setdefault("questions", [])
        course.setdefault("out_of_scope", [])
    return courses


def chunk_is_relevant(chunk, item):
    """Le passage couvre une page attendue (et contient l'extrait attendu, s'il est donné)."""
    pages = item.get("expected_pages") or []
    if pages and not any(chunk.page_start <= page <= chunk.page_end for page in pages):
        return False
    text = item.get("expected_text")
    return not text or _plain(text) in _plain(chunk.text)


def rank_stored_document(document, query, embedder, weights, depth=None):
    """Classements d'un document indexé, pour plusieurs poids lexicaux, en un seul calcul.

    Mêmes étapes que search_chunks() : vecteurs pgvector (CosineDistance), BM25 sur
    les mêmes passages, fusion par hybrid_order(). Retourne un dictionnaire :
    chunks {id: chunk}, cosine {id: similarité}, lexical_rank {id: rang},
    orders {poids: [ids du meilleur au moins bon]}.
    """
    from pgvector.django import CosineDistance

    depth = depth or getattr(settings, "RETRIEVAL_CANDIDATES", 50)
    vector = embedder.embed_query(query)
    dense = list(
        document.chunks.filter(embedding__isnull=False, embedding_model=embedder.model_name)
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance", "chunk_index")
        .defer("embedding")
    )
    cosine = {chunk.id: 1 - chunk.distance for chunk in dense}
    dense_ids = [chunk.id for chunk in dense]
    lexical_ids = [chunk.id for chunk in lexical_rank(dense, query, limit=depth)]
    orders = {}
    for weight in weights:
        orders[weight] = hybrid_order(dense_ids, lexical_ids if weight > 0 else [], cosine, weight, depth)[0]
    return {
        "chunks": {chunk.id: chunk for chunk in dense},
        "cosine": cosine,
        "lexical_rank": {chunk_id: rank for rank, chunk_id in enumerate(lexical_ids, start=1)},
        "orders": orders,
    }


def wilson_interval(successes, total, z=1.96):
    """Intervalle de confiance à 95 % d'une proportion (méthode de Wilson).

    Plus fiable que « p ± 1,96·√(p(1-p)/n) » pour les petits échantillons :
    avec 3 succès sur 10, il donne [0,11 ; 0,60], ce qui montre à quel point
    une mesure sur 10 questions est imprécise.
    """
    if not total:
        return 0.0, 1.0
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - margin), min(1.0, centre + margin)
