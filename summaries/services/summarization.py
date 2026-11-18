import logging
from dataclasses import dataclass

from django.conf import settings

from ..models import Summary
from .errors import SummaryError
from .providers import get_provider
from .sections import build_sections

logger = logging.getLogger(__name__)

MAX_REDUCE_ROUNDS = 5


@dataclass(frozen=True)
class LevelConfig:
    section_words: int       # taille du résumé de chaque section
    final_words: int | None  # taille du résumé final (None = pas de réduction)


LEVELS = {
    "short": LevelConfig(section_words=30, final_words=70),
    "medium": LevelConfig(section_words=60, final_words=180),
    "detailed": LevelConfig(section_words=120, final_words=None),
}


def _word_count(text):
    return len(text.split())


def _group(items, limit):
    """Regroupe des textes pour que chaque groupe tienne dans `limit` caractères."""
    groups, current, length = [], [], 0
    for item in items:
        if current and length + len(item) + 1 > limit:
            groups.append(current)
            current, length = [], 0
        current.append(item)
        length += len(item) + 1
    if current:
        groups.append(current)
    return groups


def _page_label(section):
    if section.page_start == section.page_end:
        return f"Page {section.page_start}"
    return f"Pages {section.page_start} à {section.page_end}"


def build_summary(sections, level, provider, limit):
    """Résumé hiérarchique : résumer chaque section, puis combiner."""
    config = LEVELS.get(level)
    if config is None:
        raise SummaryError(f"Niveau de résumé inconnu : « {level} ».")

    # 1) Étape « map » : un résumé par section
    partials = [
        (section, provider.summarize(section.text, config.section_words))
        for section in sections
    ]
    partials = [(s, text) for s, text in partials if text.strip()]
    if not partials:
        raise SummaryError("Le modèle n'a produit aucun résumé.")

    # Niveau détaillé : on garde la structure, avec les pages
    if config.final_words is None:
        return "\n\n".join(f"{_page_label(s)} :\n{text}" for s, text in partials)

    # 2) Étape « reduce » : combiner tant que c'est trop long
    texts = [text for _, text in partials]
    combined = " ".join(texts)
    for _ in range(MAX_REDUCE_ROUNDS):
        if len(combined) <= limit:
            break
        texts = [
            provider.summarize(" ".join(group), config.final_words)
            for group in _group(texts, limit)
        ]
        texts = [t for t in texts if t.strip()]
        combined = " ".join(texts)

    # 3) Résumé final cohérent
    if _word_count(combined) > config.final_words:
        combined = provider.summarize(combined, config.final_words)
    return combined.strip()


def generate_summary(document, level, provider=None):
    """Génère (ou régénère) le résumé d'un document pour un niveau donné."""
    if level not in LEVELS:
        raise SummaryError(f"Niveau de résumé inconnu : « {level} ».")

    provider = provider or get_provider()
    limit = settings.SUMMARY_SECTION_CHARS
    sections = build_sections(list(document.pages.all()), limit)
    if not sections:
        raise SummaryError("Ce document ne contient aucun texte à résumer.")

    if provider.is_slow and len(sections) > settings.SUMMARY_MAX_SECTIONS:
        raise SummaryError(
            f"Document trop long pour un traitement immédiat ({len(sections)} sections, "
            f"maximum {settings.SUMMARY_MAX_SECTIONS})."
        )

    content = build_summary(sections, level, provider, limit)
    if not content.strip():
        raise SummaryError("Le résumé généré est vide.")

    summary, _ = Summary.objects.update_or_create(
        document=document,
        level=level,
        defaults={
            "content": content,
            "provider": provider.name,
            "model_name": provider.model_name,
            "section_count": len(sections),
        },
    )
    return summary