"""Démonstration de bout en bout, en ligne de commande, sans passer par l'interface web.

    python manage.py demo                          # cours d'exemple, avec le LLM configuré
    python manage.py demo --sans-llm               # sans LLM : prétraitement, recherche, résumé extractif
    python manage.py demo --fichier mon_cours.pdf  # sur un autre document (PDF ou TXT)
    python manage.py demo --garder                 # conserve le compte et le cours de démonstration

Étapes : import et prétraitement, indexation (embeddings), recherche hybride, résumés des trois
niveaux, génération d'un QCM, questions au chatbot (dont une hors cours).

Un compte temporaire est créé pour l'occasion, puis supprimé avec tout ce qu'il contient
(cours, fichier, résumés, quiz, conversation) : la commande ne touche à aucune donnée existante.
"""

import time
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from chatbot.models import Conversation
from chatbot.services.rag import answer_question
from courses.models import CourseDocument
from courses.services.embeddings import EmbeddingError, get_embedder, index_document
from courses.services.processing import process_document
from courses.services.retrieval import search_chunks
from llm import LLMError
from quizzes.services.errors import QuizError
from quizzes.services.generation import generate_quiz
from summaries.services.errors import SummaryError
from summaries.services.providers.extractive import ExtractiveProvider
from summaries.services.summarization import generate_summary

DEFAULT_FILE = Path(settings.BASE_DIR) / "demo" / "cours_exemple.txt"
DEFAULT_QUESTION = "Pourquoi un système RAG doit-il savoir refuser de répondre ?"
OUT_OF_SCOPE = "Quelle est la capitale de l'Australie ?"
LEVELS = (("short", "court"), ("medium", "moyen"), ("detailed", "détaillé"))


class Command(BaseCommand):
    help = "Démonstration de bout en bout sur un cours d'exemple (compte temporaire, supprimé à la fin)."

    def add_arguments(self, parser):
        parser.add_argument("--fichier", default=str(DEFAULT_FILE), help="Document PDF ou TXT à utiliser")
        parser.add_argument("--question", default=DEFAULT_QUESTION, help="Question posée au chatbot")
        parser.add_argument("--sans-llm", action="store_true",
                            help="Sans LLM : résumé extractif, ni QCM ni réponse générée")
        parser.add_argument("--garder", action="store_true", help="Conserver le compte et le cours de démonstration")

    def handle(self, *args, **options):
        path = Path(options["fichier"])
        if not path.is_file() or path.suffix.lower() not in (".pdf", ".txt"):
            raise CommandError(f"Fichier introuvable ou non pris en charge (PDF ou TXT) : {path}")
        self.with_llm = not options["sans_llm"]
        username = f"demo-{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, email=f"{username}@demo.invalid", password=None)
        document = None
        try:
            document = self._import(user, path)
            indexed = self._index(document)
            if indexed:
                self._search(document, options["question"])
            self._summaries(document)
            if self.with_llm:
                self._quiz(document)
                if indexed:
                    self._chat(document, user, options["question"])
        finally:
            if options["garder"]:
                self.stdout.write(f"\nCompte « {user.username} » et cours n° {document.pk if document else '-'} "
                                  "conservés (définissez un mot de passe dans /admin/ pour vous connecter).")
            else:
                if document:
                    document.delete()  # supprime aussi le fichier sur le disque
                user.delete()
                self.stdout.write("\nDonnées de démonstration supprimées.")

    # --- Étapes -------------------------------------------------------------------------

    def _step(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {title}"))
        return time.perf_counter()

    def _done(self, started, text=""):
        self.stdout.write(f"   {text} ({time.perf_counter() - started:.1f} s)")

    def _import(self, user, path):
        started = self._step("1. Import et prétraitement")
        document = CourseDocument(owner=user, title=path.stem[:255], file_type=path.suffix.lower().lstrip("."),
                                  file_size=path.stat().st_size)
        with path.open("rb") as handle:
            document.file.save(path.name, File(handle), save=True)
        document = process_document(document)
        if document.status != CourseDocument.Status.READY:
            raise CommandError(f"Traitement échoué : {document.error_message}")
        chunks = list(document.chunks.all())
        self._done(started, f"« {document.title} » : {document.page_count} page(s), {len(chunks)} passage(s), "
                            f"{sum(c.char_count for c in chunks) // max(len(chunks), 1)} caractères en moyenne")
        return document

    def _index(self, document):
        started = self._step("2. Indexation (embeddings)")
        try:
            count = index_document(document, get_embedder())
        except EmbeddingError as exc:
            self.stdout.write(self.style.WARNING(f"   Indexation impossible : {exc} — recherche et chatbot ignorés."))
            return False
        self._done(started, f"{count} passage(s) encodé(s) par {settings.EMBEDDING_MODEL_NAME}")
        return True

    def _search(self, document, question):
        started = self._step("3. Recherche hybride (vecteurs + BM25, fusion RRF)")
        self.stdout.write(f"   Question : {question}")
        hits = search_chunks(document, question, k=3)
        for rank, hit in enumerate(hits, start=1):
            excerpt = " ".join(hit.chunk.text.split())[:110]
            self.stdout.write(f"   {rank}. page {hit.chunk.page_start}, cosinus {hit.score:.3f} : {excerpt}…")
        self._done(started, f"{len(hits)} passage(s)")

    def _summaries(self, document):
        provider = None if self.with_llm else ExtractiveProvider()
        for level, label in LEVELS:
            started = self._step(f"4. Résumé {label}")
            try:
                summary = generate_summary(document, level, provider)
            except SummaryError as exc:
                self.stdout.write(self.style.WARNING(f"   {exc}"))
                if provider is None:
                    self.stdout.write("   Relancez avec --sans-llm pour un résumé extractif.")
                return
            self.stdout.write("   " + summary.content.replace("\n", "\n   "))
            self._done(started, f"{len(summary.content.split())} mots, méthode {summary.provider} ({summary.model_name})")

    def _quiz(self, document):
        started = self._step("5. QCM (3 questions, difficulté moyenne)")
        try:
            quiz = generate_quiz(document, 3, "medium")
        except (QuizError, LLMError) as exc:
            self.stdout.write(self.style.WARNING(f"   {exc}"))
            return
        for question in quiz.questions.prefetch_related("choices"):
            self.stdout.write(f"   {question.order}. {question.text}")
            for letter, choice in zip("ABCD", question.choices.all()):
                self.stdout.write(f"      {letter}. {choice.text}{'   <- bonne réponse' if choice.is_correct else ''}")
            self.stdout.write(f"      Explication : {question.explanation}")
        self._done(started, f"{quiz.questions.count()} question(s)")

    def _chat(self, document, user, question):
        conversation = Conversation.objects.create(document=document, owner=user, title="Démonstration")
        for number, text in ((6, question), (7, OUT_OF_SCOPE)):
            started = self._step(f"{number}. Chatbot : {text}")
            try:
                answer = answer_question(conversation, text)
            except (LLMError, EmbeddingError) as exc:
                self.stdout.write(self.style.WARNING(f"   {exc}"))
                return
            self.stdout.write(f"   {answer.content}")
            for source in answer.sources:
                if source["cited"]:
                    self.stdout.write(f"   [{source['n']}] page {source['page_start']} : {source['excerpt'][:90]}…")
            self._done(started, "réponse appuyée sur le cours" if answer.grounded else "refus : hors cours")
