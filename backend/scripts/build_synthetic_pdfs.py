"""Write the synthetic report PDFs to data/synthetic/pdfs/ so they can be opened and checked by eye.

    python scripts/build_synthetic_pdfs.py

Seeding renders the same PDFs in memory (app/report_pdf.py); this script only saves copies. The
output folder is git-ignored: the PDFs are generated from corpus.json and the report specs, so they
never need committing. Every page is footed "Synthetic demonstration data. Not real BPI data."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SYNTHETIC_DATA_DIR  # noqa: E402
from app.report_pdf import render_study_report  # noqa: E402


def main() -> int:
    out = SYNTHETIC_DATA_DIR / "pdfs"
    out.mkdir(exist_ok=True)
    corpus = json.loads((SYNTHETIC_DATA_DIR / "corpus.json").read_text(encoding="utf-8"))["studies"]
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((SYNTHETIC_DATA_DIR / "report_pdfs").glob("*.json"))]
    for study in corpus + specs:
        report = render_study_report(study)
        (out / report.filename).write_bytes(report.pdf)
        pages = ", ".join(f"p.{p}" for p in report.pages)
        print(f"{report.filename:62} {report.page_count} pages; findings on {pages}")
    print(f"Wrote {len(corpus) + len(specs)} PDFs to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
