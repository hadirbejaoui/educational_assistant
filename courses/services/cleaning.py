import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text):
    """Nettoie le texte brut d'une page.

    Étapes : normalisation Unicode, suppression des caractères de contrôle,
    recollage des mots coupés en fin de ligne, nettoyage des espaces et
    fusion des retours à la ligne simples. Les paragraphes (lignes vides)
    sont conservés.
    """
    # NFKC transforme par exemple la ligature « ﬁ » en « fi »
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # « informa-\ntion » devient « information »
    text = re.sub(r"([a-zà-ÿ])-\n([a-zà-ÿ])", r"\1\2", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    # Un retour à la ligne isolé (coupure de ligne du PDF) devient un espace
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()