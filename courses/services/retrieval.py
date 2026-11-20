import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from pgvector.django import CosineDistance

from ..models import DocumentChunk
from .embeddings import get_embedder

# Paramètres de la recherche hybride
RRF_K = 60                 # constante standard de Reciprocal Rank Fusion (Cormack et al., 2009)
LEXICAL_LIMIT = 10         # valeur par défaut de lexical_rank() utilisée seule
BM25_K1, BM25_B = 1.5, 0.75

# Mots vides français et anglais : uniquement des mots grammaticaux, jamais des
# termes de matière. Les lettres isolées (« C », « R », « n », « x ») sont gardées,
# sauf « a », « à » et « y ». Un mot écrit en MAJUSCULES au milieu d'un texte en
# minuscules (« SA », « IT », « OR ») est traité comme un sigle et n'est jamais retiré.
_STOPWORD_TEXT = """
    a à ai as au aux avec avez avons ça ce ceci cela celle celles celui ces cet cette
    chez comme comment dans de des donc dont du elle elles en entre est et étaient
    était été être eu eux il ils je la le les leur leurs lui ma mais me même mes
    moi mon ne ni nos notre nous on ont ou où par pas peut peuvent plus pour pourquoi
    quand que quel quelle quelles quels qui quoi sa sans se ses si sois son sont sur
    ta te tes toi ton tu un une vers vos votre vous y
    an and are at be been being but by can could did do does for from had has have how
    if in into is it its of on or our should so than that the their them then there
    these they this those to was we were what when where which while who whom why will
    with would you your
"""

# « l'entreprise », « qu'est-ce », « jusqu'à » : l'article élidé est retiré
_ELISION = re.compile(r"\b(?:[cdjlmnst]|qu|jusqu|lorsqu|puisqu|quoiqu)['’]", re.IGNORECASE)
# Sigles à points : « S.N.C. », « S.A », « e.g. » -> « SNC », « SA », « eg »
_DOTTED_ACRONYM = re.compile(r"(?<![\w.])[^\W\d_](?:\.[^\W\d_])+\.?(?![\w])")
# Nombres décimaux (« 0,5 » = « 0.5 »), puis mots avec composés (« k-NN », « TCP/IP »)
# et suffixes de langages (« C++ », « C# »)
_TOKEN = re.compile(r"\d+[.,]\d+|[^\W_]+(?:[-‐/][^\W_]+)*(?:\+\+|#)?")
_COMPOUND_SEPARATOR = re.compile(r"[-‐/]")
# Coupures de segments (phrases, lignes, listes) : « 3.14 » et « 0,5 » ne coupent pas
_SEGMENT_BREAK = re.compile(r"[\n!?;]|[.:,](?=\s|$)")


@dataclass
class SearchHit:
    chunk: DocumentChunk
    score: float                 # Similarité cosinus : 1 = identique (ne dépend pas de la fusion)
    rrf_score: float = 0.0       # Score de fusion RRF qui détermine l'ordre des résultats
    dense_rank: int | None = None    # Rang dans la recherche vectorielle (None : hors candidats)
    lexical_rank: int | None = None  # Rang dans la recherche BM25 (None : aucun mot commun)


def _strip_accents(text):
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


_STOPWORDS = frozenset(_strip_accents(word) for word in _STOPWORD_TEXT.split())


def _is_acronym(word, segment_upper):
    letters = [char for char in word if char.isalpha()]
    return len(letters) >= 2 and word.isupper() and not segment_upper


def _normalize(word, acronym):
    """Forme de comparaison d'un mot, ou "" si c'est un mot vide.

    Minuscules et sans accents ; pluriel simple retiré (« sociétés » -> « societe »),
    sauf pour les sigles (« SAS » reste « sas »).
    """
    word = _strip_accents(word.casefold()).replace(",", ".")
    if not acronym and word in _STOPWORDS:
        return ""
    if not acronym and len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


@lru_cache(maxsize=8192)
def _analyze(text):
    """Retourne (mots, bigrammes) d'un texte, de façon identique pour questions et passages.

    - accents et casse ignorés, articles élidés retirés ;
    - sigles à points recollés (« S.N.C. » = « SNC ») ;
    - termes courts conservés (« C », « R », « x », « 2 ») : seuls les mots vides sont retirés ;
    - mots composés : chaque partie + la forme collée (« k-NN » -> k, nn, knn) ;
    - bigrammes de mots consécutifs pour favoriser les expressions exactes.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _ELISION.sub(" ", text)
    text = _DOTTED_ACRONYM.sub(lambda m: m.group(0).replace(".", ""), text)

    words, bigrams = [], []
    for segment in _SEGMENT_BREAK.split(text):
        cased = [char for char in segment if char.lower() != char.upper()]
        # Titre entièrement en majuscules : ses mots ne sont pas des sigles
        segment_upper = len(cased) >= 12 and sum(c.isupper() for c in cased) > 0.7 * len(cased)
        sequence = []
        for raw in _TOKEN.findall(segment):
            parts = _COMPOUND_SEPARATOR.split(raw)
            kept = [
                word
                for word in (_normalize(part, _is_acronym(part, segment_upper)) for part in parts)
                if word
            ]
            if len(parts) > 1 and kept:
                words.append(_normalize("".join(parts), _is_acronym(raw, segment_upper)) or "")
            words.extend(kept)
            sequence.extend(kept)
        bigrams.extend(f"{a} {b}" for a, b in zip(sequence, sequence[1:]))
    return tuple(word for word in words if word), tuple(bigrams)


def _tokens(text):
    """Mots normalisés d'un texte (sans mots vides). Conservé pour compatibilité."""
    return list(_analyze(text)[0])


def _terms(text):
    words, bigrams = _analyze(text)
    return Counter(words), Counter(bigrams)


def lexical_scores(chunks, query):
    """Scores BM25 des passages pour la question, triés du meilleur au moins bon.

    Retourne une liste de (score, chunk) avec score > 0. Les statistiques (IDF,
    longueur moyenne) sont calculées sur l'ensemble des passages fournis.
    """
    query_words, query_bigrams = _terms(query)
    terms = set(query_words) | set(query_bigrams)
    if not terms or not chunks:
        return []

    counted = []
    for chunk in chunks:
        words, bigrams = _terms(chunk.text)
        counted.append((chunk, words + bigrams, sum(words.values())))

    count = len(counted)
    average = (sum(length for _, _, length in counted) / count) or 1
    document_frequency = {
        term: sum(1 for _, counts, _ in counted if term in counts) for term in terms
    }
    idf = {
        term: math.log(1 + (count - df + 0.5) / (df + 0.5))
        for term, df in document_frequency.items()
        if df
    }

    scored = []
    for chunk, counts, length in counted:
        norm = BM25_K1 * (1 - BM25_B + BM25_B * (length or 1) / average)
        score = 0.0
        for term, weight in idf.items():
            tf = counts.get(term, 0)
            if tf:
                score += weight * tf * (BM25_K1 + 1) / (tf + norm)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: -pair[0])  # tri stable : à égalité, l'ordre d'entrée est gardé
    return scored


def lexical_rank(chunks, query, limit=LEXICAL_LIMIT):
    """Classe les passages selon les mots de la question avec BM25 (sans dictionnaire)."""
    return [chunk for _, chunk in lexical_scores(chunks, query)[:limit]]


def rrf_fuse(rankings, weights, k=RRF_K):
    """Reciprocal Rank Fusion pondérée.

    `rankings` : listes d'identifiants, du meilleur au moins bon.
    score(d) = somme_i  poids_i / (k + rang_i(d)), rang commençant à 1 ;
    un document absent d'une liste ne reçoit rien de cette liste.
    """
    fused = {}
    for ranking, weight in zip(rankings, weights):
        if weight <= 0:
            continue
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + weight / (k + rank)
    return fused


def hybrid_order(dense_ids, lexical_ids, cosine, weight, depth):
    """Ordre final de la recherche hybride (fonction pure, réutilisée par l'évaluation).

    Les deux listes sont tronquées à la même profondeur `depth`, fusionnées par RRF
    (poids 1 pour la liste vectorielle, `weight` pour BM25) ; à score RRF égal, la
    meilleure similarité cosinus (`cosine[id]`) passe devant.
    Retourne (identifiants ordonnés, scores RRF).
    """
    fused = rrf_fuse([dense_ids[:depth], lexical_ids[:depth]], [1.0, weight])
    ordered = sorted(fused, key=lambda item: (-fused[item], -cosine[item]))
    return ordered, fused


def search_chunks(document, query, k=None, embedder=None):
    """
    Retourne les passages les plus pertinents d'un document.

    Recherche hybride :
    1. Recherche vectorielle (dense) sur tous les passages indexés du document.
    2. Recherche lexicale BM25 sur exactement les mêmes passages.
    3. Fusion des deux classements avec RRF, chaque liste étant limitée aux
       RETRIEVAL_CANDIDATES premiers (profondeur identique pour les deux méthodes).

    L'ordre suit le score RRF ; `hit.score` reste la similarité cosinus,
    utilisée par le chatbot pour décider s'il peut répondre.
    """
    query = query.strip()
    if not query:
        return []

    embedder = embedder or get_embedder()
    k = k or settings.RETRIEVAL_TOP_K
    depth = max(getattr(settings, "RETRIEVAL_CANDIDATES", 50), k)
    weight = settings.RETRIEVAL_LEXICAL_WEIGHT

    # 1. Recherche vectorielle
    vector = embedder.embed_query(query)
    dense = list(
        document.chunks.filter(embedding__isnull=False, embedding_model=embedder.model_name)
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance", "chunk_index")
        .defer("embedding")
    )
    if not dense:
        return []

    hits = {
        chunk.id: SearchHit(chunk, 1 - chunk.distance, dense_rank=rank)
        for rank, chunk in enumerate(dense, start=1)
    }
    dense_ids = [chunk.id for chunk in dense]

    # 2. Recherche lexicale sur le même ensemble de passages
    lexical_ids = []
    if weight > 0:
        lexical_ids = [chunk.id for chunk in lexical_rank(dense, query, limit=depth)]
        for rank, chunk_id in enumerate(lexical_ids, start=1):
            hits[chunk_id].lexical_rank = rank

    # 3. Fusion RRF
    cosine = {chunk_id: hit.score for chunk_id, hit in hits.items()}
    ordered, fused = hybrid_order(dense_ids, lexical_ids, cosine, weight, depth)
    for chunk_id, value in fused.items():
        hits[chunk_id].rrf_score = value
    return [hits[chunk_id] for chunk_id in ordered[:k]]
