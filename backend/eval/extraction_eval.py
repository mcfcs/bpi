"""Extraction evaluation: how well do the study-card extractors read real report PDFs?

Gold set: the hand-labelled cards in data/public/cards/ (method, sample, fieldwork end, regions,
key findings with page numbers). For every public report whose PDF has been downloaded
(scripts/fetch_public_reports.py), the PDF goes through the same path as an upload
(documents.extract_pdf -> normalise_report_text -> extractor -> map_finding_pages) and is scored:

    method      extracted method_type equals the card's
    sample      sample size within 10% of the card's
    fieldwork   fieldwork end within 31 days of the card's
    regions     same regions after expanding to administrative regions (Jaccard >= 0.5)
    recall      share of the card's findings matched by an extracted finding (same value for
                quant stats, otherwise >= 50% shared word trigrams)
    page        share of matched findings pinned to the card's page
    locator     share of the card's quotes the page locator puts on the card's page (independent
                of extraction: it checks citations can be resolved in the real layout)

The synthetic report PDFs are scored the same way as a baseline (their gold is the spec itself).

    python -m eval.extraction_eval                 offline extractor
    python -m eval.extraction_eval --claude        also the Claude extractor, if credentials are set
    python -m eval.extraction_eval --json

Results are on six public reports; treat them as a smoke test of robustness, not a benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import geography, public_sources  # noqa: E402
from app.config import SYNTHETIC_DATA_DIR  # noqa: E402
from app.documents import _tokens, extract_pdf, locate_page, map_finding_pages, normalise_report_text  # noqa: E402
from app.llm import OfflineLLM  # noqa: E402
from app.llm_types import LLM  # noqa: E402
from app.report_pdf import render_study_report  # noqa: E402
from app.schemas import StudyCardExtraction  # noqa: E402

FIELDS = ("method", "sample", "fieldwork", "regions")


@dataclass
class Score:
    report: str
    kind: str                     # "public" or "synthetic"
    extractor: str
    fields: dict[str, bool] = field(default_factory=dict)
    recall: float = 0.0
    page: float | None = None
    locator: float | None = None
    found: int = 0
    gold: int = 0
    note: str = ""


def _trigrams(text: str) -> set[tuple[str, ...]]:
    t = _tokens(text)
    return {tuple(t[i:i + 3]) for i in range(len(t) - 2)}


def _matches(gold: dict, extracted) -> bool:
    if gold["finding_type"] == "quant_stat" and gold.get("value") is not None:
        return extracted.value is not None and abs(float(extracted.value) - float(gold["value"])) < 0.05
    g = _trigrams(gold["text"])
    return bool(g) and len(g & _trigrams(extracted.text)) / len(g) >= 0.5


def _regions_match(gold: list[str], got: list[str]) -> bool:
    a, b = geography.expand(gold), geography.expand(got)
    if not a and not b:
        return True
    return bool(a | b) and len(a & b) / len(a | b) >= 0.5


def score_card(gold: dict, card: StudyCardExtraction, pages: list[str], report: str, kind: str,
               extractor: str) -> Score:
    s = Score(report=report, kind=kind, extractor=extractor, gold=len(gold["findings"]), found=len(card.findings))
    s.fields["method"] = card.method_type == gold["method_type"]
    gn = gold.get("sample_size")
    s.fields["sample"] = bool(gn and card.sample_size and abs(card.sample_size - gn) <= 0.1 * gn)
    try:
        s.fields["fieldwork"] = bool(card.fieldwork_end) and abs(
            (date.fromisoformat(card.fieldwork_end) - date.fromisoformat(gold["fieldwork_end"])).days) <= 31
    except ValueError:
        s.fields["fieldwork"] = False
    s.fields["regions"] = _regions_match(gold["population"].get("regions") or [], card.population.regions)

    found_pages, _ = map_finding_pages(card, pages)
    matched, on_page = 0, 0
    for g in gold["findings"]:
        hit = next((i for i, f in enumerate(card.findings) if _matches(g, f)), None)
        if hit is not None:
            matched += 1
            on_page += int(g.get("page") is not None and found_pages.get(hit) == g["page"])
    s.recall = matched / len(gold["findings"]) if gold["findings"] else 0.0
    s.page = on_page / matched if matched else None
    quotes = [g for g in gold["findings"] if g.get("quote") and g.get("page")]
    if quotes:
        s.locator = sum(locate_page(g["quote"], pages)[0] == g["page"] for g in quotes) / len(quotes)
    return s


def run(extractors: list[LLM]) -> list[Score]:
    scores: list[Score] = []
    for report in public_sources.load_reports():
        if not report.card:
            continue
        if not report.available:
            scores.append(Score(report=report.slug, kind="public", extractor="-", note="PDF not downloaded"))
            continue
        extracted = extract_pdf(report.pdf_path.read_bytes())
        text = normalise_report_text(extracted)
        for llm in extractors:
            card = llm.extract_study_card(text, [])
            scores.append(score_card(report.card, card, extracted.pages, report.slug, "public", llm.name))

    corpus = json.loads((SYNTHETIC_DATA_DIR / "corpus.json").read_text(encoding="utf-8"))["studies"]
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((SYNTHETIC_DATA_DIR / "report_pdfs").glob("*.json"))]
    for study in corpus + specs:
        rendered = render_study_report(study)
        extracted = extract_pdf(rendered.pdf)
        gold = {**study, "findings": [{**f, "page": p, "quote": f["text"]} for f, p in zip(study["findings"], rendered.pages)]}
        text = normalise_report_text(extracted)
        for llm in extractors:
            card = llm.extract_study_card(text, [])
            scores.append(score_card(gold, card, extracted.pages, study.get("code") or study["title"], "synthetic", llm.name))
    return scores


def _pct(x: float | None) -> str:
    return "  -  " if x is None else f"{100 * x:4.0f}%"


def summarise(scores: list[Score]) -> dict:
    out: dict = {}
    for kind in ("public", "synthetic"):
        for extractor in sorted({s.extractor for s in scores if s.kind == kind and s.extractor != "-"}):
            rows = [s for s in scores if s.kind == kind and s.extractor == extractor]
            pages = [s.page for s in rows if s.page is not None]
            loc = [s.locator for s in rows if s.locator is not None]
            out[f"{kind}/{extractor}"] = {
                "reports": len(rows),
                **{f: sum(s.fields[f] for s in rows) / len(rows) for f in FIELDS},
                "recall": sum(s.recall for s in rows) / len(rows),
                "page": sum(pages) / len(pages) if pages else None,
                "locator": sum(loc) / len(loc) if loc else None,
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claude", action="store_true", help="also run the Claude extractor (needs credentials)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    extractors: list[LLM] = [OfflineLLM()]
    if args.claude:
        from app.config import get_settings
        from app.llm import build_llm
        settings = get_settings()
        if settings.llm_provider == "anthropic":
            extractors.append(build_llm(settings))
        else:
            print("No Claude credentials configured; running the offline extractor only.\n")
    scores = run(extractors)
    summary = summarise(scores)
    if args.json:
        print(json.dumps({"scores": [asdict(s) for s in scores], "summary": summary}, indent=2))
        return 0
    print(f"{'report':46} {'extractor':18} method sample fieldw region recall  page locator  found/gold")
    for s in scores:
        if s.note:
            print(f"{s.report[:46]:46} {s.note}")
            continue
        f = s.fields
        print(f"{s.report[:46]:46} {s.extractor[:18]:18} " + " ".join(f"{'  yes ' if f[k] else '  no  '}" for k in FIELDS)
              + f" {_pct(s.recall)} {_pct(s.page)} {_pct(s.locator)}   {s.found}/{s.gold}")
    print("\nSummary (share of reports with the field right; recall/page/locator averaged per report):")
    for key, row in summary.items():
        print(f"  {key:30} n={row['reports']:2}  " + "  ".join(f"{k} {_pct(row[k])}" for k in (*FIELDS, "recall", "page", "locator")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
