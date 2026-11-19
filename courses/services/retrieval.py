from dataclasses import dataclass

from django.conf import settings
from pgvector.django import CosineDistance

from ..models import DocumentChunk
from .embeddings import get_embedder


@dataclass
class SearchHit:
    chunk: DocumentChunk
    score: float  # similarité cosinus : 1 = identique


def search_chunks(document, query, k=None, embedder=None):
    """Retourne les passages d'UN document les plus proches de la question.

    La recherche est toujours limitée au document reçu : l'appelant a déjà
    vérifié qu'il appartient à l'utilisateur.
    """
    query = query.strip()
    if not query:
        return []
    embedder = embedder or get_embedder()
    k = k or settings.RETRIEVAL_TOP_K

    vector = embedder.embed_query(query)
    chunks = (
        document.chunks.filter(embedding__isnull=False, embedding_model=embedder.model_name)
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance")[:k]
    )
    return [SearchHit(chunk, 1 - chunk.distance) for chunk in chunks]