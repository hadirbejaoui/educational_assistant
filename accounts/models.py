
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Utilisateur personnalisé.

    Hérite de AbstractUser (username, password, email, etc.).
    On pourra ajouter des champs plus tard sans casser la base.
    """
    email = models.EmailField("adresse e-mail", unique=True)

    def __str__(self):
        return self.username
