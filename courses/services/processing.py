import dataclasses
import logging

from django.conf import settings
from django.db import transaction

from ..models import CourseDocument, DocumentChunk, DocumentPage
from .chunking import chunk_pages
from .cleaning import clean_text
from .data import ExtractionError
from .extraction import extract_pages

logger = logging.getLogger(__name__)


def _mark_failed(document, message):
    document.status = CourseDocument.Status.FAILED
    document.error_message = message
    document.page_count = 0
    document.save(update_fields=["status", "error_message", "page_count"])


def process_document(document):
    """Extrait, nettoie, découpe et enregistre un document.

    Ne lève jamais d'exception : en cas de problème, le document passe
    au statut « failed » avec un message lisible.
    """
    document.status = CourseDocument.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message"])

    try:
        raw_pages = extract_pages(document.file.path, document.file_type)
        pages = [dataclasses.replace(p, text=clean_text(p.text)) for p in raw_pages]

        if not any(p.text for p in pages):
            raise ExtractionError(
                "Aucun texte extractible (PDF scanné ou composé d'images ?). "
                "L'OCR n'est pas pris en charge."
            )

        chunks = chunk_pages(pages, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        # Tout ou rien : si un enregistrement échoue, rien n'est gardé
        with transaction.atomic():
            document.pages.all().delete()
            document.chunks.all().delete()
            DocumentPage.objects.bulk_create(
                DocumentPage(
                    document=document, page_number=p.page_number, text=p.text
                )
                for p in pages
            )
            DocumentChunk.objects.bulk_create(
                DocumentChunk(
                    document=document,
                    chunk_index=c.index,
                    text=c.text,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    chapter=c.chapter[:255],
                    char_count=len(c.text),
                )
                for c in chunks
            )
    except ExtractionError as exc:
        _mark_failed(document, str(exc))
        return document
    except Exception:
        logger.exception("Échec du traitement du document %s", document.pk)
        _mark_failed(document, "Erreur inattendue pendant le traitement du document.")
        return document

    document.page_count = len(pages)
    document.status = CourseDocument.Status.READY
    document.save(update_fields=["status", "page_count"])
    return document