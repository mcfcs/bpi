"""How the robustness tiers weigh every kind of evidence in the repository.

Runs app/tiers.py (unchanged) over the synthetic corpus, the synthetic report PDFs that wait in the
review queue, and the hand-labelled public research studies, and prints one row per study with the
points behind its tier. No database or network is needed.

    python -m eval.evidence_weighing                  as of today
    python -m eval.evidence_weighing --as-of 2026-10-27
    python -m eval.evidence_weighing --json

The flags column marks outcomes S&I may want to revisit (see README, "Weighing evidence"):
    qual-capped     qualitative work can never rise above C, however recent
    mixed-penalty   survey numbers in a mixed-method report get mixed, not quant, method points
    n-flat          sample points stop at n >= 1,000 and ignore design (probability vs convenience)
    date-unstated   fieldwork end inferred from the report date
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import public_sources  # noqa: E402
from app.config import SYNTHETIC_DATA_DIR, TIER_CONFIG  # noqa: E402
from app.tiers import tier_breakdown  # noqa: E402


def _studies() -> list[tuple[str, dict]]:
    corpus = json.loads((SYNTHETIC_DATA_DIR / "corpus.json").read_text(encoding="utf-8"))
    rows = [("synthetic (approved)", s) for s in corpus["studies"]]
    for path in sorted((SYNTHETIC_DATA_DIR / "report_pdfs").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        rows.append(("synthetic PDF (review queue)", {**spec, "code": spec.get("code") or spec["title"]}))
    for report in public_sources.load_reports():
        if report.card:
            rows.append((f"public: {report.entry['publisher']}", {**report.card, "_entry": report.entry}))
    return rows


def evidence_table(today: date) -> list[dict]:
    out = []
    top_band = TIER_CONFIG["sample_bands"][0][0]
    for source, s in _studies():
        breakdown = tier_breakdown(s["method_type"], s.get("sample_size"), date.fromisoformat(s["fieldwork_end"]), today)
        flags = []
        if s["method_type"] == "qual":
            flags.append("qual-capped")
        if s["method_type"] == "mixed" and any(f["finding_type"] == "quant_stat" for f in s["findings"]):
            flags.append("mixed-penalty")
        if s["method_type"] != "qual" and (s.get("sample_size") or 0) >= 3 * top_band:
            flags.append("n-flat")
        if "not stated" in (s.get("_entry", {}).get("fieldwork", "").lower()):
            flags.append("date-unstated")
        out.append({
            "code": s["code"], "title": s["title"], "source": source, "method_type": s["method_type"],
            "sample_size": s.get("sample_size"), "fieldwork_end": s["fieldwork_end"],
            "tier": breakdown["tier"], "score": breakdown["score"], "breakdown": breakdown, "flags": flags,
        })
    out.sort(key=lambda r: (r["tier"], -r["score"], r["code"]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = evidence_table(args.as_of)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    print(f"Robustness tiers as of {args.as_of} (method + sample + recency; A >= {TIER_CONFIG['tiers']['A']}, "
          f"B >= {TIER_CONFIG['tiers']['B']})\n")
    print(f"{'tier':4} {'score':>5}  {'m':>2} {'n':>2} {'r':>2}  {'method':6} {'sample':>6} {'fieldwork':10}  "
          f"{'code':48} source / flags")
    for r in rows:
        b = r["breakdown"]
        print(f"{r['tier']:4} {r['score']:>5}  {b['method_points']:>2} {b['sample_points']:>2} {b['recency_points']:>2}  "
              f"{r['method_type']:6} {r['sample_size'] or '-':>6} {r['fieldwork_end']:10}  {r['code'][:48]:48} "
              f"{r['source']}{'  [' + ', '.join(r['flags']) + ']' if r['flags'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
