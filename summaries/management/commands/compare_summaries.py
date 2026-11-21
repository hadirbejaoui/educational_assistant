"""Compare les méthodes de résumé sur les mêmes cours, sans rien enregistrer en base.

python manage.py compare_summaries --document 8 --document 5 [--level short --level medium]
                                   [--methods extractive,huggingface,llm]

Pour chaque cours, niveau et méthode : le résumé, sa longueur, le taux de compression
(mots du résumé / mots du cours) et le temps de calcul. Écrit :
- evaluation/exemples/comparaison_resumes.md : à insérer dans le rapport ;
- evaluation/exemples/grille_comparaison_resumes.csv : à noter (fidélité, concision,
  clarté de 1 à 5), puis : python manage.py export_examples --score-summaries <fichier>

Conseil pour une évaluation honnête : noter les résumés sans regarder la colonne
« methode » (la masquer dans Excel), pour ne pas favoriser une méthode.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.commands.export_examples import SUMMARY_COLUMNS
from courses.models import CourseDocument
from courses.services.evaluation import write_sheet
from summaries.models import Summary
from summaries.services.errors import SummaryError
from summaries.services.providers.extractive import ExtractiveProvider
from summaries.services.providers.huggingface import HuggingFaceProvider
from summaries.services.sections import build_sections
from summaries.services.summarization import build_summary, section_limit


def make_provider(name):
    if name == "extractive":
        return ExtractiveProvider()
    if name == "huggingface":
        return HuggingFaceProvider(settings.SUMMARY_MODEL_NAME)
    if name == "llm":
        from summaries.services.providers.llm import LLMSummaryProvider

        try:
            return LLMSummaryProvider()
        except SummaryError as exc:  # LLM non configuré : message clair plutôt qu'une trace
            raise CommandError(f"Méthode « llm » indisponible : {exc} (ou retirez-la de --methods)")
    raise CommandError(f"Méthode inconnue : {name} (extractive, huggingface ou llm)")


class Command(BaseCommand):
    help = "Compare les méthodes de résumé (extractive, modèle Hugging Face, LLM) sur vos cours."

    def add_arguments(self, parser):
        parser.add_argument("--document", type=int, action="append", required=True)
        parser.add_argument("--level", action="append", choices=list(Summary.Level.values))
        parser.add_argument("--methods", default="extractive,huggingface,llm")
        parser.add_argument("--out", default=str(settings.BASE_DIR / "evaluation" / "exemples"))

    def handle(self, *args, **options):
        levels = options["level"] or ["short", "medium"]
        providers = [make_provider(name.strip()) for name in options["methods"].split(",") if name.strip()]
        labels = dict(Summary.Level.choices)
        out = Path(options["out"])
        out.mkdir(parents=True, exist_ok=True)

        lines = ["# Comparaison des méthodes de résumé", "",
                 "| Cours | Niveau | Méthode | Mots | Compression | Temps |", "|---|---|---|---|---|---|"]
        details, rows = [], []
        for document_id in options["document"]:
            try:
                document = CourseDocument.objects.get(pk=document_id)
            except CourseDocument.DoesNotExist:
                raise CommandError(f"Document {document_id} introuvable.")
            pages = list(document.pages.all())
            source_words = sum(len(page.text.split()) for page in pages) or 1
            if not any(page.text.strip() for page in pages):
                raise CommandError(f"« {document.title} » ne contient aucun texte.")
            for level in levels:
                for provider in providers:
                    method = f"{provider.name} ({provider.model_name})"
                    limit = section_limit(provider, level)
                    sections = build_sections(pages, limit)
                    started = time.perf_counter()
                    try:
                        content = build_summary(sections, level, provider, limit)
                    except SummaryError as exc:
                        # Une panne (délai dépassé...) est un résultat à noter, pas une raison d'arrêter
                        elapsed = time.perf_counter() - started
                        lines.append(f"| {document.title} | {labels[level]} | {method} | échec | — | "
                                     f"{elapsed:.1f} s |")
                        details += [f"## {document.title} — {labels[level].lower()} — {method}", "",
                                    f"*Échec : {exc}*", ""]
                        self.stdout.write(f"{document.title} | {labels[level]} | {provider.name} : "
                                          f"ÉCHEC après {elapsed:.1f} s ({exc})")
                        continue
                    elapsed = time.perf_counter() - started
                    words = len(content.split())
                    lines.append(f"| {document.title} | {labels[level]} | {method} | {words} | "
                                 f"{words / source_words:.1%} | {elapsed:.1f} s |")
                    details += [f"## {document.title} — {labels[level].lower()} — {method}", "",
                                f"*{len(sections)} section(s) de {limit} caractères au plus*", "", content, ""]
                    rows.append({"id": len(rows) + 1, "cours": document.title, "niveau": labels[level],
                                 "methode": method, "nb_mots": words, "resume": content})
                    self.stdout.write(f"{document.title} | {labels[level]} | {provider.name} : "
                                      f"{words} mots en {elapsed:.1f} s")

        (out / "comparaison_resumes.md").write_text("\n".join(lines + [""] + details), encoding="utf-8")
        write_sheet(out / "grille_comparaison_resumes.csv", SUMMARY_COLUMNS, rows)
        self.stdout.write(f"Écrit : {out / 'comparaison_resumes.md'} et {out / 'grille_comparaison_resumes.csv'}")
