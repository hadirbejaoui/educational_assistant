"""Fidélité des réponses : une réponse est-elle appuyée par ses sources ?

Aucune métrique automatique n'est fiable pour cela avec un petit modèle local :
on fait donc relire un échantillon par un humain.

1) Générer la grille de relecture (appelle le vrai LLM, compter ~1 min par question) :
   python manage.py rag_faithfulness --sample 10 --out evaluation/fidelite.csv
2) Ouvrir le CSV dans Excel, remplir la colonne « appuyee » avec oui / partiel / non
   (et « commentaire » si besoin), enregistrer en CSV.
3) Calculer le taux :
   python manage.py rag_faithfulness --score evaluation/fidelite.csv

Définitions pour la relecture :
- oui     : chaque affirmation de la réponse se retrouve dans les sources citées ;
- partiel : l'essentiel est appuyé, mais un détail est ajouté ou déformé ;
- non     : une affirmation importante n'est pas dans les sources (invention) ;
- refus   : rempli automatiquement quand le chatbot a refusé de répondre ;
- erreur  : rempli automatiquement quand le LLM a échoué (délai dépassé...).
"""

import random
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chatbot.models import ChatMessage
from chatbot.services.rag import answer_question
from courses.models import CourseDocument
from courses.services.embeddings import EmbeddingError, get_embedder
from courses.services.evaluation import load_course_questions, read_sheet, wilson_interval, write_sheet
from llm import LLMError, get_llm_client

COLUMNS = ["id", "cours", "question", "reponse", "sources_citees", "secondes", "modele", "appuyee", "commentaire"]
VERDICTS = ("oui", "partiel", "non", "refus", "erreur")


class Command(BaseCommand):
    help = "Génère une grille de relecture de la fidélité des réponses, ou calcule le taux à partir d'une grille remplie."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(settings.BASE_DIR / "evaluation" / "rag_questions.json"))
        parser.add_argument("--sample", type=int, default=10, help="Nombre de questions tirées au hasard")
        parser.add_argument("--seed", type=int, default=42, help="Graine du tirage (reproductible)")
        parser.add_argument("--out", default=str(settings.BASE_DIR / "evaluation" / "fidelite.csv"))
        parser.add_argument("--score", metavar="CSV", help="Calcule le taux de fidélité d'une grille remplie")

    def handle(self, *args, **options):
        if options["score"]:
            self._score(options["score"])
        else:
            self._generate(options)

    def _generate(self, options):
        try:
            courses = load_course_questions(options["file"])
        except (OSError, ValueError) as exc:
            raise CommandError(f"Fichier d'évaluation invalide : {exc}")
        pool = [(course["document_id"], item["question"]) for course in courses for item in course["questions"]]
        random.Random(options["seed"]).shuffle(pool)
        pool = pool[: options["sample"]]

        embedder, client = get_embedder(), get_llm_client()
        rows = []
        for number, (document_id, question) in enumerate(pool, start=1):
            document = CourseDocument.objects.get(pk=document_id)
            # Conversation temporaire, jamais enregistrée : pas d'historique
            conversation = SimpleNamespace(document=document, messages=ChatMessage.objects.none())
            started = time.perf_counter()
            try:
                answer = answer_question(conversation, question, embedder=embedder, client=client)
            except EmbeddingError as exc:
                raise CommandError(str(exc))
            except LLMError as exc:
                # Une panne (délai dépassé...) est un résultat à garder, pas une raison d'arrêter
                elapsed = time.perf_counter() - started
                rows.append({
                    "id": number, "cours": document.title, "question": question,
                    "reponse": f"ERREUR : {exc}", "sources_citees": "", "secondes": f"{elapsed:.1f}",
                    "modele": f"{client.name}/{client.model_name}", "appuyee": "erreur", "commentaire": "",
                })
                self.stdout.write(f"{number}/{len(pool)} : {elapsed:.0f} s (erreur : {exc})")
                continue
            elapsed = time.perf_counter() - started
            cited = [s for s in answer.sources if s["cited"]] or answer.sources
            sources = "\n\n".join(
                f"[{s['n']}] p.{s['page_start']}-{s['page_end']} : "
                + document.chunks.get(pk=s["chunk_id"]).text[:1200]
                for s in cited
            )
            rows.append({
                "id": number, "cours": document.title, "question": question,
                "reponse": answer.content, "sources_citees": sources,
                "secondes": f"{elapsed:.1f}", "modele": f"{client.name}/{client.model_name}",
                "appuyee": "" if answer.grounded else "refus", "commentaire": "",
            })
            self.stdout.write(f"{number}/{len(pool)} : {elapsed:.0f} s {'(refus)' if not answer.grounded else ''}")

        # Point-virgule et BOM UTF-8 : le CSV s'ouvre correctement dans Excel en français
        write_sheet(options["out"], COLUMNS, rows)
        times = [float(r["secondes"]) for r in rows]
        self.stdout.write(f"Grille écrite : {options['out']}")
        if times:
            self.stdout.write(f"Temps de réponse : moyenne {sum(times) / len(times):.1f} s, max {max(times):.1f} s")
        self.stdout.write("Remplissez la colonne « appuyee » (oui / partiel / non), puis : "
                          f"python manage.py rag_faithfulness --score {options['out']}")

    def _score(self, path):
        try:
            rows = read_sheet(path)
        except OSError as exc:
            raise CommandError(str(exc))
        if rows and "appuyee" not in rows[0]:
            raise CommandError("Colonne « appuyee » introuvable : le fichier a-t-il été enregistré au format CSV ?")
        verdicts = [(r.get("appuyee") or "").strip().lower() for r in rows]
        unknown = [v for v in verdicts if v and v not in VERDICTS]
        if unknown:
            raise CommandError(f"Valeurs inconnues dans « appuyee » : {sorted(set(unknown))} (attendu : {', '.join(VERDICTS)})")
        missing = verdicts.count("")
        answered = [v for v in verdicts if v in ("oui", "partiel", "non")]
        n = len(answered)
        self.stdout.write(f"{len(rows)} lignes | {n} réponses relues | {verdicts.count('refus')} refus | "
                          f"{verdicts.count('erreur')} erreurs du LLM | {missing} non relues")
        if not n:
            raise CommandError("Aucune réponse relue : remplissez la colonne « appuyee ».")
        for label in ("oui", "partiel", "non"):
            count = answered.count(label)
            low, high = wilson_interval(count, n)
            self.stdout.write(f"  {label:<8} {count / n:6.1%}  IC95 [{low:.0%} - {high:.0%}]  ({count}/{n})")
        if n < 30:
            self.stdout.write(self.style.WARNING(
                f"Échantillon de {n} réponses : les intervalles sont larges, à présenter comme une "
                "indication, pas comme une mesure précise."
            ))
