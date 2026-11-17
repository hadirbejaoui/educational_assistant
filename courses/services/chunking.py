import bisect

from .data import ChunkData


def _find_break(text, start, end):
    """Cherche une coupure naturelle dans la 2e moitié de la fenêtre.

    Priorité : fin de paragraphe, fin de phrase, retour à la ligne, espace.
    """
    window_start = start + (end - start) // 2
    for separator in ("\n\n", ". ", "\n", " "):
        position = text.rfind(separator, window_start, end)
        if position != -1:
            return position + len(separator)
    return end


def chunk_pages(pages, chunk_size, overlap):
    """Découpe une liste de PageData (déjà nettoyées) en ChunkData.

    Chaque passage garde sa page de début, sa page de fin et le chapitre
    de la page où il commence.
    """
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Il faut 0 <= overlap < chunk_size.")

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

        if end >= total:
            break

        next_position = end - overlap
        if next_position <= position:
            next_position = end
        else:  # recommencer au début d'un mot
            space = full_text.find(" ", next_position, end)
            if space != -1:
                next_position = space + 1
        position = next_position

    return chunks