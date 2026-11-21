from django.conf import settings
from django.db import models

from courses.models import CourseDocument


class Conversation(models.Model):
    document = models.ForeignKey(
        CourseDocument, on_delete=models.CASCADE, related_name="conversations"
    )
    # Les cours sont partagés ; chaque étudiant a ses propres conversations
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations"
    )
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["document", "-updated_at"])]

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Étudiant"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    # Passages consultés : [{"n", "chunk_id", "page_start", "page_end", "chapter", "score", "cited", "excerpt"}]
    sources = models.JSONField(default=list, blank=True)
    # False quand l'assistant a refusé de répondre (n'a de sens que pour l'assistant)
    is_grounded = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"{self.get_role_display()} : {self.content[:40]}"