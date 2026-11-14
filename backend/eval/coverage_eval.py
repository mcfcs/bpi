"""Coverage-check evaluation: does "Before you commission" call new problems new?

Runs the real `commissioning.assess_objectives` for each case in eval/coverage_cases.json as the
named persona (so RLS and restricted-study hints behave as in the app) and checks the coverage state,
that the expected studies are among the cited findings, and whether a restricted-study hint appears.

    python -m eval.coverage_eval                          # hashing + default fastembed model
    python -m eval.coverage_eval --provider fastembed -v
    python -m eval.coverage_eval --provider bedrock      # Cohere on Bedrock (billed, fractions of a cent)
    python -m eval.coverage_eval --public-pdfs ../data/public/pdfs   # include public studies (PUB-*)

Public studies are seeded only when their PDFs are present (they are git-ignored); without them the
cases that need them are reported as skipped. The cases are few and were written alongside the fix:
treat this as a regression check, not a calibration set.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pgserver

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import commissioning, public_sources  # noqa: E402
from app.embeddings import DEFAULT_FASTEMBED_MODEL, build_embedder  # noqa: E402
from app.migrations import apply_migrations  # noqa: E402
from app.db import Database  # noqa: E402
from app.seed import persona_id, seed  # noqa: E402

from eval.retrieval_eval import TODAY  # noqa: E402

CASES = Path(__file__).with_name("coverage_cases.json")
PERSONAS = {"ana": "ana.reyes@example.com", "ben": "ben.santos@example.com", "carla": "carla.mendoza@example.com"}


def fresh_database(server, name: str, embedder, include_public: bool) -> tuple[Database, set[str]]:
    import psycopg

    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        conn.execute(f'drop database if exists "{name}"')
        conn.execute(f'create database "{name}"')
    uri = server.get_uri(name)
    apply_migrations(uri)
    db = Database(uri, max_size=2)
    result = seed(db, TODAY, embedder=embedder, include_reports=False, include_public=include_public)
    return db, set(result["studies"]) | set(result["public"])


def check(db: Database, embedder, case: dict, seeded: set[str]) -> dict:
    email = PERSONAS[case["who"]]
    with db.as_user(persona_id(email), email) as conn:
        (assessed,) = commissioning.assess_objectives(conn, [case["objective"]], embedder, TODAY)
        codes = {r["study_code"] for r in conn.execute(
            "select s.code as study_code from public.findings f join public.studies s on s.id = f.study_id "
            "where f.id = any(%s::uuid[])", [assessed["finding_ids"]]).fetchall()} if assessed["finding_ids"] else set()
    restricted = [s["code"] for c in assessed["caveats"] if c["code"] == "restricted_match" for s in c["studies"]]
    expect = case["expect"]
    problems = []
    if assessed["coverage"] not in expect["coverage"]:
        problems.append(f"coverage {assessed['coverage']} (want {'/'.join(expect['coverage'])})")
    missing = [c for c in expect.get("studies", []) if c not in codes]
    if missing:
        problems.append(f"missing {missing}")
    if "restricted" in expect and sorted(restricted) != sorted(expect["restricted"]):
        problems.append(f"restricted hint {restricted or '-'} (want {expect['restricted'] or '-'})")
    needs = set(case.get("needs", []))
    return {"case": case, "coverage": assessed["coverage"], "codes": sorted(codes), "restricted": restricted,
            "problems": problems, "skipped": bool(needs - seeded)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["hashing", "fastembed", "bedrock", "all"], default="all",
                        help="all = hashing + fastembed (bedrock is billed, so only when named)")
    parser.add_argument("--public-pdfs", type=Path, help="directory holding the downloaded public report PDFs")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.public_pdfs:
        public_sources.PDF_DIR = args.public_pdfs.resolve()
    include_public = any(r.card and r.available for r in public_sources.load_reports())
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    specs = ([("hashing", None)] if args.provider in ("hashing", "all") else []) + \
            ([("fastembed", DEFAULT_FASTEMBED_MODEL)] if args.provider in ("fastembed", "all") else [])
    if args.provider == "bedrock":
        from app.config import get_settings

        get_settings()  # loads backend/.env.local: AWS_PROFILE and AWS_REGION for the Bedrock client
        specs.append(("bedrock", None))
    server = pgserver.get_server(tempfile.mkdtemp(prefix="si-coverage-"), cleanup_mode="delete")
    failures = 0
    try:
        for i, (provider, model) in enumerate(specs):
            embedder = build_embedder(provider, model)
            db, seeded = fresh_database(server, f"coverage_{i}", embedder, include_public)
            try:
                results = [check(db, embedder, case, seeded) for case in cases]
            finally:
                db.close()
            ran = [r for r in results if not r["skipped"]]
            ok = [r for r in ran if not r["problems"]]
            failures += len(ran) - len(ok)
            print(f"\n## {embedder.name}: {len(ok)}/{len(ran)} cases pass"
                  f"{f', {len(results) - len(ran)} skipped (public PDFs missing)' if len(ran) < len(results) else ''}")
            for kind in ("negative", "positive"):
                group = [r for r in ran if r["case"]["kind"] == kind]
                print(f"   {kind}: {sum(not r['problems'] for r in group)}/{len(group)}")
            for r in results:
                if r["skipped"]:
                    continue
                if r["problems"] or args.verbose:
                    c = r["case"]
                    print(f"- [{c['kind']}] {c['who']}: {c['objective']}\n    {r['coverage']}; studies {r['codes'] or '-'}; "
                          f"restricted {r['restricted'] or '-'}" + (f"; FAIL: {'; '.join(r['problems'])}" if r["problems"] else ""))
    finally:
        server.cleanup()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
