import bisect
import re

from .data import ChunkData

# Fin de phrase : ponctuation forte (éventuellement suivie d'un guillemet ou d'une
# parenthèse fermante), puis un blanc, puis un début de phrase plausible.
# « M. Dupont », « art. 12 » ou « e.g. the » ne sont donc pas des fins de phrase.
# Une fin de paragraphe ou un retour à la ligne reste toujours une coupure possible.
_SENTENCE_END = re.compile(
    r"(?<!\b[A-Za-z])[.!?…][\"'»”)\]]*\s+(?=[\"'«“(\[]?[A-ZÀ-ÖØ-Þ•\-–])"
)
_HEADING_MAX_CHARS = 80


def _sentence_ends(text, start, end):
    """Positions (dans `text`) juste après chaque fin de phrase de [start, end)."""
    return [m.end() for m in _SENTENCE_END.finditer(text, start, end)]


def _looks_like_heading(line):
    line = line.strip()
    return (
        0 < len(line) <= _HEADING_MAX_CHARS
        and not line.endswith((".", "!", "?", ",", ";", "…"))
        and any(char.isalpha() for char in line)
    )


def _find_break(text, start, end):
    """Cherche une coupure naturelle dans la 2e moitié de la fenêtre.

    Priorité : fin de paragraphe, fin de phrase, retour à la ligne,
    point-virgule / deux-points, espace. Un titre n'est jamais laissé seul en
    fin de passage : la coupure est déplacée juste avant lui.
    """
    window_start = start + (end - start) // 2
    cut = end
    position = text.rfind("\n\n", window_start, end)
    if position != -1:
        cut = position + 2
    else:
        ends = _sentence_ends(text, window_start, end)
        if ends:
            cut = ends[-1]
        else:
            for separator in ("\n", "; ", ": ", " "):
                position = text.rfind(separator, window_start, end)
                if position != -1:
                    cut = position + len(separator)
                    break

    # Titre en fin de passage -> il ira avec son contenu dans le passage suivant
    body = text[start:cut].rstrip()
    line_start = body.rfind("\n") + 1
    if line_start and start + line_start > window_start and _looks_like_heading(body[line_start:]):
        cut = start + line_start
    return cut


def _overlap_start(text, position, end, overlap):
    """Début du passage suivant : environ `overlap` caractères avant `end`.

    On préfère commencer au début d'une phrase (ou d'une ligne), sinon au début
    d'un mot, pour ne pas ouvrir un passage au milieu d'un mot.
    """
    target = end - overlap
    if target <= position:
        return end
    low = max(position + 1, end - overlap - overlap // 2)
    high = end - overlap // 4
    candidates = _sentence_ends(text, low, high)
    candidates += [i + 1 for i in range(low, high) if text[i] == "\n"]
    candidates = [c for c in candidates if position < c < end]
    if candidates:
        return min(candidates, key=lambda c: abs(c - target))
    space = text.find(" ", target, end)
    return space + 1 if space != -1 else target


def chunk_pages(pages, chunk_size, overlap):
    """Découpe une liste de PageData (déjà nettoyées) en ChunkData.

    Chaque passage garde sa page de début, sa page de fin et le chapitre
    de la page où il commence. Les passages font au plus `chunk_size`
    caractères, sont coupés de préférence entre paragraphes puis entre
    phrases, et se chevauchent d'environ `overlap` caractères.
    """
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Il faut 0 <= overlap < chunk_size.")
    min_tail = chunk_size // 4  # en dessous, un dernier passage serait presque vide

    # 1) Assembler tout le texte en mémorisant où commence chaque page
    parts, starts, page_info, offset = [], [], [], 0
    for page in pages:
        content = page.text.strip()
        if not content:
            continue
        starts.append(offset)
        page_info.append((page.page_number, page.chapter))
        parts.append(content + "\n\n")
        offset += len(content) + 2
    full_text = "".join(parts)
    total = len(full_text)

    def page_index_at(position):
        return max(bisect.bisect_right(starts, position) - 1, 0)

    # 2) Fenêtre glissante
    chunks, position = [], 0
    while position < total:
        end = min(position + chunk_size, total)
        if end < total:
            remaining = total - position
            if total - end < min_tail and remaining > chunk_size:
                # Équilibrer les deux derniers passages plutôt que d'en laisser un minuscule
                end = position + (remaining + overlap) // 2
            end = _find_break(full_text, position, end)

        raw = full_text[position:end]
        text = raw.strip()
        if text:
            first = position + (len(raw) - len(raw.lstrip()))
            last = first + len(text) - 1
            first_info = page_info[page_index_at(first)]
            last_info = page_info[page_index_at(last)]
            chunks.append(
                ChunkData(
                    index=len(chunks),
                    text=text,
                    page_start=first_info[0],
                    page_end=last_info[0],
                    chapter=first_info[1],
                )
            )

        if end >= total or not full_text[end:].strip():
            break
        position = _overlap_start(full_text, position, end, overlap) if overlap else end

    return chunks
