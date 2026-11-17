import os

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_document_file(uploaded_file):
    """Vérifie l'extension, la taille et (pour un PDF) la signature du fichier."""
    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError("Format non autorisé. Importez un fichier PDF ou TXT.")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if uploaded_file.size > max_bytes:
        raise ValidationError(
            f"Fichier trop volumineux (maximum {settings.MAX_UPLOAD_SIZE_MB} Mo)."
        )
    if uploaded_file.size == 0:
        raise ValidationError("Le fichier est vide.")

    if extension == ".pdf":
        header = uploaded_file.read(5)
        uploaded_file.seek(0)
        if header != b"%PDF-":
            raise ValidationError("Ce fichier n'est pas un PDF valide.")