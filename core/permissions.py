"""Accès aux cours : chaque compte dispose de son propre espace pédagogique.

Un utilisateur n'accède qu'à SES cours, et donc aux résumés, passages et index de ces
cours ; ses quiz, tentatives et conversations sont en plus filtrés par utilisateur.
Toutes les vues passent par `user_documents` : un identifiant modifié dans une URL ou
un formulaire désigne un cours hors de ce filtre et donne 404 (pas 403, pour ne pas
révéler qu'il existe). Masquer un bouton dans un gabarit ne serait pas une sécurité.

L'administrateur (`is_staff`) gère les comptes dans l'admin Django (/admin/) ; dans
l'application, il a son propre espace privé comme tout le monde.
"""

from courses.models import CourseDocument


def user_documents(user):
    """Cours appartenant à `user` : seule porte d'accès aux cours dans les vues."""
    return CourseDocument.objects.filter(owner=user)
