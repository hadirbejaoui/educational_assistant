from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseDocument


class Command(BaseCommand):
    help = "Liste les passages d'un document qui contiennent un texte (lecture seule)."

    def add_arguments(self, parser):
        parser.add_argument("document", type=int)
        parser.add_argument("text")

    def handle(self, *args, **options):
        try:
            document = CourseDocument.objects.get(pk=options["document"])
        except CourseDocument.DoesNotExist:
            raise CommandError("Document introuvable.")
        needle = options["text"]
        chunks = document.chunks.filter(text__icontains=needle)
        self.stdout.write(f"{chunks.count()} passage(s) contenant ce texte")
        for chunk in chunks:
            position = chunk.text.lower().find(needle.lower())
            snippet = " ".join(chunk.text[max(0, position - 60) : position + 140].split())
            pages = (
                f"p.{chunk.page_start}"
                if chunk.page_start == chunk.page_end
                else f"p.{chunk.page_start}-{chunk.page_end}"
            )
            line = f"  #{chunk.chunk_index} {pages} {snippet}"
            self.stdout.write(line.encode("ascii", "replace").decode())
