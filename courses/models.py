import os
import uuid

from django.conf import settings
from django.db import models


def document_upload_path(instance, filename):
    """Range chaque fichier dans media/documents/<id_utilisateur>/<uuid>.<ext>.

    Le nom d'origine n'est pas utilisé : cela évite les collisions et les
    noms dangereux. Le nom d'origine reste lisible dans le champ `title`.
    """
    extension = os.path.splitext(filename)[1].lower()
    return f"documents/{instance.owner_id}/{uuid.uuid4().hex}{extension}"


class CourseDocument(models.Model):
    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        TXT = "txt", "TXT"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Importé"
        PROCESSING = "processing", "En traitement"
        READY = "ready", "Prêt"
        FAILED = "failed", "Échec"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField("titre", max_length=255)
    file = models.FileField("fichier", upload_to=document_upload_path)
    file_type = models.CharField(max_length=3, choices=FileType.choices)
    file_size = models.PositiveBigIntegerField("taille (octets)", default=0)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.UPLOADED
    )
    error_message = models.TextField(blank=True)
    page_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["owner", "-uploaded_at"])]

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        """Supprime aussi le fichier physique du disque."""
        file_field = self.file
        result = super().delete(*args, **kwargs)
        if file_field:
            file_field.delete(save=False)
        return result


class DocumentPage(models.Model):
    """Texte d'une page. Rempli en Phase 4."""

    document = models.ForeignKey(
        CourseDocument, on_delete=models.CASCADE, related_name="pages"
    )
    page_number = models.PositiveIntegerField()
    text = models.TextField(blank=True)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"], name="unique_page_per_document"
            )
        ]

    def __str__(self):
        return f"{self.document.title} - page {self.page_number}"