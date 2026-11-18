from dataclasses import dataclass


@dataclass
class Section:
    text: str
    page_start: int
    page_end: int


def _split_long(text, limit):
    """Coupe un texte trop long sur des espaces, en morceaux d'au plus `limit`."""
    parts = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def build_sections(pages, limit):
    """Regroupe des pages (objets avec page_number et text) en sections."""
    sections, buffer = [], []
    state = {"length": 0, "start": 0, "end": 0}

    def flush():
        if buffer:
            sections.append(
                Section(" ".join(buffer), state["start"], state["end"])
            )
            buffer.clear()
            state["length"] = 0

    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        for piece in _split_long(text, limit):
            if buffer and state["length"] + len(piece) + 1 > limit:
                flush()
            if not buffer:
                state["start"] = page.page_number
            buffer.append(piece)
            state["length"] += len(piece) + 1
            state["end"] = page.page_number
    flush()
    return sections