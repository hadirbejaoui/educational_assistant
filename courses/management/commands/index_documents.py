from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseDocument
from courses.services.embeddings import EmbeddingError, get_embedder, index_document


class Command(BaseCommand):
    help = "Calcule les embeddings des passages (tous les documents prêts, ou un seul)."

    def add_arguments(self, parser):
        parser.add_argument("--document", type=int, help="Identifiant d'un document")
        parser.add_argument("--force", action="store_true", help="Tout recalculer")

    def handle(self, *args, **options):
        documents = CourseDocument.objects.filter(status=CourseDocument.Status.READY)
        if options["document"]:
            documents = documents.filter(pk=options["document"])
        embedder = get_embedder()
        try:
            for document in documents:
                count = index_document(document, embedder, force=options["force"])
                self.stdout.write(f"{document.title} : {count} passage(s) indexé(s)")
        except EmbeddingError as exc:
            raise CommandError(str(exc))