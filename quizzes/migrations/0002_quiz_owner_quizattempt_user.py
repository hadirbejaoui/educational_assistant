"""Bibliothèque de cours partagée : chaque quiz et chaque tentative reçoivent leur propriétaire.

Les lignes existantes sont attribuées au propriétaire du cours, c'est-à-dire à la personne
qui les voyait déjà : aucune donnée n'est perdue ni rendue visible à quelqu'un d'autre.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_owners(apps, schema_editor):
    Quiz = apps.get_model("quizzes", "Quiz")
    QuizAttempt = apps.get_model("quizzes", "QuizAttempt")
    for quiz in Quiz.objects.select_related("document"):
        quiz.owner_id = quiz.document.owner_id
        quiz.save(update_fields=["owner"])
    for attempt in QuizAttempt.objects.select_related("quiz"):
        attempt.user_id = attempt.quiz.owner_id
        attempt.save(update_fields=["user"])


class Migration(migrations.Migration):
    dependencies = [
        ("quizzes", "0001_initial"),
        ("courses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="quiz", name="owner",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="quizzes", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="quizattempt", name="user",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="quiz_attempts", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(fill_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="quiz", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="quizzes", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="quizattempt", name="user",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="quiz_attempts", to=settings.AUTH_USER_MODEL),
        ),
    ]
