"""Exemples de résumés et de quiz pour le rapport, et grilles d'évaluation qualitative.

Répond à la section 6.6 du cahier des charges :
« Exemples de résumés produits pour différents documents. Exemples de quiz générés
(avec correction). Évaluation qualitative de la pertinence des résumés et quiz. »

1) Exporter (lecture seule de la base) :
   python manage.py export_examples [--document 8 --document 5] [--out evaluation/exemples]
   -> resumes.md, quiz.md (à copier dans le rapport)
   -> grille_resumes.csv, grille_quiz.csv (à remplir dans Excel)
2) Après relecture, calculer les résultats :
   python manage.py export_examples --score-summaries evaluation/exemples/grille_resumes.csv
   python manage.py export_examples --score-quiz evaluation/exemples/grille_quiz.csv

Critères (ceux de la section 6.7 du cahier des charges) :
- résumés : fidelite, concision, clarte, notées de 1 (mauvais) à 5 (excellent) ;
- quiz, par question : coherente (la question a une seule bonne réponse, justifiée par
  le cours), pertinente (elle porte sur une notion importante du cours),
  niveau_adapte (la difficulté correspond au niveau demandé) : oui / non.
"""

import statistics
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseDocument
from courses.services.evaluation import read_sheet, wilson_interval, write_sheet
from quizzes.models import Quiz
from summaries.models import Summary

SUMMARY_COLUMNS = ["id", "cours", "niveau", "methode", "nb_mots", "resume",
                   "fidelite", "concision", "clarte", "commentaire"]
QUIZ_COLUMNS = ["id", "quiz", "cours", "difficulte", "question", "choix", "bonne_reponse",
                "explication", "coherente", "pertinente", "niveau_adapte", "commentaire"]
SUMMARY_CRITERIA = ("fidelite", "concision", "clarte")
QUIZ_CRITERIA = ("coherente", "pertinente", "niveau_adapte")
LEVEL_ORDER = {"short": 0, "medium": 1, "detailed": 2}


class Command(BaseCommand):
    help = "Exporte des exemples de résumés et de quiz, et les grilles d'évaluation qualitative."

    def add_arguments(self, parser):
        parser.add_argument("--document", type=int, action="append", help="Identifiant d'un cours (répétable)")
        parser.add_argument("--out", default=str(settings.BASE_DIR / "evaluation" / "exemples"))
        parser.add_argument("--score-summaries", metavar="CSV", help="Résultats d'une grille de résumés remplie")
        parser.add_argument("--score-quiz", metavar="CSV", help="Résultats d'une grille de quiz remplie")

    def handle(self, *args, **options):
        if options["score_summaries"]:
            return self._score_summaries(options["score_summaries"])
        if options["score_quiz"]:
            return self._score_quiz(options["score_quiz"])
        self._export(options)

    # --- Export ---------------------------------------------------------------------

    def _export(self, options):
        documents = CourseDocument.objects.filter(status=CourseDocument.Status.READY)
        if options["document"]:
            documents = documents.filter(pk__in=options["document"])
        summaries = sorted(
            Summary.objects.filter(document__in=documents).select_related("document"),
            key=lambda s: (s.document.title, LEVEL_ORDER.get(s.level, 9), s.provider),
        )
        quizzes = Quiz.objects.filter(document__in=documents).select_related("document").prefetch_related(
            "questions__choices"
        )
        if not summaries and not quizzes:
            raise CommandError("Aucun résumé ni quiz pour ces cours : générez-en depuis l'interface.")

        out = Path(options["out"])
        out.mkdir(parents=True, exist_ok=True)

        lines = ["# Exemples de résumés", ""]
        rows = []
        for number, summary in enumerate(summaries, start=1):
            method = f"{summary.provider}" + (f" ({summary.model_name})" if summary.model_name else "")
            words = len(summary.content.split())
            lines += [
                f"## {summary.document.title} — résumé {summary.get_level_display().lower()}",
                "",
                f"*Méthode : {method} · {words} mots · {summary.section_count} section(s) · "
                f"{summary.document.page_count} page(s) dans le cours*",
                "",
                summary.content,
                "",
            ]
            rows.append({"id": number, "cours": summary.document.title, "niveau": summary.get_level_display(),
                         "methode": method, "nb_mots": words, "resume": summary.content})
        (out / "resumes.md").write_text("\n".join(lines), encoding="utf-8")
        write_sheet(out / "grille_resumes.csv", SUMMARY_COLUMNS, rows)

        lines, rows, number = ["# Exemples de quiz (avec correction)", ""], [], 0
        for quiz in quizzes:
            lines += [f"## {quiz.title}", "",
                      f"*Cours : {quiz.document.title} · difficulté : {quiz.get_difficulty_display().lower()} · "
                      f"modèle : {quiz.provider} {quiz.model_name}*", ""]
            for question in quiz.questions.all():
                number += 1
                choices = list(question.choices.all())
                good = next((c.text for c in choices if c.is_correct), "")
                lines.append(f"**{question.order}. {question.text}**")
                lines.append("")
                for letter, choice in zip("ABCD", choices):
                    mark = " ✔ (bonne réponse)" if choice.is_correct else ""
                    lines.append(f"- {letter}. {choice.text}{mark}")
                lines += ["", f"*Explication : {question.explanation}*", ""]
                rows.append({
                    "id": number, "quiz": quiz.title, "cours": quiz.document.title,
                    "difficulte": quiz.get_difficulty_display(), "question": question.text,
                    "choix": " | ".join(c.text for c in choices), "bonne_reponse": good,
                    "explication": question.explanation,
                })
        (out / "quiz.md").write_text("\n".join(lines), encoding="utf-8")
        write_sheet(out / "grille_quiz.csv", QUIZ_COLUMNS, rows)

        self.stdout.write(f"{len(summaries)} résumé(s) et {number} question(s) de quiz exportés dans {out}")
        self.stdout.write("  resumes.md, quiz.md : exemples à insérer dans le rapport")
        self.stdout.write("  grille_resumes.csv : notez fidelite, concision, clarte de 1 à 5")
        self.stdout.write("  grille_quiz.csv : répondez oui/non à coherente, pertinente, niveau_adapte")

    # --- Résultats des grilles ------------------------------------------------------------

    def _read(self, path, criteria):
        try:
            rows = read_sheet(path)
        except OSError as exc:
            raise CommandError(str(exc))
        if rows and any(c not in rows[0] for c in criteria):
            raise CommandError(f"Colonnes attendues : {', '.join(criteria)}")
        return rows

    def _score_summaries(self, path):
        rows = self._read(path, SUMMARY_CRITERIA)
        groups = {}
        for row in rows:
            values = {}
            for criterion in SUMMARY_CRITERIA:
                raw = (row.get(criterion) or "").strip()
                if not raw:
                    continue
                if raw not in {"1", "2", "3", "4", "5"}:
                    raise CommandError(f"Ligne {row.get('id')} : « {criterion} » doit valoir 1 à 5 (lu : {raw!r}).")
                values[criterion] = int(raw)
            if values:
                groups.setdefault(row.get("methode", "?"), []).append(values)
        if not groups:
            raise CommandError("Aucune note trouvée : remplissez fidelite, concision et clarte (1 à 5).")
        self.stdout.write("Moyenne (écart-type) des notes de 1 à 5, par méthode de résumé :")
        self.stdout.write(f"  {'méthode':<45} {'n':>3}" + "".join(f"{c:>15}" for c in SUMMARY_CRITERIA))
        for method, items in sorted(groups.items()):
            cells = []
            for criterion in SUMMARY_CRITERIA:
                notes = [item[criterion] for item in items if criterion in item]
                if not notes:
                    cells.append(f"{'-':>15}")
                    continue
                spread = statistics.stdev(notes) if len(notes) > 1 else 0.0
                cells.append(f"{statistics.mean(notes):>9.2f} ({spread:.1f})")
            self.stdout.write(f"  {method[:45]:<45} {len(items):>3}" + "".join(cells))
        total = sum(len(items) for items in groups.values())
        if total < 10:
            self.stdout.write(self.style.WARNING(f"{total} résumés notés : résultat indicatif."))

    def _score_quiz(self, path):
        rows = self._read(path, QUIZ_CRITERIA)
        self.stdout.write("Proportion de « oui » par critère (intervalle de confiance à 95 %) :")
        reviewed = 0
        for criterion in QUIZ_CRITERIA:
            answers = [(row.get(criterion) or "").strip().lower() for row in rows]
            bad = sorted({a for a in answers if a and a not in ("oui", "non")})
            if bad:
                raise CommandError(f"« {criterion} » doit valoir oui ou non (lu : {bad}).")
            filled = [a for a in answers if a]
            reviewed = max(reviewed, len(filled))
            if not filled:
                self.stdout.write(f"  {criterion:<14} non rempli")
                continue
            yes = filled.count("oui")
            low, high = wilson_interval(yes, len(filled))
            self.stdout.write(f"  {criterion:<14} {yes / len(filled):6.1%}  [{low:.0%} - {high:.0%}]  ({yes}/{len(filled)})")
        if not reviewed:
            raise CommandError("Aucune question relue : remplissez coherente, pertinente, niveau_adapte.")
        if reviewed < 30:
            self.stdout.write(self.style.WARNING(f"{reviewed} questions relues : résultat indicatif."))
