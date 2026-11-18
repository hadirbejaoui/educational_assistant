import re
from collections import Counter

from .base import BaseSummaryProvider

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\w{3,}", re.UNICODE)
_STOPWORDS = {
    "les", "des", "une", "est", "que", "qui", "dans", "pour", "pas", "sur", "par",
    "avec", "sont", "ces", "ses", "aux", "ont", "plus", "mais", "comme", "cette",
    "the", "and", "for", "that", "with", "this", "are", "was", "from", "have",
}


class ExtractiveProvider(BaseSummaryProvider):
    """Résumé par extraction : garde les phrases les plus « chargées » en mots-clés.

    Aucun modèle à télécharger. Sert à valider toute la chaîne et de secours.
    """

    name = "extractive"
    model_name = "frequency-based"

    def summarize(self, text, max_words):
        text = text.strip()
        words = text.split()
        if len(words) <= max_words:
            return text

        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        frequencies = Counter(
            w.lower() for w in _WORD.findall(text) if w.lower() not in _STOPWORDS
        )
        if not sentences or not frequencies:
            return " ".join(words[:max_words])

        scored = []
        for index, sentence in enumerate(sentences):
            tokens = [w.lower() for w in _WORD.findall(sentence)]
            score = sum(frequencies[t] for t in tokens) / (len(tokens) + 5)
            scored.append((score, index, sentence))

        chosen, used = [], 0
        for score, index, sentence in sorted(scored, reverse=True):
            length = len(sentence.split())
            if used + length <= max_words:
                chosen.append((index, sentence))
                used += length

        if not chosen:  # même la meilleure phrase est trop longue
            return " ".join(words[:max_words])
        return " ".join(sentence for _, sentence in sorted(chosen))