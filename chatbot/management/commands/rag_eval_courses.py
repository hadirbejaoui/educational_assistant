"""Évaluation et calibration du RAG sur vos cours réels.

python manage.py rag_eval_courses [--file evaluation/rag_questions.json] [--k 3]

Mesure, pour chaque poids lexical :
- succès@K (au moins un passage pertinent dans les K premiers), rappel@K, MRR ;
- taux de refus à tort (question avec réponse refusée par le seuil RAG_MIN_SCORE) ;
- taux d'acceptation à tort (question hors cours non refusée par le seuil).
Puis propose des valeurs de RAG_MIN_SCORE, RAG_SCORE_WINDOW et
RETRIEVAL_LEXICAL_WEIGHT, avec des intervalles de confiance qui disent si
l'échantillon suffit pour conclure.

Seule l'étape de recherche est évaluée : le LLM peut encore refuser ensuite
(NON_TROUVE). La fidélité des réponses se mesure avec rag_faithfulness.
"""

from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from chatbot.services.rag import _select_hits
from courses.models import CourseDocument
from courses.services.embeddings import EmbeddingError, get_embedder
from courses.services.evaluation import (
    chunk_is_relevant,
    load_course_questions,
    ndcg_at_k,
    rank_stored_document,
    recall_at_k,
    reciprocal_rank,
    wilson_interval,
)

WEIGHTS = (0.0, 0.5, 1.0, 2.0)
THRESHOLDS = [round(0.70 + 0.005 * i, 3) for i in range(45)]   # 0,700 à 0,920
WINDOWS = (0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15)
MIN_ANSWERABLE, MIN_OUT_OF_SCOPE = 20, 10   # en dessous : échantillon trop petit
# On ne recommande de changer un réglage que si, en net, au moins 2 questions y gagnent :
# une seule question qui change de rang relève du hasard sur des échantillons de cette taille.
MIN_NET_GAIN = 2


def _ascii(text, limit=60):
    return " ".join(text.split())[:limit].encode("ascii", "replace").decode()


def _rate(numerator, total):
    low, high = wilson_interval(numerator, total)
    value = numerator / total if total else 0.0
    return f"{value:6.1%} [{low:.0%}-{high:.0%}] ({numerator}/{total})"


class Command(BaseCommand):
    help = "Évalue la recherche et calibre les seuils du chatbot sur vos cours réels."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(settings.BASE_DIR / "evaluation" / "rag_questions.json"))
        parser.add_argument("--k", type=int, default=3, help="K des métriques @K (défaut : 3)")
        parser.add_argument("--details", action="store_true", help="Affiche chaque question")

    def handle(self, *args, **options):
        try:
            courses = load_course_questions(options["file"])
        except (OSError, ValueError) as exc:
            raise CommandError(f"Fichier d'évaluation invalide : {exc}")
        k = options["k"]
        top_k = settings.RETRIEVAL_TOP_K
        embedder = get_embedder()

        answerable, out_of_scope = [], []
        for course in courses:
            try:
                document = CourseDocument.objects.get(pk=course["document_id"])
            except CourseDocument.DoesNotExist:
                raise CommandError(f"Document {course['document_id']} introuvable.")
            if not document.chunks.filter(embedding_model=embedder.model_name).exists():
                raise CommandError(f"« {document.title} » n'est pas indexé : python manage.py index_documents")
            try:
                for item in course["questions"]:
                    ranking = rank_stored_document(document, item["question"], embedder, WEIGHTS)
                    relevant = {cid for cid, chunk in ranking["chunks"].items() if chunk_is_relevant(chunk, item)}
                    if not relevant:
                        self.stderr.write(f"Aucun passage ne couvre la réponse attendue : {_ascii(item['question'])}")
                    answerable.append({"course": document.title, "question": item["question"],
                                       "ranking": ranking, "relevant": relevant})
                for question in course["out_of_scope"]:
                    out_of_scope.append({"course": document.title, "question": question,
                                         "ranking": rank_stored_document(document, question, embedder, WEIGHTS)})
            except EmbeddingError as exc:
                raise CommandError(str(exc))

        n_ans, n_out = len(answerable), len(out_of_scope)
        self.stdout.write(f"{len(courses)} cours | {n_ans} questions avec réponse | {n_out} hors cours | "
                          f"modèle {embedder.model_name} | top-k du chatbot = {top_k}\n")

        # 1. Qualité du classement selon le poids lexical
        self.stdout.write(f"=== Classement (K = {k}) ===")
        self.stdout.write(f"{'poids':>6} {'succès@K':>9} {'rappel@K':>9} {'MRR':>6} {'NDCG@K':>7}")
        ranking_scores = {}
        for weight in WEIGHTS:
            rows = []
            for row in answerable:
                order = row["ranking"]["orders"][weight]
                rows.append((
                    1.0 if row["relevant"] & set(order[:k]) else 0.0,
                    recall_at_k(order, row["relevant"], k),
                    reciprocal_rank(order, row["relevant"]),
                    ndcg_at_k(order, row["relevant"], k),
                ))
            means = [sum(column) / max(len(rows), 1) for column in zip(*rows)] if rows else [0, 0, 0, 0]
            ranking_scores[weight] = means
            marker = "  <- actuel" if weight == settings.RETRIEVAL_LEXICAL_WEIGHT else ""
            self.stdout.write(f"{weight:>6g} {means[0]:>9.3f} {means[1]:>9.3f} {means[2]:>6.3f} {means[3]:>7.3f}{marker}")
        current_weight = settings.RETRIEVAL_LEXICAL_WEIGHT
        best_weight = current_weight if current_weight in WEIGHTS else 1.0

        def first_rank(row, weight):
            order = row["ranking"]["orders"][weight]
            return next((i for i, cid in enumerate(order, start=1) if cid in row["relevant"]), 10**6)

        for weight in WEIGHTS:
            gains = sum(first_rank(r, weight) < first_rank(r, best_weight) for r in answerable)
            losses = sum(first_rank(r, weight) > first_rank(r, best_weight) for r in answerable)
            if gains - losses >= MIN_NET_GAIN and ranking_scores[weight][2] > ranking_scores[best_weight][2]:
                best_weight = weight
        self.stdout.write(f"Poids retenu : {best_weight:g} "
                          f"({'inchangé : aucun autre poids ne gagne nettement ' + str(MIN_NET_GAIN) + ' questions' if best_weight == current_weight else 'gain net mesuré'})")

        # 2. Seuil de refus
        def best_cosine(row, weight):
            order = row["ranking"]["orders"][weight][:top_k]
            return max((row["ranking"]["cosine"][cid] for cid in order), default=0.0)

        def error_rates(weight, threshold):
            false_refusals = sum(best_cosine(r, weight) < threshold for r in answerable)
            false_accepts = sum(best_cosine(r, weight) >= threshold for r in out_of_scope)
            return false_refusals, false_accepts

        current = settings.RAG_MIN_SCORE
        self.stdout.write(f"\n=== Seuil de refus (poids lexical {best_weight:g}) ===")
        fr, fa = error_rates(best_weight, current)
        self.stdout.write(f"Actuel RAG_MIN_SCORE = {current}")
        self.stdout.write(f"  refus à tort        : {_rate(fr, n_ans)}")
        self.stdout.write(f"  acceptation à tort  : {_rate(fa, n_out)}")

        scored = []
        for threshold in THRESHOLDS:
            fr, fa = error_rates(best_weight, threshold)
            balanced = (fr / max(n_ans, 1) + fa / max(n_out, 1)) / 2
            scored.append((balanced, abs(threshold - current), threshold, fr, fa))
        scored.sort()
        best_error, _, best_threshold, fr, fa = scored[0]
        plateau = sorted(t for e, _, t, _, _ in scored if abs(e - best_error) < 1e-9)
        current_errors = error_rates(best_weight, current)
        # On garde le seuil actuel s'il fait (presque) aussi bien : moins de 2 erreurs de plus
        if sum(current_errors) - (fr + fa) < MIN_NET_GAIN:
            best_threshold, (fr, fa) = current, current_errors
        self.stdout.write(f"Proposé RAG_MIN_SCORE = {best_threshold} "
                          f"(erreur équilibrée minimale atteinte de {plateau[0]} à {plateau[-1]})")
        self.stdout.write(f"  refus à tort        : {_rate(fr, n_ans)}")
        self.stdout.write(f"  acceptation à tort  : {_rate(fa, n_out)}")
        self.stdout.write("Distribution du meilleur cosinus :")
        for label, rows in (("avec réponse", answerable), ("hors cours", out_of_scope)):
            values = sorted(best_cosine(r, best_weight) for r in rows)
            if values:
                self.stdout.write(f"  {label:<13} min {values[0]:.3f} | médiane {values[len(values) // 2]:.3f} | max {values[-1]:.3f}")

        # 3. Fenêtre : garder le passage pertinent sans noyer le LLM sous les passages
        self.stdout.write(f"\n=== Fenêtre RAG_SCORE_WINDOW (seuil {best_threshold}) ===")
        self.stdout.write(f"{'fenêtre':>8} {'passage pertinent gardé':>24} {'passages envoyés (moy.)':>24}")
        window_rows = []
        for window in WINDOWS:
            kept_relevant, sizes, accepted = 0, [], 0
            with override_settings(RAG_MIN_SCORE=best_threshold, RAG_SCORE_WINDOW=window):
                for row in answerable:
                    order = row["ranking"]["orders"][best_weight][:top_k]
                    hits = [SimpleNamespace(id=cid, score=row["ranking"]["cosine"][cid],
                                            lexical_rank=row["ranking"]["lexical_rank"].get(cid))
                            for cid in order]
                    selected = _select_hits(hits)
                    if selected:
                        accepted += 1
                        sizes.append(len(selected))
                        kept_relevant += bool({h.id for h in selected} & row["relevant"])
            ratio = kept_relevant / accepted if accepted else 0.0
            window_rows.append((window, ratio, sum(sizes) / max(len(sizes), 1)))
            self.stdout.write(f"{window:>8.2f} {ratio:>23.1%} {window_rows[-1][2]:>24.1f}")
        best_ratio = max(r for _, r, _ in window_rows)
        current_window = settings.RAG_SCORE_WINDOW
        current_ratio = next((r for w, r, _ in window_rows if abs(w - current_window) < 1e-9), None)
        if current_ratio is not None and current_ratio >= best_ratio - 1e-9:
            # Une fenêtre plus étroite enverrait moins de passages, mais ce critère ne vérifie
            # qu'UN passage pertinent : une question qui en demande plusieurs y perdrait.
            best_window = current_window
        else:
            best_window = min(w for w, r, _ in window_rows if r >= best_ratio - 1e-9)

        # 4. Conclusion honnête
        self.stdout.write("\n=== Recommandation ===")
        self.stdout.write(f"RETRIEVAL_LEXICAL_WEIGHT={best_weight:g}  RAG_MIN_SCORE={best_threshold}  RAG_SCORE_WINDOW={best_window}")
        answer_min = min((best_cosine(r, best_weight) for r in answerable), default=1.0)
        out_max = max((best_cosine(r, best_weight) for r in out_of_scope), default=0.0)
        self.stdout.write(f"Marge de séparation : plus faible question avec réponse {answer_min:.3f} "
                          f"- plus forte question hors cours {out_max:.3f} = {answer_min - out_max:+.3f}")
        if answer_min - out_max < 0.02:
            self.stdout.write(self.style.WARNING(
                "Marge très faible : une nouvelle question proche du cours mais sans réponse "
                "passera probablement le seuil. Le refus final repose alors sur le LLM (NON_TROUVE)."
            ))
        if n_ans < MIN_ANSWERABLE or n_out < MIN_OUT_OF_SCOPE:
            self.stdout.write(self.style.WARNING(
                f"ÉCHANTILLON TROP PETIT POUR CONCLURE : {n_ans} questions avec réponse "
                f"(minimum conseillé {MIN_ANSWERABLE}) et {n_out} hors cours (minimum {MIN_OUT_OF_SCOPE}). "
                "Les intervalles de confiance ci-dessus sont larges : ne modifiez pas les réglages "
                "sur cette seule base."
            ))
        self.stdout.write(
            "Attention : seuils choisis sur les mêmes questions que celles qui les évaluent, "
            "donc résultat optimiste. Validez-les sur de nouvelles questions avant de les adopter."
        )

        if options["details"]:
            self.stdout.write("\n=== Détail (rang du 1er passage pertinent, meilleur cosinus) ===")
            for row in answerable:
                order = row["ranking"]["orders"][best_weight]
                rank = next((i for i, cid in enumerate(order, start=1) if cid in row["relevant"]), None)
                self.stdout.write(f"  [{_ascii(row['course'], 20)}] {_ascii(row['question'])} : rang {rank or '-'} | cos {best_cosine(row, best_weight):.3f}")
            for row in out_of_scope:
                self.stdout.write(f"  [hors cours] {_ascii(row['question'])} : cos {best_cosine(row, best_weight):.3f}")
