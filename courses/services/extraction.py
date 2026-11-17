import logging
import re

import pymupdf

from .data import ExtractionError, PageData

logger = logging.getLogger(__name__)

TXT_PAGE_CHARS = 3000  # taille d'une « page virtuelle » pour les fichiers TXT

# Ligne du type « Chapitre 3 », « Partie II : Les bases », « Section 2.1 »
_HEADING_RE = re.compile(
    r"^\s*((?:chapitre|chapter|partie|part|section)\s+[0-9IVXLC]+\b.{0,80})$",
    re.IGNORECASE | re.MULTILINE,
)


def _detect_heading(raw_text):
    """Retourne le dernier titre de chapitre trouvé dans le texte brut d'une page."""
    matches = _HEADING_RE.findall(raw_text)
    return matches[-1].strip() if matches else ""


def _chapter_from_toc(entries, page_number):
    """Dernier titre de niveau 1 du sommaire situé à cette page ou avant."""
    title = ""
    for page, entry_title in entries:
        if page <= page_number:
            title = entry_title.strip()
        else:
            break
    return title


def extract_pdf_pages(path):
    pages = []
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ExtractionError("Le PDF est protégé par un mot de passe.")

            toc_entries = sorted(
                (entry[2], entry[1])
                for entry in doc.get_toc()
                if entry[0] == 1 and entry[2] >= 1
            )

            current_chapter = ""
            for number, page in enumerate(doc, start=1):
                try:
                    text = page.get_text("text")
                except Exception:  # une page illisible ne doit pas tout bloquer
                    logger.warning("Page %s illisible dans %s", number, path)
                    text = ""

                if toc_entries:
                    chapter = _chapter_from_toc(toc_entries, number)
                else:
                    current_chapter = _detect_heading(text) or current_chapter
                    chapter = current_chapter
                pages.append(PageData(number, text, chapter))
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Impossible de lire le PDF (fichier corrompu ?).") from exc
    return pages


def _decode(raw_bytes):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin-1", errors="replace")


def _split_txt_into_pages(text):
    if "\f" in text:  # saut de page explicite
        return text.split("\f")

    parts, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        if current and len(current) + len(paragraph) > TXT_PAGE_CHARS:
            parts.append(current)
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current)
    return parts


def extract_txt_pages(path):
    try:
        with open(path, "rb") as handle:
            text = _decode(handle.read())
    except OSError as exc:
        raise ExtractionError("Impossible de lire le fichier texte.") from exc

    pages, current_chapter = [], ""
    for number, part in enumerate(_split_txt_into_pages(text), start=1):
        current_chapter = _detect_heading(part) or current_chapter
        pages.append(PageData(number, part, current_chapter))
    return pages


def extract_pages(path, file_type):
    if file_type == "pdf":
        return extract_pdf_pages(path)
    if file_type == "txt":
        return extract_txt_pages(path)
    raise ExtractionError(f"Type de fichier non pris en charge : {file_type}")