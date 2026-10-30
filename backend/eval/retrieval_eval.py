"""Retrieval evaluation: does search find the right studies when users word things their own way?

For each embedder, seeds a throwaway embedded Postgres with the synthetic corpus, runs the real
`retrieval.search` for every question in eval/questions.json as the S&I analyst (who can read every
approved study, so permissions don't confound the score), and scores at the study level:

    recall      share of expected studies retrieved (positives)
    hit@1       the top-ranked study is an expected one
    MRR         1 / rank of the first expected study
    precision   share of retrieved studies that were expected (positives)
    neg FP      share of off-topic questions that retrieved anything
    near-neg FP the same for questions that name a covered product but ask what no study measures
    micro F1    over all questions, where anything retrieved for an off-topic question is a false positive

    python -m eval.retrieval_eval                                   # configured floors, hashing + default fastembed model
    python -m eval.retrieval_eval --provider hashing
    python -m eval.retrieval_eval --model BAAI/bge-small-en-v1.5 --model sentence-transformers/all-MiniLM-L6-v2
    python -m eval.retrieval_eval --sweep                            # grid-search floors per embedder
    python -m eval.retrieval_eval --show-misses
    python -m eval.retrieval_eval --no-facets                        # also report without the facet rerank
    python -m eval.retrieval_eval --split tune --sweep               # tune on one half, then report the other

Each question is in the 'tune' or 'holdout' half; full runs also print a table per half. Choose
floors and weights on 'tune' only. Both halves are small (~20 questions), so sweep results are a
starting point: recalibrate on real studies with held-out questions.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pgserver
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import retrieval  # noqa: E402
from app.config import RETRIEVAL_CONFIG, retrieval_config  # noqa: E402
from app.db import Database  # noqa: E402
from app.embeddings import DEFAULT_FASTEMBED_MODEL, Embedder, build_embedder  # noqa: E402
from app.migrations import apply_migrations  # noqa: E402
from app.seed import persona_id, seed  # noqa: E402

QUESTIONS = Path(__file__).with_name("questions.json")
ANALYST = "ana.reyes@example.com"
TODAY = date(2026, 10, 27)


@dataclass
class Outcome:
    q: str
    set: str
    expected: list[str]
    found: list[str]                 # study codes in rank order (first appearance)
    top_similarity: float = 0.0
    split: str = ""                  # "tune" or "holdout" (questions.json)

    @property
    def tp(self) -> int:
        return len(set(self.found) & set(self.expected))

    @property
    def recall(self) -> float:
        return self.tp / len(self.expected) if self.expected else 0.0

    @property
    def precision(self) -> float:
        return self.tp / len(self.found) if self.found else 0.0

    @property
    def rr(self) -> float:
        return next((1 / i for i, code in enumerate(self.found, 1) if code in self.expected), 0.0)


@dataclass
class Scores:
    by_set: dict[str, dict[str, float]] = field(default_factory=dict)
    overall: dict[str, float] = field(default_factory=dict)


SETS = ["canonical", "paraphrase", "taglish", "negative", "near_negative"]


def score(outcomes: list[Outcome]) -> Scores:
    s = Scores()
    for name in sorted({o.set for o in outcomes}, key=SETS.index):
        group = [o for o in outcomes if o.set == name]
        if name in ("negative", "near_negative"):
            s.by_set[name] = {"n": len(group), "neg_fp": sum(bool(o.found) for o in group) / len(group)}
        else:
            s.by_set[name] = {
                "n": len(group),
                "recall": sum(o.recall for o in group) / len(group),
                "hit@1": sum(bool(o.found) and o.found[0] in o.expected for o in group) / len(group),
                "mrr": sum(o.rr for o in group) / len(group),
                "precision": sum(o.precision for o in group) / len(group),
            }
    tp = sum(o.tp for o in outcomes)
    fp = sum(len(o.found) - o.tp for o in outcomes)
    fn = sum(len(o.expected) - o.tp for o in outcomes)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    positives = [o for o in outcomes if o.expected]
    # "Neg FP" stays the off-topic set only, comparable with earlier runs; near-negatives are separate.
    negatives = [o for o in outcomes if o.set == "negative"]
    s.overall = {
        "micro_f1": 2 * p * r / (p + r) if p + r else 0.0,
        "recall": sum(o.recall for o in positives) / len(positives),
        "mrr": sum(o.rr for o in positives) / len(positives),
        "neg_fp": sum(bool(o.found) for o in negatives) / len(negatives) if negatives else 0.0,
    }
    return s


def run(conn: psycopg.Connection, embedder: Embedder, questions: list[dict], config: dict) -> list[Outcome]:
    outcomes = []
    for item in questions:
        sources = retrieval.search(conn, item["q"], embedder, config=config)
        codes = list(dict.fromkeys(s.study_code for s in sources))
        outcomes.append(Outcome(item["q"], item["set"], item["expected"], codes,
                                max((s.similarity for s in sources), default=0.0), item.get("split", "")))
    return outcomes


def sweep(conn: psycopg.Connection, embedder: Embedder, questions: list[dict]) -> list[tuple[dict, Scores]]:
    """Grid-search the absolute and relative floors; best micro F1 first (ties: fewer negative hits)."""
    results = []
    floors = [round(x * 0.02, 2) for x in range(0, 46)]          # 0.00 .. 0.90
    relatives = [0.0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9]
    for floor, rel in itertools.product(floors, relatives):
        cfg = {"min_similarity": floor, "relative_floor": rel}
        results.append((cfg, score(run(conn, embedder, questions, cfg))))
    results.sort(key=lambda r: (-r[1].overall["micro_f1"], r[1].overall["neg_fp"], -r[1].overall["recall"]))
    return results


def fresh_database(server, name: str, embedder: Embedder) -> Database:
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        conn.execute(f'drop database if exists "{name}"')
        conn.execute(f'create database "{name}"')
    uri = server.get_uri(name)
    apply_migrations(uri)
    db = Database(uri, max_size=2)
    seed(db, TODAY, embedder=embedder, include_reports=False)
    return db


def table(rows: list[tuple[str, Scores]]) -> str:
    head = ("| Embedder | Para recall | Para hit@1 | Para precision | Taglish recall | Canonical recall | MRR (all) "
            "| Neg FP | Near-neg FP | Micro F1 |\n|---|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for name, s in rows:
        b = s.by_set
        para = b.get("paraphrase", {})
        lines.append(
            f"| {name} | {para.get('recall', 0):.2f} | {para.get('hit@1', 0):.2f} | {para.get('precision', 0):.2f} "
            f"| {b.get('taglish', {}).get('recall', 0):.2f} | {b.get('canonical', {}).get('recall', 0):.2f} "
            f"| {s.overall['mrr']:.2f} | {s.overall['neg_fp']:.2f} | {b.get('near_negative', {}).get('neg_fp', 0):.2f} "
            f"| {s.overall['micro_f1']:.2f} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["hashing", "fastembed", "all"], default="all")
    parser.add_argument("--model", action="append", help="fastembed model (repeatable)")
    parser.add_argument("--sweep", action="store_true", help="grid-search similarity floors per embedder")
    parser.add_argument("--show-misses", action="store_true")
    parser.add_argument("--split", choices=["tune", "holdout", "all"], default="all",
                        help="evaluate (and sweep) only this half of questions.json")
    parser.add_argument("--no-facets", action="store_true",
                        help="also report each embedder without the product/topic facet rerank")
    parser.add_argument("--json", type=Path, help="write raw results here")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    if args.split != "all":
        questions = [q for q in questions if q.get("split") == args.split]
    variants = [("configured", {})] + ([("no facets", {"facet_boost": {}})] if args.no_facets else [])
    by_half: dict[str, list[tuple[str, Scores]]] = {"tune": [], "holdout": []}
    specs: list[tuple[str, str | None]] = []
    if args.provider in ("hashing", "all"):
        specs.append(("hashing", None))
    if args.provider in ("fastembed", "all"):
        specs += [("fastembed", m) for m in (args.model or [DEFAULT_FASTEMBED_MODEL])]

    server = pgserver.get_server(tempfile.mkdtemp(prefix="si-eval-"), cleanup_mode="delete")
    rows, raw = [], {}
    try:
        for i, (provider, model) in enumerate(specs):
            started = time.perf_counter()
            embedder = build_embedder(provider, model)
            db = fresh_database(server, f"eval_{i}", embedder)
            try:
                with db.as_user(persona_id(ANALYST), ANALYST) as conn:
                    for label, override in variants:
                        outcomes = run(conn, embedder, questions, override)
                        rows.append((f"{embedder.name} ({label})", score(outcomes)))
                        for half, group in by_half.items():
                            subset = [o for o in outcomes if o.split == half]
                            if subset and args.split == "all":
                                group.append((f"{embedder.name} ({label})", score(subset)))
                        if label != "configured":
                            continue
                        raw[embedder.name] = {"configured": [o.__dict__ for o in outcomes],
                                              "config": {k: retrieval_config(embedder.name)[k]
                                                         for k in ("min_similarity", "relative_floor", "facet_boost")}}
                        if args.show_misses:
                            print(f"\n## Misses: {embedder.name}")
                            for o in outcomes:
                                missing = [c for c in o.expected if c not in o.found]
                                extra = [c for c in o.found if c not in o.expected]
                                if missing or extra:
                                    print(f"- [{o.set}/{o.split}] {o.q}\n    missing {missing or '-'}; "
                                          f"unexpected {extra or '-'}; top sim {o.top_similarity:.2f}")
                    if args.sweep:
                        best = sweep(conn, embedder, questions)
                        cfg, s = best[0]
                        rows.append((f"{embedder.name} (best: floor {cfg['min_similarity']}, rel {cfg['relative_floor']})", s))
                        raw[embedder.name]["sweep_top5"] = [{**c, **sc.overall} for c, sc in best[:5]]
            finally:
                db.close()
            print(f"{embedder.name}: {time.perf_counter() - started:.1f}s", file=sys.stderr)
    finally:
        server.cleanup()

    print(f"\nRetrieval evaluation on {len(questions)} questions ({args.split}; "
          f"defaults: floor {RETRIEVAL_CONFIG['min_similarity']}, rel {RETRIEVAL_CONFIG['relative_floor']})\n")
    print(table(rows))
    for half, group in by_half.items():
        if group:
            print(f"\n{half.capitalize()} half only:\n")
            print(table(group))
    if args.json:
        args.json.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
