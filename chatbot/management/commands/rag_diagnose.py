import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chatbot.services.rag import _select_hits
from courses.models import CourseDocument
from courses.services.embeddings import get_embedder
from courses.services.retrieval import lexical_rank, search_chunks


def _ascii(text, limit=90):
    """Évite les erreurs d'affichage de l'arabe dans la console Windows."""
    text = " ".join(text.split())[:limit]
    return text.encode("ascii", "replace").decode()


def _pages(chunk):
    if chunk.page_start == chunk.page_end:
        return f"p.{chunk.page_start}"
    return f"p.{chunk.page_start}-{chunk.page_end}"


class Command(BaseCommand):
    help = "Affiche les meilleurs passages et leurs scores pour des questions de test."

    def add_arguments(self, parser):
        parser.add_argument("document", type=int, help="Identifiant du document")
        parser.add_argument("questions", nargs="+", help="Une ou plusieurs questions")
        parser.add_argument("--k", type=int, default=8)
        parser.add_argument(
            "--find",
            help="Texte d'un passage attendu : affiche son rang pour la 1re question",
        )

    def handle(self, *args, **options):
        try:
            document = CourseDocument.objects.get(pk=options["document"])
        except CourseDocument.DoesNotExist:
            raise CommandError("Document introuvable.")

        embedder = get_embedder()
        self.stdout.write(
            f"Seuil RAG_MIN_SCORE = {settings.RAG_MIN_SCORE} | "
            f"fenetre RAG_SCORE_WINDOW = {settings.RAG_SCORE_WINDOW}\n"
        )

        for question in options["questions"]:
            started = time.time()
            hits = search_chunks(document, question, k=options["k"], embedder=embedder)
            kept = {id(hit) for hit in _select_hits(hits)}
            verdict = "REPONSE" if kept else "REFUS"
            self.stdout.write(
                f"\nQ : {_ascii(question, 120)}  ({time.time() - started:.1f} s) -> {verdict}"
            )
            for rank, hit in enumerate(hits, start=1):
                mark = "OK " if id(hit) in kept else "-- "
                ranks = f"vect.{hit.dense_rank} bm25.{hit.lexical_rank or '-'}"
                self.stdout.write(
                    f"  {mark}{rank}. cos {hit.score:.3f} rrf {hit.rrf_score:.4f} "
                    f"({ranks:<15}) {_pages(hit.chunk):<8} {_ascii(hit.chunk.text, 70)}"
                )

        if options["find"]:
            self._report_rank(document, options["questions"][0], options["find"], embedder)

    def _report_rank(self, document, question, needle, embedder):
        """Rang d'un passage attendu : final, vectoriel seul et mots-clés seuls."""
        wanted = {chunk.id for chunk in document.chunks.filter(text__icontains=needle)}
        if not wanted:
            self.stdout.write(f"\nAucun passage ne contient {needle!r}.")
            return

        fused = search_chunks(document, question, k=1000, embedder=embedder)
        by_score = sorted(fused, key=lambda hit: -hit.score)
        lexical = lexical_rank([hit.chunk for hit in fused], question, limit=1000)

        self.stdout.write(
            f"\nRang du passage contenant {needle!r} (question : {_ascii(question, 60)})"
        )
        for final_rank, hit in enumerate(fused, start=1):
            if hit.chunk.id not in wanted:
                continue
            vector_rank = next(
                i for i, other in enumerate(by_score, start=1) if other.chunk.id == hit.chunk.id
            )
            word_rank = next(
                (i for i, chunk in enumerate(lexical, start=1) if chunk.id == hit.chunk.id),
                None,
            )
            self.stdout.write(
                f"  #{hit.chunk.chunk_index} {_pages(hit.chunk)} : "
                f"rang final {final_rank}/{len(fused)} | "
                f"rang vectoriel {vector_rank} | "
                f"rang mots-cles {word_rank or 'absent'} | "
                f"score {hit.score:.3f}"
            )