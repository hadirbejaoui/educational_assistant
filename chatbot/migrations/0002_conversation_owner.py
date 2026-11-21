"""Bibliothèque de cours partagée : chaque conversation reçoit son propriétaire.

Les lignes existantes sont attribuées au propriétaire du cours, c'est-à-dire à la personne
qui les voyait déjà : aucune donnée n'est perdue ni rendue visible à quelqu'un d'autre.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_owners(apps, schema_editor):
    Conversation = apps.get_model("chatbot", "Conversation")
    for conversation in Conversation.objects.select_related("document"):
        conversation.owner_id = conversation.document.owner_id
        conversation.save(update_fields=["owner"])


class Migration(migrations.Migration):
    dependencies = [
        ("chatbot", "0001_initial"),
        ("courses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation", name="owner",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="conversations", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(fill_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="conversation", name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="conversations", to=settings.AUTH_USER_MODEL),
        ),
    ]
