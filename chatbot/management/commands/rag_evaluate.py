import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chatbot.services.rag import (
    NOT_FOUND_TOKEN,
    PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    _build_context,
    _select_hits,
)
from courses.services import eval_corpus
from courses.services.embeddings import EmbeddingError, get_embedder
from courses.services.evaluation import (
    MODES,
    build_chunks,
    evaluate,
    index_chunks,
    pool_documents,
    rank,
    refusal_stats,
)
from llm import LLMError, get_llm_client


def _ascii(text, limit=70):
    """Évite les erreurs d'affichage dans la console Windows."""
    return " ".join(text.split())[:limit].encode("ascii", "replace").decode()


class Command(BaseCommand):
    help = (
        "Compare recherche vectorielle, BM25 et hybride (RRF) sur un corpus synthétique "
        "multi-matières : Precision@K, Recall@K, MRR, NDCG@K, temps de recherche "
        "et, en option, temps de génération du LLM."
    )

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=5, help="K des métriques @K (défaut : 5)")
        parser.add_argument(
            "--weights", default="",
            help="Poids lexicaux à comparer, ex. « 0.5,1,2 » (défaut : RETRIEVAL_LEXICAL_WEIGHT)",
        )
        parser.add_argument("--chunk-size", type=int, help="Taille des passages (défaut : CHUNK_SIZE)")
        parser.add_argument(
            "--llm", type=int, default=0, metavar="N",
            help="Mesure aussi le temps de génération sur N questions (appelle le LLM configuré)",
        )
        parser.add_argument("--details", action="store_true", help="Affiche chaque question")
        parser.add_argument(
            "--pooled", action="store_true",
            help="Réunit toutes les matières en une seule collection (plus difficile : "
                 "les autres cours deviennent des distracteurs)",
        )

    def handle(self, *args, **options):
        k = options["k"]
        weights = (
            [float(w) for w in options["weights"].split(",") if w.strip()]
            or [settings.RETRIEVAL_LEXICAL_WEIGHT or 1.0]
        )
        embedder = get_embedder()

        started = time.perf_counter()
        try:
            documents = []
            for spec in eval_corpus.DOCUMENTS:
                chunks = build_chunks(eval_corpus.raw_pages(spec), options["chunk_size"])
                documents.append(
                    (index_chunks(spec["key"], chunks, embedder), eval_corpus.questions(spec))
                )
        except EmbeddingError as exc:
            raise CommandError(str(exc))
        if options["pooled"]:
            documents = [pool_documents(documents)]
        chunk_count = sum(len(d.chunks) for d, _ in documents)
        question_count = sum(len(q) for _, q in documents)
        self.stdout.write(
            f"Corpus : {len(documents)} documents, {chunk_count} passages, "
            f"{question_count} questions | modèle {embedder.model_name} | "
            f"indexation {time.perf_counter() - started:.1f} s\n"
        )

        for weight in weights:
            reports = evaluate(documents, embedder, k=k, weight=weight)
            self._print_reports(reports, k, weight, options["details"])

        stats = refusal_stats(documents, embedder, settings.RAG_MIN_SCORE)
        self.stdout.write(
            f"\nRefus par seuil (RAG_MIN_SCORE = {settings.RAG_MIN_SCORE}) :\n"
            f"  questions avec réponse acceptées : {stats['answered_rate']:.0%} "
            f"(cosinus max min/moy : {min(stats['answerable']):.3f} / "
            f"{sum(stats['answerable']) / len(stats['answerable']):.3f})\n"
            f"  questions hors cours refusées     : {stats['refused_rate']:.0%} "
            f"(cosinus max moy/max : "
            f"{sum(stats['unanswerable']) / len(stats['unanswerable']):.3f} / "
            f"{max(stats['unanswerable']):.3f})"
        )

        if options["llm"]:
            self._measure_generation(documents, embedder, options["llm"], weights[0])

    def _print_reports(self, reports, k, weight, details):
        self.stdout.write(f"\n=== Poids lexical = {weight:g} (K = {k}) ===")
        self.stdout.write(
            f"{'mode':<8} {'P@K':>6} {'R@K':>6} {'MRR':>6} {'NDCG@K':>7} {'temps moy.':>11}"
        )
        for mode in MODES:
            report = reports[mode]
            seconds = report.search_seconds
            self.stdout.write(
                f"{mode:<8} {report.mean('precision'):>6.3f} {report.mean('recall'):>6.3f} "
                f"{report.mean('mrr'):>6.3f} {report.mean('ndcg'):>7.3f} "
                f"{1000 * sum(seconds) / max(len(seconds), 1):>8.1f} ms"
            )

        kinds = sorted({row["kind"] for row in reports["hybrid"].per_question})
        self.stdout.write("\nMRR par type de question :")
        self.stdout.write(f"  {'type':<20}" + "".join(f"{m:>8}" for m in MODES) + "   n")
        for kind in kinds:
            count = sum(1 for r in reports["hybrid"].per_question if r["kind"] == kind)
            self.stdout.write(
                f"  {_ascii(kind, 20):<20}"
                + "".join(f"{reports[m].mean('mrr', kind):>8.3f}" for m in MODES)
                + f"   {count}"
            )

        rows = zip(*(reports[m].per_question for m in MODES))
        misses = [r for r in rows if any(x["first_rank"] is None or x["first_rank"] > k for x in r)]
        if details or misses:
            title = "Détail" if details else f"Questions dont le passage attendu est hors du top {k}"
            self.stdout.write(f"\n{title} (rang du 1er passage pertinent : dense / bm25 / hybride) :")
            for row in (zip(*(reports[m].per_question for m in MODES)) if details else misses):
                ranks = " / ".join(str(x["first_rank"] or "-") for x in row)
                self.stdout.write(f"  [{row[0]['document']}] {_ascii(row[0]['question'])} : {ranks}")

    def _measure_generation(self, documents, embedder, count, weight):
        client = get_llm_client()
        questions = [(d, q) for d, qs in documents for q in qs]
        # Mélange déterministe : questions avec et sans réponse
        questions = questions[:: max(len(questions) // count, 1)][:count]
        self.stdout.write(f"\nGénération ({client.name} / {client.model_name}) sur {len(questions)} questions :")
        timings = []
        for document, item in questions:
            ordered, cosine = rank(document, item["question"], "hybrid", embedder, weight)
            by_id = {chunk.id: chunk for chunk in document.chunks}
            hits = [
                SimpleNamespace(chunk=by_id[i], score=cosine[i])
                for i in ordered[: settings.RETRIEVAL_TOP_K]
            ]
            selected = _select_hits(hits)
            if not selected:
                self.stdout.write(f"  refus avant LLM : {_ascii(item['question'])}")
                continue
            context, _ = _build_context(selected)
            prompt = PROMPT_TEMPLATE.format(context=context, history="", question=item["question"])
            started = time.perf_counter()
            try:
                raw = client.generate(prompt, system=SYSTEM_PROMPT, temperature=0.1)
            except LLMError as exc:
                raise CommandError(str(exc))
            elapsed = time.perf_counter() - started
            timings.append(elapsed)
            verdict = "NON_TROUVE" if NOT_FOUND_TOKEN in raw.upper() else "réponse"
            expected = "attendu : réponse" if item["needles"] else "attendu : refus"
            self.stdout.write(
                f"  {elapsed:5.1f} s  {verdict:<10} ({expected})  {_ascii(item['question'])}"
            )
        if timings:
            self.stdout.write(
                f"  temps moyen : {sum(timings) / len(timings):.1f} s | max : {max(timings):.1f} s"
            )
