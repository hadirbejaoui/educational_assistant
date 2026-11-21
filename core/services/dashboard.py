"""Données du tableau de bord.

Chaque requête part des cours de l'utilisateur ou de son identifiant : un compte
ne voit jamais les données d'un autre. Les views n'ont qu'à appeler
`dashboard_data(request.user)`.
"""

from django.db.models import Avg, F, FloatField, ExpressionWrapper

from chatbot.models import Conversation
from core.permissions import user_documents
from quizzes.models import Quiz, QuizAttempt
from summaries.models import Summary

RECENT_ITEMS = 5


def user_counts(user):
    """Compteurs principaux de l'utilisateur."""
    return {
        "documents": user_documents(user).count(),
        "summaries": Summary.objects.filter(document__in=user_documents(user)).count(),
        "quizzes": Quiz.objects.filter(owner=user).count(),
        "conversations": Conversation.objects.filter(owner=user).count(),
    }


def completed_attempts(user):
    """Tentatives terminées de l'utilisateur, les plus récentes d'abord."""
    return QuizAttempt.objects.filter(
        user=user, completed_at__isnull=False
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
        "recent_documents": list(user_documents(user)[:recent]),
        "recent_conversations": list(
            Conversation.objects.filter(owner=user).select_related("document")[:recent]
        ),
    }
