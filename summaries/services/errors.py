class SummaryError(Exception):
    """Erreur lisible par l'étudiant."""


class SummaryProviderError(SummaryError):
    """Le fournisseur de résumé n'est pas utilisable (modèle absent, etc.)."""