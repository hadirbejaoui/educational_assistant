import logging
import threading
from abc import ABC, abstractmethod

from django.conf import settings
from django.db.models import Q

from ..models import DocumentChunk

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Erreur lisible par l'étudiant."""


class BaseEmbedder(ABC):
    """Interface commune : changer de modèle d'embeddings = changer une classe."""

    name = "base"
    model_name = ""

    @abstractmethod
    def embed_passages(self, texts):
        """Retourne une liste de vecteurs (listes de floats), un par texte."""

    @abstractmethod
    def embed_query(self, text):
        """Retourne le vecteur d'une question."""


_LOCK = threading.Lock()
_LOADED = {}  # nom du modèle -> modèle chargé (une seule fois)


class SentenceTransformerEmbedder(BaseEmbedder):
    name = "sentence-transformers"

    def __init__(self, model_name):
        self.model_name = model_name

    def _load(self):
        with _LOCK:
            if self.model_name not in _LOADED:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingError(
                        "La bibliothèque sentence-transformers n'est pas installée."
                    ) from exc
                try:
                    _LOADED[self.model_name] = SentenceTransformer(self.model_name)
                except Exception as exc:
                    raise EmbeddingError(
                        f"Impossible de charger le modèle « {self.model_name} » "
                        "(connexion nécessaire au premier chargement)."
                    ) from exc
            return _LOADED[self.model_name]

    def _encode(self, texts):
        model = self._load()
        try:
            vectors = model.encode(
                texts,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            logger.exception("Échec du calcul des embeddings")
            raise EmbeddingError("Échec du calcul des embeddings.") from exc
        result = [vector.tolist() for vector in vectors]
        if result and len(result[0]) != settings.EMBEDDING_DIMENSIONS:
            raise EmbeddingError(
                f"Le modèle produit {len(result[0])} dimensions, "
                f"{settings.EMBEDDING_DIMENSIONS} attendues."
            )
        return result

    def embed_passages(self, texts):
        prefix = settings.EMBEDDING_PASSAGE_PREFIX
        return self._encode([prefix + text for text in texts])

    def embed_query(self, text):
        return self._encode([settings.EMBEDDING_QUERY_PREFIX + text])[0]


def get_embedder():
    """Choisit le modèle d'embeddings selon EMBEDDING_MODEL_NAME."""
    return SentenceTransformerEmbedder(settings.EMBEDDING_MODEL_NAME)


def index_document(document, embedder=None, force=False):
    """Calcule et enregistre les embeddings des passages d'un document.

    Seuls les passages sans vecteur, ou dont le vecteur vient d'un autre modèle,
    sont recalculés (sauf `force`). Retourne le nombre de passages traités.
    """
    embedder = embedder or get_embedder()
    chunks = document.chunks.all()
    if not force:
        chunks = chunks.filter(
            Q(embedding__isnull=True) | ~Q(embedding_model=embedder.model_name)
        )
    chunks = list(chunks)

    size = settings.EMBEDDING_BATCH_SIZE
    for start in range(0, len(chunks), size):
        batch = chunks[start : start + size]
        vectors = embedder.embed_passages([chunk.text for chunk in batch])
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector
            chunk.embedding_model = embedder.model_name
        DocumentChunk.objects.bulk_update(batch, ["embedding", "embedding_model"])
    return len(chunks)