"""Public research reports: a manifest of freely downloadable third-party PDFs, and hand-labelled
study cards for them.

data/public/manifest.json lists each report (publisher, year, official URL, licence, method, sample,
fieldwork, sha256). The PDFs themselves are downloaded by backend/scripts/fetch_public_reports.py
into data/public/pdfs/ and are git-ignored: third-party PDFs are never committed.

data/public/cards/<slug>.json holds a study card per report, labelled by reading the PDF: method,
sample, fieldwork end, population, and key findings each with the page it is on and a short
faithful quote. The cards serve two purposes:

* seeded as approved, open studies labelled "Public source" (provenance = 'public') when the PDF is
  present locally, so the demo shows how the tiers weigh official statistics against BPI-style
  surveys and focus groups;
* a gold set for eval/extraction_eval.py, which scores the extractors against them.

Public studies are not BPI research and are always shown with their publisher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import PUBLIC_DATA_DIR
from .schemas import ExtractedFinding, ExtractedPopulation, ExtractedSubgroup, StudyCardExtraction

MANIFEST = PUBLIC_DATA_DIR / "manifest.json"
CARDS_DIR = PUBLIC_DATA_DIR / "cards"
PDF_DIR = PUBLIC_DATA_DIR / "pdfs"


@dataclass
class PublicReport:
    slug: str
    entry: dict            # the manifest entry
    card: dict | None      # the hand-labelled card, if written

    @property
    def pdf_path(self) -> Path:
        return PDF_DIR / f"{self.slug}.pdf"

    @property
    def available(self) -> bool:
        return self.pdf_path.exists() and self.pdf_path.stat().st_size > 0


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["reports"]


def load_reports(manifest: Path = MANIFEST, cards_dir: Path = CARDS_DIR) -> list[PublicReport]:
    reports = []
    for entry in load_manifest(manifest):
        card_path = cards_dir / f"{entry['slug']}.json"
        card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.exists() else None
        reports.append(PublicReport(slug=entry["slug"], entry=entry, card=card))
    return reports


def card_to_extraction(card: dict) -> StudyCardExtraction:
    findings = []
    for f in card["findings"]:
        sub = f.get("subgroup")
        findings.append(ExtractedFinding(
            text=f["text"],
            finding_type=f["finding_type"],
            theme=f.get("theme", card.get("theme")),
            metric_key=f.get("metric_key"),
            value=f.get("value") if f["finding_type"] == "quant_stat" else None,
            unit=f.get("unit"),
            base_n=f.get("base_n"),
            subgroup=ExtractedSubgroup(**{"age_band": None, "region": None, "segment": None, **sub}) if sub else None,
            direction=f.get("direction"),
        ))
    return StudyCardExtraction(
        title=card["title"],
        summary=card["summary"],
        method_type=card["method_type"],
        sample_size=card.get("sample_size"),
        fieldwork_end=card.get("fieldwork_end"),
        population=ExtractedPopulation(**{"age_min": None, "age_max": None, "regions": [], "segment": None,
                                          **card.get("population", {})}),
        findings=findings,
    )


def card_pages(card: dict) -> tuple[list[int | None], list[str | None]]:
    return [f.get("page") for f in card["findings"]], [f.get("quote") for f in card["findings"]]
