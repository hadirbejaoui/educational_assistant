"""Données du tableau de bord.

Chaque requête part d'un filtre sur le propriétaire du document : un étudiant
ne voit jamais les données d'un autre. Les views n'ont qu'à appeler
`dashboard_data(request.user)`.
"""

from django.db.models import Avg, F, FloatField, ExpressionWrapper

from chatbot.models import Conversation
from courses.models import CourseDocument
from quizzes.models import Quiz, QuizAttempt
from summaries.models import Summary

RECENT_ITEMS = 5


def user_counts(user):
    """Compteurs principaux de l'utilisateur."""
    return {
        "documents": CourseDocument.objects.filter(owner=user).count(),
        "summaries": Summary.objects.filter(document__owner=user).count(),
        "quizzes": Quiz.objects.filter(document__owner=user).count(),
        "conversations": Conversation.objects.filter(document__owner=user).count(),
    }


def completed_attempts(user):
    """Tentatives terminées de l'utilisateur, les plus récentes d'abord."""
    return QuizAttempt.objects.filter(
        quiz__document__owner=user, completed_at__isnull=False
    ).select_related("quiz", "quiz__document")


def average_grade(user):
    """Moyenne des notes sur 20 des tentatives terminées (None s'il n'y en a pas)."""
    grade = ExpressionWrapper(F("score") * 20.0 / F("total"), output_field=FloatField())
    value = (
        completed_attempts(user)
        .filter(total__gt=0)
        .aggregate(value=Avg(grade))["value"]
    )
    return round(value, 1) if value is not None else None


def dashboard_data(user, recent=RECENT_ITEMS):
    return {
        "counts": user_counts(user),
        "average_grade": average_grade(user),
        "recent_attempts": list(completed_attempts(user)[:recent]),
        "recent_documents": list(CourseDocument.objects.filter(owner=user)[:recent]),
        "recent_conversations": list(
            Conversation.objects.filter(document__owner=user).select_related("document")[:recent]
        ),
    }
