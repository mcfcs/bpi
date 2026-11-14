"""Render a synthetic research report PDF from a study record, and record where each finding lands.

The demo corpus (data/synthetic/corpus.json) holds study cards, not reports. To show citations that
open the source report at the right page, each study gets a realistic multi-page report generated
from its own fields: a cover, method and sample, key findings spread over pages (with a chart for
percentage results), verbatims for qualitative work, and an "About this report" page. Every page
carries a "Synthetic demonstration data" footer.

The layout is deliberately the one `documents.normalise_report_text` and `offline_extract` read
(labelled details block, "Key findings" bullets, quoted verbatims), so generated reports also go
through PDF ingestion without Claude. Output is deterministic for a given study record.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from fpdf import FPDF

from .config import metric_label

SYNTHETIC_NOTICE = "Synthetic demonstration data. Not real BPI data."
SECTION_HEADINGS = ("Study details", "Summary", "Method and sample", "Key findings", "In their words",
                    "About this report")

# Core PDF fonts are Latin-1 only; the corpus is ASCII today, but later additions may not be.
_ASCII = str.maketrans({"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"',
                        "”": '"', "…": "...", "•": "-", " ": " ", "·": "|"})

RED = (154, 25, 30)
SLATE = (63, 87, 128)
INK = (34, 34, 34)
MUTED = (110, 110, 110)
RULE = (210, 210, 210)

METHOD_LINES = {
    "quant": "Quantitative survey (online and telephone questionnaire)",
    "qual": "Qualitative focus groups (FGDs)",
    "mixed": "Mixed method: quantitative survey and qualitative in-depth interviews",
}


def clean(text: str | None) -> str:
    text = (text or "").translate(_ASCII)
    return text.encode("latin-1", "replace").decode("latin-1")


def _long_date(d: date) -> str:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


def _fieldwork_window(study: dict) -> tuple[date, date]:
    end = date.fromisoformat(study["fieldwork_end"])
    start = date.fromisoformat(study["fieldwork_start"]) if study.get("fieldwork_start") else end - timedelta(days=27)
    return start, end


def _coverage(study: dict) -> str:
    pop = study.get("population") or {}
    regions = pop.get("regions") or []
    place = "Nationwide" if any(r.lower() == "nationwide" for r in regions) else " and ".join(
        [", ".join(regions[:-1]), regions[-1]] if len(regions) > 1 else regions) or "Not stated"
    if pop.get("age_min") is not None and pop.get("age_max") is not None:
        return f"{place}; respondents aged {pop['age_min']}-{pop['age_max']}"
    return place


def _sample_line(study: dict) -> str:
    n = study.get("sample_size")
    segment = (study.get("population") or {}).get("segment") or "respondents"
    if not n:
        return "Not stated"
    if study["method_type"] == "qual":
        groups = study.get("groups") or max(1, round(n / 7))
        return f"{groups} focus groups, {n} participants"
    if study["method_type"] == "mixed":
        idi = study.get("interviews") or 20
        return f"n={n:,} survey respondents ({segment}) plus {idi} in-depth interview participants"
    return f"n={n:,} {segment}"


def details_block(study: dict) -> list[tuple[str, str]]:
    """The labelled lines extraction reads; one line each so PDF text extraction keeps them whole."""
    start, end = _fieldwork_window(study)
    return [
        ("Method", study.get("method_line") or METHOD_LINES.get(study["method_type"], "Not stated")),
        ("Sample", _sample_line(study)),
        ("Fieldwork", f"{_long_date(start)} to {_long_date(end)}"),
        ("Coverage", _coverage(study)),
        ("Segment", (study.get("population") or {}).get("segment") or "Not stated"),
    ]


def _attribution(finding: dict) -> str:
    sub = finding.get("subgroup") or {}
    return ", ".join(p for p in (sub.get("segment"), sub.get("region")) if p) or "Participant"


def _method_paragraphs(study: dict) -> list[str]:
    n = study.get("sample_size")
    start, end = _fieldwork_window(study)
    window = f"between {_long_date(start)} and {_long_date(end)}"
    segment = (study.get("population") or {}).get("segment") or "respondents"
    if not segment.split()[0].isupper():   # keep acronyms such as "SME owners"
        segment = segment[:1].lower() + segment[1:]
    if study["method_type"] == "qual":
        # Studies outside small business set their own recruitment sentence; the default suits SMEs.
        recruited = study.get("recruitment") or (
            f"Groups were recruited through local business associations and screened for {segment} who "
            "had been in operation for at least two years.")
        return [
            f"Fieldwork took place {window}. {recruited}",
            "Each discussion ran for about two hours, was moderated in the participants' preferred "
            "language and was recorded with consent. Quotations are translated where needed.",
            "Qualitative findings describe the range of views expressed. They do not measure how "
            "common a view is and should not be read as percentages.",
        ]
    paragraphs = [
        f"Interviews were completed {window}. Quotas were set on age band and region and the results "
        f"are weighted to the profile of {segment} in the areas covered.",
        f"The total sample is n={n:,}. Bases for subgroup figures are shown next to each result. "
        "Differences of fewer than five points between subgroups are within the margin of error.",
    ]
    if study["method_type"] == "mixed":
        paragraphs.append("Survey results were followed by in-depth interviews with a subset of respondents "
                          "to explain the patterns in the numbers. Interview themes are reported separately "
                          "from survey percentages.")
    return paragraphs


def _filename(study: dict) -> str:
    stem = study.get("code") or study["title"]
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") + "-report.pdf"


@dataclass
class RenderedReport:
    pdf: bytes
    pages: list[int]          # page of each finding, in the order of study["findings"]
    page_count: int
    filename: str


class _ReportPDF(FPDF):
    def __init__(self, code: str, notice: str):
        super().__init__(format="A4")
        self.code = code
        self.notice = notice
        self.set_margins(20, 22, 20)
        self.set_auto_page_break(True, margin=22)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.set_xy(20, 10)
        self.cell(0, 5, clean(f"Strategy & Insights research report | {self.code}"), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(20, 16, 190, 16)
        self.set_y(22)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*RED)
        self.cell(120, 5, clean(self.notice))
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def render_study_report(study: dict, *, notice: str = SYNTHETIC_NOTICE) -> RenderedReport:
    code = study.get("code") or "Draft for S&I review"   # codes are assigned when a study is ingested
    pdf = _ReportPDF(code, notice)
    pdf.set_title(clean(study["title"]))
    pdf.set_author("Strategy & Insights (synthetic)")
    pdf.set_subject(clean(notice))
    pdf.set_creator("S&I evidence assistant demo generator")
    pdf.set_creation_date(datetime(2026, 1, 1, tzinfo=timezone.utc))

    def text(size: float, style: str = "", color=INK, family: str = "Helvetica"):
        pdf.set_font(family, style, size)
        pdf.set_text_color(*color)

    def para(body: str, size: float = 10.5, height: float = 5.6, style: str = "", color=INK):
        text(size, style, color)
        pdf.multi_cell(0, height, clean(body), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(2.5)

    def heading(title: str):
        if pdf.get_y() > 240:
            pdf.add_page()
        pdf.ln(2)
        text(15, "B", RED)
        pdf.cell(0, 9, clean(title), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    def subheading(title: str):
        text(11.5, "B", SLATE)
        pdf.cell(0, 7, clean(title), new_x="LMARGIN", new_y="NEXT")

    def ensure_room(height: float):
        if pdf.will_page_break(height):
            pdf.add_page()

    def bullet(body: str) -> int:
        """A finding bullet; returns the page it starts on (never split across a page break)."""
        text(10.5, "B")
        lines = pdf.multi_cell(165, 5.6, clean(body), dry_run=True, output="LINES")
        ensure_room(len(lines) * 5.6 + 3)
        page = pdf.page_no()
        pdf.cell(5, 5.6, "-")
        pdf.multi_cell(165, 5.6, clean(body), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(2.5)
        return page

    def verbatim(body: str, attribution: str) -> int:
        text(10.5, "I", INK)
        quote = f'"{body}" - {attribution}'
        lines = pdf.multi_cell(160, 5.6, clean(quote), dry_run=True, output="LINES")
        ensure_room(len(lines) * 5.6 + 4)
        page = pdf.page_no()
        pdf.set_x(28)
        pdf.multi_cell(160, 5.6, clean(quote), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(3)
        return page

    def bar_chart(items: list[tuple[str, float]], title: str):
        height = 12 + 8 * len(items)
        ensure_room(height + 6)
        subheading(title)
        top = pdf.get_y() + 2
        scale = 90 / max(100.0, max(v for _, v in items))
        for i, (label, value) in enumerate(items):
            y = top + i * 8
            text(9, "", INK)
            pdf.set_xy(20, y)
            pdf.cell(58, 6, clean(label[:38]))
            pdf.set_fill_color(*SLATE)
            pdf.rect(80, y + 1, max(0.5, value * scale), 4.5, style="F")
            pdf.set_xy(82 + value * scale, y)
            pdf.cell(20, 6, f"{value:g}%")
        pdf.set_y(top + 8 * len(items) + 3)
        text(8, "", MUTED)
        pdf.cell(0, 5, "Chart: share of respondents, total sample unless a subgroup is shown.",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    findings = study.get("findings") or []
    pages: list[int | None] = [None] * len(findings)
    method = study["method_type"]

    # ---------------------------------------------------------------- cover
    pdf.add_page()
    pdf.set_fill_color(*RED)
    pdf.rect(0, 0, 210, 14, style="F")
    pdf.set_y(40)
    text(10, "B", RED)
    pdf.cell(0, 6, "STRATEGY & INSIGHTS RESEARCH REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    text(24, "B", INK)
    pdf.multi_cell(0, 11, clean(study["title"]), new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(6)
    text(11, "", MUTED)
    _, end = _fieldwork_window(study)
    reported = f"{calendar.month_name[end.month % 12 + 1]} {end.year + (end.month == 12)}"  # the month after fieldwork
    for label, value in (("Study code", code), ("Commissioned by", study.get("owner_team") or "Strategy & Insights"),
                         ("Access", study.get("access_level") or "restricted"), ("Report date", reported)):
        pdf.cell(0, 6.5, clean(f"{label}: {value}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(220)
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.6)
    pdf.rect(20, 220, 170, 26)
    pdf.set_xy(24, 224)
    text(11, "B", RED)
    pdf.cell(0, 6, clean(notice), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(24)
    text(9, "", INK)
    pdf.multi_cell(160, 5, "Generated for the S&I evidence assistant prototype. Names, figures and quotations are "
                           "invented and must not be cited as research.", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_line_width(0.2)

    # ---------------------------------------------------------------- details, summary, method
    pdf.add_page()
    heading("Study details")
    for label, value in details_block(study):
        text(10, "B")
        pdf.cell(26, 6, clean(f"{label}:"))
        text(10, "")
        pdf.cell(0, 6, clean(value), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    heading("Summary")
    para(study.get("summary") or "")
    heading("Method and sample")
    for p in _method_paragraphs(study):
        para(p)

    # ---------------------------------------------------------------- key findings
    pdf.add_page()
    heading("Key findings")
    themes = [(i, f) for i, f in enumerate(findings) if f["finding_type"] != "verbatim"]
    quotes = [(i, f) for i, f in enumerate(findings) if f["finding_type"] == "verbatim"]
    headline = [(metric_label(f.get("metric_key")), float(f["value"])) for _, f in themes
                if f["finding_type"] == "quant_stat" and f.get("unit") == "%" and f.get("value") is not None
                and not f.get("subgroup")]
    intro = {
        "quant": "Results below are from the survey. Each finding shows its base; subgroup results follow the "
                 "total-sample results they break down.",
        "qual": "Themes below summarise what participants described across the groups. They indicate the range "
                "of views, not how common each view is.",
        "mixed": "Survey percentages come first, followed by the themes from the in-depth interviews that help "
                 "explain them.",
    }[method]
    para(intro)
    if headline and len(headline) >= 2:
        bar_chart(headline, "Headline results")
    for count, (i, f) in enumerate(themes):
        if count and count % 2 == 0:
            pdf.add_page()   # two findings per page, so page citations are meaningful
        sub = f.get("subgroup") or {}
        if f["finding_type"] == "quant_stat":
            label = metric_label(f.get("metric_key"))
            subheading(f"{label}{' (subgroup)' if sub.get('age_band') or sub.get('region') else ''}")
        else:
            subheading(metric_label(f.get("metric_key")) if f.get("metric_key") else "Theme")
        pages[i] = bullet(f["text"])
        if f["finding_type"] == "quant_stat" and f.get("base_n"):
            para(f"Base: {'subgroup' if sub else 'all respondents'} (n={int(f['base_n']):,}).", size=9, color=MUTED)
        elif f["finding_type"] == "qual_theme":
            para("Raised in several groups; see the quotations in the next section.", size=9, color=MUTED)

    if quotes:
        pdf.add_page()
        heading("In their words")
        para("Quotations are lightly edited for clarity. Attributions give occupation, age and location.",
             size=9, color=MUTED)
        for i, f in quotes:
            pages[i] = verbatim(f["text"], _attribution(f))

    # ---------------------------------------------------------------- about
    pdf.add_page()
    heading("About this report")
    owner = study.get("owner_team") or "Strategy & Insights"
    para(f"This report was prepared by Strategy & Insights{'' if owner == 'Strategy & Insights' else ' for ' + owner}. "
         f"Findings in the evidence assistant cite this document by study code ({code}) and page.")
    para("Limitations: results describe the population covered above and should not be generalised to other "
         "regions, age groups or segments without checking the study details.")
    para(notice + " Every name, figure and quotation in this document is invented for the hackathon "
         "prototype.", style="B", color=RED)

    output = bytes(pdf.output())
    return RenderedReport(pdf=output, pages=[p or 1 for p in pages], page_count=pdf.page_no(),
                          filename=_filename(study))
