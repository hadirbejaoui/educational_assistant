from dataclasses import dataclass


class ExtractionError(Exception):
    """Erreur lisible par l'étudiant (PDF protégé, scanné, corrompu...)."""


@dataclass
class PageData:
    page_number: int
    text: str
    chapter: str = ""


@dataclass
class ChunkData:
    index: int
    text: str
    page_start: int
    page_end: int
    chapter: str = ""