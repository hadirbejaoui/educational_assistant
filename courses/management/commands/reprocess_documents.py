from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseDocument
from courses.services.embeddings import EmbeddingError, get_embedder, index_document
from courses.services.processing import process_document


class Command(BaseCommand):
    help = (
        "Ré-extrait, re-nettoie et re-découpe les documents prêts, puis recalcule leurs "
        "embeddings. À lancer après une modification du nettoyage ou du découpage : "
        "les passages existants ne sont pas modifiés automatiquement."
    )

    def add_arguments(self, parser):
        parser.add_argument("--document", type=int, help="Identifiant d'un document")

    def handle(self, *args, **options):
        documents = CourseDocument.objects.filter(status=CourseDocument.Status.READY)
        if options["document"]:
            documents = documents.filter(pk=options["document"])
        embedder = get_embedder()
        for document in documents:
            before = document.chunks.count()
            document = process_document(document)
            if document.status != CourseDocument.Status.READY:
                self.stderr.write(f"{document.title} : échec ({document.error_message})")
                continue
            try:
                count = index_document(document, embedder)
            except EmbeddingError as exc:
                raise CommandError(f"{document.title} : {exc}")
            self.stdout.write(f"{document.title} : {before} -> {count} passage(s) indexé(s)")
