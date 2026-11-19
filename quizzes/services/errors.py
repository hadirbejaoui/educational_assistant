class QuizError(Exception):
    """Erreur lisible par l'étudiant."""


class QuizFormatError(QuizError):
    """La réponse du LLM n'a pas le format attendu."""