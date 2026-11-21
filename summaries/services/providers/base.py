from abc import ABC, abstractmethod


class BaseSummaryProvider(ABC):
    """Interface commune : changer de fournisseur = changer une classe."""

    name = "base"
    model_name = ""
    is_slow = False  # True pour les modèles lourds (limite le nombre de sections)

    @abstractmethod
    def summarize(self, text, max_words, level="medium"):
        """Retourne un résumé d'au plus environ `max_words` mots.

        `level` (short, medium, detailed) indique le style attendu ; les fournisseurs
        qui ne savent pas adapter leur style (extractif, mT5) l'ignorent.
        """