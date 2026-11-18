from django.db import models

from courses.models import CourseDocument


class Summary(models.Model):
    class Level(models.TextChoices):
        SHORT = "short", "Court"
        MEDIUM = "medium", "Moyen"
        DETAILED = "detailed", "Détaillé"

    document = models.ForeignKey(
        CourseDocument, on_delete=models.CASCADE, related_name="summaries"
    )
    level = models.CharField(max_length=10, choices=Level.choices)
    content = models.TextField()
    provider = models.CharField(max_length=50)
    model_name = models.CharField(max_length=120, blank=True)
    section_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "level"], name="unique_summary_per_level"
            )
        ]

    def __str__(self):
        return f"{self.document.title} - {self.get_level_display()}"