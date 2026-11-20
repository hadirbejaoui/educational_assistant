import re
import unicodedata
from collections import Counter

# Caractères de contrôle (sauf \t et \n), y compris le bloc C1 (U+0080-U+009F)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Caractères invisibles : trait d'union conditionnel, espaces de largeur nulle, BOM
_INVISIBLE_CHARS = re.compile(r"[­​‌‍⁠﻿]")

# Début de ligne qui ouvre un nouvel élément : puce, « 1. », « 2) », « a) », « IV. »
_LIST_ITEM = re.compile(r"^(?:[•▪◦●○■□➢►‣\-–—*·]\s|\(?\d{1,3}[.)]\s|\(?[a-zA-Z][.)]\s|[IVXLC]{1,6}[.)]\s)")
_HYPHENATED = re.compile(r"([^\W\d_])-\n([^\W\d_])")
_SENTENCE_END = (".", "!", "?", ":", ";", "…", "»", '"', "”")

# Une ligne seule faite d'un numéro de page : « 12 », « - 12 - », « Page 3 / 20 », « p. 4 »
_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:page|p\.)?\s*\d{1,4}(?:\s*(?:/|sur|of)\s*\d{1,4})?(?:\s*[-–—])?\s*$",
    re.IGNORECASE,
)


def _is_heading_like(line, longest):
    """Ligne courte, sans ponctuation finale : probablement un titre."""
    return (
        len(line) <= 80
        and len(line) < 0.75 * longest  # les lignes de texte coupées sont presque pleines
        and not line.endswith(_SENTENCE_END + (",",))
        and any(char.isalpha() for char in line)
    )


def _join_lines(block):
    """Recolle les lignes coupées par la mise en page, en gardant la structure.

    Un retour à la ligne est conservé avant un élément de liste, après un titre
    et après une phrase terminée suivie d'une majuscule (fin de paragraphe probable).
    Sinon, c'est une simple coupure de ligne du PDF : elle devient un espace.
    """
    lines = [line.strip() for line in block.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    longest = max(len(line) for line in lines)

    result = lines[0]
    for previous, line in zip(lines, lines[1:]):
        starts_upper = line[0].isupper() or line[0].isdigit()
        keep_break = (
            _LIST_ITEM.match(line)
            or (_is_heading_like(previous, longest) and starts_upper)
            or (
                previous.endswith(_SENTENCE_END)
                and starts_upper
                and len(previous) < 0.85 * longest  # ligne non pleine : fin de paragraphe
            )
        )
        result += ("\n" if keep_break else " ") + line
    return result


# Exposants, indices et fractions : NFKC les aplatirait (« 10³ » -> « 103 »)
_KEEP_DECOMPOSITIONS = ("<super>", "<sub>", "<fraction>")


def _normalize_unicode(text):
    """NFKC (ligatures « ﬁ » -> « fi », espaces insécables, lettres mathématiques
    stylisées, formes pleine chasse...), sauf pour les exposants, indices et
    fractions, qui changeraient le sens d'une formule. Le reste est en NFC."""
    parts, start = [], 0
    for position, char in enumerate(text):
        if ord(char) > 127 and unicodedata.decomposition(char).startswith(_KEEP_DECOMPOSITIONS):
            parts.append(unicodedata.normalize("NFKC", text[start:position]))
            parts.append(char)
            start = position + 1
    parts.append(unicodedata.normalize("NFKC", text[start:]))
    return unicodedata.normalize("NFC", "".join(parts))


def clean_text(text):
    """Nettoie le texte brut d'une page.

    Étapes : normalisation Unicode, suppression des caractères de contrôle et
    invisibles, recollage des mots coupés en fin de ligne, nettoyage des espaces,
    recollage des lignes coupées par la mise en page. Les paragraphes (lignes
    vides) sont conservés, ainsi que les retours à la ligne structurants
    (titres, listes, fins de paragraphe). Nombres, symboles et formules ne sont
    jamais supprimés.
    """
    text = _normalize_unicode(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _INVISIBLE_CHARS.sub("", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)

    # « informa-\ntion » devient « information » (lettres de toutes les langues).
    # Si la suite commence par une majuscule, le tiret est gardé : « Jean-Pierre ».
    text = _HYPHENATED.sub(
        lambda m: m.group(1) + ("" if m.group(2).islower() else "-") + m.group(2), text
    )

    paragraphs = re.split(r"\n{2,}", text)
    text = "\n\n".join(p for p in (_join_lines(p) for p in paragraphs) if p)
    return text.strip()


_NUMBER = re.compile(r"\d+")


def strip_repeated_lines(texts, min_pages=3, ratio=0.5, edge_lines=2):
    """Supprime en-têtes et pieds de page répétés, ainsi que les numéros de page seuls.

    Seules les `edge_lines` premières et dernières lignes de chaque page sont
    examinées. Une telle ligne est retirée si :
    - c'est un numéro de page seul (« 12 », « Page 3 / 20 ») ;
    - ou la même ligne exacte apparaît au bord d'au moins `ratio` des pages
      (et d'au moins `min_pages` pages) : titre courant, nom du cours... ;
    - ou elle ne diffère d'une page à l'autre que par un nombre qui suit le
      numéro de page (« Cours X - 12 » sur la page 12), sur autant de pages.
    Un titre comme « Exercice 2 » en haut d'une page n'est donc pas supprimé.
    Prend et renvoie une liste de textes bruts.
    """

    def edges(lines):
        filled = [i for i, line in enumerate(lines) if line.strip()]
        return sorted(set(filled[:edge_lines] + filled[-edge_lines:]))

    def counter_key(line, page_index):
        numbers = _NUMBER.findall(line)
        if len(numbers) != 1:
            return None
        # Même gabarit et même décalage entre le nombre et la position de la page
        return (_NUMBER.sub("#", line), int(numbers[0]) - page_index)

    split = [text.split("\n") for text in texts]
    exact, counters = Counter(), Counter()
    for page_index, lines in enumerate(split):
        candidates = [lines[i].strip() for i in edges(lines) if len(lines[i].strip()) <= 100]
        exact.update(set(candidates))
        counters.update({key for key in (counter_key(c, page_index) for c in candidates) if key})

    threshold = max(min_pages, ratio * len(texts))
    repeated = {line for line, count in exact.items() if count >= threshold}
    page_counters = {key for key, count in counters.items() if count >= threshold}

    result = []
    for page_index, lines in enumerate(split):
        drop = set()
        for i in edges(lines):
            line = lines[i].strip()
            if (
                line in repeated
                or counter_key(line, page_index) in page_counters
                or _PAGE_NUMBER_LINE.match(line)
            ):
                drop.add(i)
        result.append("\n".join(line for i, line in enumerate(lines) if i not in drop))
    return result
