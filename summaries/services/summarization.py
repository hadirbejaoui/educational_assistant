"""Résumé hiérarchique (map-reduce) d'un cours, en trois niveaux réellement différents.

1. Le cours est découpé en sections qui tiennent dans le contexte du modèle (sections.py).
2. « Map » : chaque section est résumée, avec un budget de mots proportionnel à sa taille.
3. Court et moyen : les résumés partiels sont fusionnés (« reduce », en plusieurs tours si
   besoin), puis une synthèse finale ramène le tout à la longueur visée.
   Détaillé : pas de synthèse finale, qui perdrait des informations ; les parties sont
   conservées dans l'ordre du cours, chacune sous un intertitre de pages.

Les niveaux diffèrent par leur longueur visée, proportionnelle au cours (SUMMARY_LEVELS)
et par leur style (le fournisseur LLM reçoit des consignes propres à chaque niveau).
"""

import logging

from django.conf import settings

from ..models import Summary
from .errors import SummaryError
from .providers import get_provider
from .sections import build_sections

logger = logging.getLogger(__name__)

MAX_REDUCE_ROUNDS = 5
REDUCE_RATIO = 0.6  # chaque tour de fusion garde au plus 60 % des mots
# Le niveau détaillé garde une partie par section au lieu de tout fusionner
STRUCTURED_LEVELS = {"detailed"}


def _word_count(text):
    return len(text.split())


def _level_config(level):
    config = settings.SUMMARY_LEVELS.get(level)
    if config is None:
        raise SummaryError(f"Niveau de résumé inconnu : « {level} ».")
    return config


def target_words(level, source_words):
    """Longueur visée du résumé final : proportionnelle au cours, dans les bornes du niveau."""
    config = _level_config(level)
    target = round(config["ratio"] * source_words)
    target = min(max(target, config["min_words"]), config["max_words"])
    return max(1, min(target, source_words))  # jamais plus long que le cours


def section_limit(provider, level):
    """Taille maximale d'une section (caractères) pour ce fournisseur et ce niveau."""
    base = getattr(provider, "section_chars", None) or settings.SUMMARY_SECTION_CHARS
    return max(500, int(base * _level_config(level).get("section_scale", 1)))


def _section_budget(section_words, source_words, total_words):
    """Part du budget total revenant à une section, selon sa taille."""
    share = round(total_words * section_words / max(source_words, 1))
    share = max(share, settings.SUMMARY_MIN_SECTION_WORDS)
    return max(1, min(share, section_words, settings.SUMMARY_MAX_WORDS_PER_CALL))


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


def _map_sections(sections, level, provider, total_words):
    """Étape « map » : un résumé par section ; les résumés vides sont écartés."""
    source_words = sum(_word_count(s.text) for s in sections)
    partials = []
    for section in sections:
        budget = _section_budget(_word_count(section.text), source_words, total_words)
        text = provider.summarize(section.text, budget, level=level)
        if text.strip():
            partials.append((section, text.strip()))
    if not partials:
        raise SummaryError("Le modèle n'a produit aucun résumé.")
    return partials


def _reduce(texts, level, provider, limit):
    """Fusionne les résumés partiels tant que leur ensemble dépasse la taille d'une section.

    Chaque tour vise au plus REDUCE_RATIO des mots, et assez peu pour tenir dans `limit`
    caractères : la synthèse finale reçoit ainsi un texte qui tient dans le contexte.
    """
    combined = "\n\n".join(texts)
    for _ in range(MAX_REDUCE_ROUNDS):
        if len(combined) <= limit:
            break
        words = _word_count(combined)
        fitting = int(limit / (len(combined) / words) * 0.8)  # mots qui tiennent dans `limit`
        total = min(round(words * REDUCE_RATIO), fitting)
        groups = ["\n\n".join(group) for group in _group(texts, limit)]
        texts = [
            provider.summarize(group, _section_budget(_word_count(group), words, total), level=level)
            for group in groups
        ]
        texts = [t.strip() for t in texts if t.strip()]
        combined = "\n\n".join(texts)
    return texts, combined


def build_summary(sections, level, provider, limit):
    """Résumé hiérarchique de `sections` au niveau `level` (voir le docstring du module)."""
    _level_config(level)
    source_words = sum(_word_count(s.text) for s in sections)
    target = target_words(level, source_words)
    structured = level in STRUCTURED_LEVELS
    # Une seule section, ou niveau détaillé : le « map » produit directement le résultat
    expansion = 1 if structured or len(sections) == 1 else settings.SUMMARY_MAP_EXPANSION

    partials = _map_sections(sections, level, provider, round(target * expansion))

    if structured:
        if len(partials) == 1:
            return partials[0][1]
        return "\n\n".join(f"## {_page_label(s)}\n\n{text}" for s, text in partials)

    texts, combined = _reduce([text for _, text in partials], level, provider, limit)
    # Synthèse finale : relie les parties et ramène à la longueur visée
    if len(texts) > 1 or _word_count(combined) > target * 1.2:
        combined = provider.summarize(combined, target, level=level)
    return combined.strip()


def generate_summary(document, level, provider=None):
    """Génère (ou régénère) le résumé d'un document pour un niveau donné."""
    if level not in Summary.Level.values:
        raise SummaryError(f"Niveau de résumé inconnu : « {level} ».")

    provider = provider or get_provider()
    limit = section_limit(provider, level)
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
    logger.info("Résumé %s du document %s : %s mots, %s section(s)",
                level, document.pk, _word_count(content), len(sections))
    return summary
