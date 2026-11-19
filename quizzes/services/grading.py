from django.db import transaction
from django.utils import timezone

from ..models import QuizAttempt, StudentAnswer


def grade_attempt(quiz, selections):
    """Corrige une tentative.

    `selections` : {id_question: id_choix}. Un choix qui n'appartient pas à la
    question, ou une question sans réponse, compte comme faux.
    """
    questions = list(quiz.questions.prefetch_related("choices"))
    with transaction.atomic():
        attempt = QuizAttempt.objects.create(quiz=quiz, total=len(questions))
        answers, score = [], 0
        for question in questions:
            wanted_id = selections.get(question.id)
            selected = next(
                (c for c in question.choices.all() if c.id == wanted_id), None
            )
            is_correct = bool(selected and selected.is_correct)
            score += is_correct
            answers.append(
                StudentAnswer(
                    attempt=attempt, question=question,
                    selected_choice=selected, is_correct=is_correct,
                )
            )
        StudentAnswer.objects.bulk_create(answers)
        attempt.score = score
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["score", "completed_at"])
    return attempt