"""Brief-writer evaluation: the same questions, the same retrieval, a different writer.

Runs the real `BriefService.ask` as one demo persona for each writer and records what the pipeline
already measures, so writers can be compared without a judge model:

- fell back: the writer failed (error, refusal, timeout) and the brief came from templates;
- regenerated / dropped claims: the validators rejected the first draft / claims that still failed;
- claims and confidence: what the reader gets (confidence is computed in code from the claims);
- seconds per brief, tokens and an estimated cost (Anthropic list prices; Bedrock bills its own).

Wording quality needs people: --blind writes the briefs of two writers side by side as A/B, in a
random order per question, with the key in a separate file.

    python -m eval.brief_eval --writer offline --writer bedrock:global.anthropic.claude-opus-5-5 --limit 2
    python -m eval.brief_eval --writer bedrock:global.anthropic.claude-opus-5-5 \
        --writer bedrock:global.anthropic.claude-sonnet-5-5 --limit 16 --blind out/blind.md --json out/briefs.json

Writers: `offline` (templates), `bedrock:<model id>`, `anthropic:<model id>`. Retrieval is held fixed
on the local fastembed model (the validated demo embedder) whatever EMBEDDING_PROVIDER says, so only
the writer differs. Every Bedrock or Anthropic brief is a billed call (two when it is regenerated):
start with --limit 1 to see the cost per brief.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pgserver
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import CurrentUser  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.embeddings import DEFAULT_FASTEMBED_MODEL, build_embedder  # noqa: E402
from app.llm import ClaudeLLM, OfflineLLM, bedrock_client  # noqa: E402
from app.migrations import apply_migrations  # noqa: E402
from app.seed import seed  # noqa: E402
from app.synthesis import BriefService  # noqa: E402

from eval.retrieval_eval import TODAY  # noqa: E402

QUESTIONS = Path(__file__).with_name("questions.json")
PERSONAS = {"ana": "ana.reyes@example.com", "ben": "ben.santos@example.com", "carla": "carla.mendoza@example.com"}
# USD per million tokens: input, output, cache read, cache write (1.25x input). Anthropic list prices
# for the Claude API; Bedrock publishes its own, so treat the cost column as an estimate.
PRICES = {"opus-5-5": (4.0, 20.0, 0.20, 5.0), "sonnet-5-5": (2.0, 10.0, 0.10, 2.5), "haiku-5-5": (0.10, 0.50, 0.01, 0.125)}


class Recorder:
    """Wraps a client's beta.messages.parse to time each call and keep its token usage."""

    def __init__(self, client):
        self._parse = client.beta.messages.parse
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        start = time.perf_counter()
        try:
            response = self._parse(**kwargs)
        except Exception as exc:
            self.calls.append({"seconds": time.perf_counter() - start, "error": type(exc).__name__})
            raise
        u = response.usage
        content = kwargs["messages"][0]["content"]
        # A regeneration carries the validator problems as a second text block.
        feedback = content[1]["text"] if isinstance(content, list) and len(content) > 1 else None
        parsed = getattr(response, "parsed_output", None)
        self.calls.append({"seconds": time.perf_counter() - start, "stop": response.stop_reason,
                           "input": u.input_tokens, "output": u.output_tokens,
                           "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                           "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
                           "feedback": feedback,
                           # The draft's wording, to see what a rejected draft actually said.
                           "draft": [c.text for c in parsed.claims] + [x.text for x in parsed.summaries]
                           if parsed is not None and hasattr(parsed, "claims") else None})
        return response


def build_writer(spec: str, effort: str, region: str):
    if spec == "offline":
        return OfflineLLM(), None
    platform, _, model = spec.partition(":")
    if platform not in ("bedrock", "anthropic") or not model:
        raise SystemExit(f"Unknown writer {spec!r}; use offline, bedrock:<model id> or anthropic:<model id>.")
    import anthropic

    raw = bedrock_client(region) if platform == "bedrock" else anthropic.Anthropic(timeout=120.0, max_retries=1)
    recorder = Recorder(raw)
    return ClaudeLLM(model, effort, client=recorder, platform=platform), recorder


def cost(model: str, calls: list[dict]) -> float | None:
    price = next((p for key, p in PRICES.items() if key in model), None)
    if price is None:
        return None
    i, o, r, w = price
    return sum(c.get("input", 0) * i + c.get("output", 0) * o + c.get("cache_read", 0) * r
               + c.get("cache_write", 0) * w for c in calls) / 1e6


def pick_questions(limit: int | None, seed_value: int, match: str | None = None) -> list[dict]:
    items = [q for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
             if q["set"] in ("canonical", "paraphrase", "taglish")]
    random.Random(seed_value).shuffle(items)
    if match:
        items = [q for q in items if match.lower() in q["q"].lower()]
    return items[:limit] if limit else items


def load_user(db: Database, email: str) -> CurrentUser:
    with db.as_service() as conn:
        row = conn.execute(
            "select p.id::text as id, p.email, p.display_name, p.role, p.team_id::text as team_id, t.name as team_name "
            "from public.profiles p join public.teams t on t.id = p.team_id where p.email = %s", [email]).fetchone()
    return CurrentUser(**row)


def summarise(rows: list[dict]) -> dict:
    written = [r for r in rows if r["answered"]]
    secs = [r["seconds"] for r in written]
    costs = [r["cost"] for r in written if r["cost"] is not None]
    conf = {lvl: sum(1 for r in written if r["confidence"] == lvl) for lvl in ("high", "medium", "low")}
    return {
        "briefs": len(written),
        "fell_back": sum(1 for r in written if r["fell_back"]),
        "regenerated": sum(1 for r in written if r["regenerated"]),
        "dropped_claims": sum(r["dropped_claims"] for r in written),
        "claims_per_brief": round(statistics.mean(r["claims"] for r in written), 1) if written else 0,
        "confidence": conf,
        "median_s": round(statistics.median(secs), 1) if secs else None,
        "max_s": round(max(secs), 1) if secs else None,
        "cost_per_brief": round(statistics.mean(costs), 4) if costs else None,
        "cost_total": round(sum(costs), 2) if costs else None,
    }


def brief_text(brief: dict) -> str:
    lines = []
    summary = (brief.get("summaries") or {}).get("executive", {}).get("text")
    if summary:
        lines.append(f"*Summary:* {summary}")
    for c in brief["claims"]:
        lines.append(f"- **{c['kind']}**: {c['text']}")
    for n in brief["context_notes"] + brief["unresolved_conflicts"]:
        lines.append(f"- *note*: {n.get('text', '')}")
    lines.append(f"- *confidence*: {brief['confidence']['level']}")
    return "\n".join(lines)


def write_blind(path: Path, writers: list[str], results: dict[str, list[dict]], seed_value: int) -> None:
    a_name, b_name = writers[:2]
    rng = random.Random(seed_value + 1)
    doc, key = ["# Blind read\n", "For each question, which brief answers it better for a BU reader? "
                "Note A or B and why. Numbers and confidence come from code; judge wording.\n"], ["# Key\n"]
    for n, (ra, rb) in enumerate(zip(results[a_name], results[b_name]), 1):
        if not (ra["answered"] and rb["answered"]):
            continue
        pair = [(a_name, ra), (b_name, rb)]
        rng.shuffle(pair)
        doc.append(f"\n## {n}. {ra['question']}\n")
        for label, (_, r) in zip("AB", pair):
            doc.append(f"\n### {label}\n\n{brief_text(r['brief'])}\n")
        key.append(f"- {n}: A = {pair[0][0]}, B = {pair[1][0]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(doc), encoding="utf-8")
    path.with_name(path.stem + "-key.md").write_text("\n".join(key) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--writer", action="append", required=True, help="offline | bedrock:<model> | anthropic:<model>")
    parser.add_argument("--limit", type=int, help="number of questions (a fixed random sample of the answerable ones)")
    parser.add_argument("--persona", choices=sorted(PERSONAS), default="ben")
    parser.add_argument("--effort", default=None, help="effort for Claude writers (default: LLM_EFFORT, else high)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--match", help="only questions containing this text")
    parser.add_argument("--json", type=Path, help="write every brief and metric here")
    parser.add_argument("--blind", type=Path, help="write an A/B blind-read file for the first two writers")
    args = parser.parse_args()

    settings = get_settings()
    effort = args.effort or settings.llm_effort
    writers = [(spec, *build_writer(spec, effort, settings.aws_region)) for spec in args.writer]
    questions = pick_questions(args.limit, args.seed, args.match)
    embedder = build_embedder("fastembed", DEFAULT_FASTEMBED_MODEL)

    server = pgserver.get_server(tempfile.mkdtemp(prefix="si-briefs-"), cleanup_mode="delete")
    results: dict[str, list[dict]] = {}
    try:
        for i, (spec, writer, recorder) in enumerate(writers):
            name = f"briefs_{i}"
            with psycopg.connect(server.get_uri(), autocommit=True) as conn:
                conn.execute(f'drop database if exists "{name}"')
                conn.execute(f'create database "{name}"')
            apply_migrations(server.get_uri(name))
            db = Database(server.get_uri(name), max_size=2)
            try:
                seed(db, TODAY, embedder=embedder, include_reports=False)
                user = load_user(db, PERSONAS[args.persona])
                service = BriefService(db, writer, embedder, fallback_llm=OfflineLLM(), today=lambda: TODAY)
                rows = []
                for n, q in enumerate(questions, 1):
                    if recorder:
                        recorder.calls.clear()
                    start = time.perf_counter()
                    brief = service.ask(user, q["q"])
                    seconds = time.perf_counter() - start
                    calls = list(recorder.calls) if recorder else []
                    answered = brief["generated_by"] is not None
                    rows.append({
                        "question": q["q"], "set": q["set"], "answered": answered,
                        "generated_by": brief["generated_by"], "note": brief["generator_note"],
                        "fell_back": answered and recorder is not None and brief["generated_by"] != writer.name,
                        "regenerated": brief["regenerated"], "dropped_claims": brief["dropped_claims"],
                        "claims": len(brief["claims"]), "confidence": brief["confidence"]["level"],
                        "seconds": seconds, "calls": calls,
                        "cost": cost(writer.name, calls) if recorder else None, "brief": brief,
                    })
                    r = rows[-1]
                    flag = "FELL BACK " if r["fell_back"] else ""
                    spend = f" ${r['cost']:.3f}" if r["cost"] is not None else ""
                    print(f"[{spec}] {n}/{len(questions)} {flag}{r['seconds']:.1f}s{spend} "
                          f"claims {r['claims']} conf {r['confidence']} {q['q'][:60]}", flush=True)
                    if r["fell_back"]:
                        print(f"    {r['note']}", flush=True)
                results[spec] = rows
            finally:
                db.close()
    finally:
        server.cleanup()

    summaries = {spec: summarise(rows) for spec, rows in results.items()}
    print(f"\n{len(questions)} questions as {args.persona}; retrieval: fastembed; effort {effort}\n")
    print("| Writer | Briefs | Fell back | Regenerated | Dropped claims | Claims/brief | High/Med/Low | Median s | Max s | $/brief (est.) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for spec, s in summaries.items():
        c = s["confidence"]
        money = f"{s['cost_per_brief']:.3f}" if s["cost_per_brief"] is not None else "-"
        print(f"| {spec} | {s['briefs']} | {s['fell_back']} | {s['regenerated']} | {s['dropped_claims']} | "
              f"{s['claims_per_brief']} | {c['high']}/{c['medium']}/{c['low']} | {s['median_s']} | {s['max_s']} | {money} |")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"summary": summaries, "results": results}, indent=2, default=str), encoding="utf-8")
    if args.blind and len(results) >= 2:
        write_blind(args.blind, list(results), results, args.seed)
        print(f"\nBlind read: {args.blind} (key in {args.blind.stem}-key.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
