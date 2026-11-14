"""Heuristic study-card extraction for demos without Claude credentials.

It reads semi-structured reports like those in data/synthetic/reports: a details block (Method,
Sample, Fieldwork, Coverage, Segment), key-finding bullets and quoted verbatims. PDF reports are
first turned into the same form by `documents.normalise_report_text` (running headers and footers
dropped, wrapped bullets and quotations joined). Prose reports need the Claude extractor. Either
way an S&I analyst checks every field at review (checkpoint 1) before anything becomes searchable.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

from . import geography
from .config import DIRECTION_FALLBACK
from .schemas import ExtractedFinding, ExtractedPopulation, ExtractedSubgroup, StudyCardExtraction

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})

AGE_RANGE = re.compile(r"aged\s+(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})", re.IGNORECASE)
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
# "rose from 61% in wave 1 to 72% in wave 2": the finding's value is the latest figure, not the first.
CHANGE = re.compile(r"\bfrom (\d+(?:\.\d+)?)\s?%.{0,60}?\bto (\d+(?:\.\d+)?)\s?%")
RANK =re.compile(r"rank(?:ed)?\s+(\d+)(?:\s+of\s+\d+)?", re.IGNORECASE)
BASE_N = re.compile(r"(?:base\s+)?n\s*=\s*([\d,]+)", re.IGNORECASE)

# Most specific first: "would renew online if their documents were on file" is about renewal, not documents.
METRIC_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("renew online", "online renewal", "renew their loans online"), "channel_pref:online_renewal"),
    (("contact person", "someone to call", "call back", "callback", "relationship manager"), "support:contact_person"),
    (("cashback", "cash back"), "reward_pref:cashback"),
    (("travel",), "reward_pref:travel"),
    (("approval time", "how long", "approval took"), "barrier:approval_time"),
    (("collateral",), "barrier:collateral"),
    (("app error", "crash"), "barrier:app_errors"),
    (("fee", "charges"), "barrier:fees"),
    (("document", "itr", "paperwork"), "barrier:documents"),
]


def _dates(text: str) -> list[date]:
    found: list[date] = []
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        found.append(date(int(m[1]), int(m[2]), int(m[3])))
    text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    for m in re.finditer(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text):
        if m[2].lower() in MONTHS:
            found.append(date(int(m[3]), MONTHS[m[2].lower()], int(m[1])))
    text = re.sub(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", " ", text)
    for m in re.finditer(r"\b([A-Za-z]+)\s+(\d{4})\b", text):
        if m[1].lower() in MONTHS:
            year, month = int(m[2]), MONTHS[m[1].lower()]
            found.append(date(year, month, calendar.monthrange(year, month)[1]))
    return found


def _method(text: str) -> str | None:
    t = text.lower()
    qual = any(w in t for w in ("focus group", "fgd", "in-depth interview", "qualitative", "ethnograph", "usability"))
    quant = any(w in t for w in ("survey", "quantitative", "questionnaire"))
    return "mixed" if qual and quant else "qual" if qual else "quant" if quant else None


def _locations(text: str) -> list[str]:
    names: list[str] = []
    original = f" {text} "
    lowered = original.lower()
    for key in sorted(geography.ALIASES, key=len, reverse=True):
        match = re.search(rf"(?<![a-z]){re.escape(key)}(?![a-z])", lowered)
        if match:
            # Keep the report's own spelling ("Cagayan de Oro", not "Cagayan De Oro").
            as_written = original[match.start():match.end()]
            display = next((r for r in geography.REGION_ISLAND_GROUP if r.lower() == key),
                           as_written if not as_written.islower() else key.title())
            if not any(key in n.lower() for n in names):
                names.append("Nationwide" if key in geography.NATIONWIDE else display)
            # Blank out every occurrence in both strings, keeping offsets aligned.
            for m in reversed(list(re.finditer(re.escape(key), lowered))):
                blank = " " * (m.end() - m.start())
                lowered = lowered[:m.start()] + blank + lowered[m.end():]
                original = original[:m.start()] + blank + original[m.end():]
    return names


def _metric(text: str) -> str | None:
    t = text.lower()
    return next((key for hints, key in METRIC_HINTS if any(h in t for h in hints)), None)


def _direction(value: float | None, unit: str | None) -> str | None:
    if value is None or unit not in DIRECTION_FALLBACK:
        return None
    high, low = DIRECTION_FALLBACK[unit]
    if unit == "rank":
        return "high" if value <= high else "low" if value >= low else "neutral"
    return "high" if value >= high else "low" if value <= low else "neutral"


def _subgroup(text: str) -> ExtractedSubgroup | None:
    age = re.search(r"(?:among|for)\s+[\w\s]*?aged\s+(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})", text, re.IGNORECASE)
    region = re.search(r"\b(?:in|among owners in)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", text)
    region_name = region.group(1) if region and region.group(1).lower() in geography.ALIASES else None
    if not age and not region_name:
        return None
    return ExtractedSubgroup(age_band=f"{age.group(1)}-{age.group(2)}" if age else None, region=region_name, segment=None)


# ---------------------------------------------------------------------------
# Prose fallback: reports without a labelled details block (most real PDFs). Cautious on purpose:
# it fills a field only from a sentence that clearly states it, and the analyst checks it at review.
# Findings are not guessed from prose; they need Claude or the analyst.
# ---------------------------------------------------------------------------

PROSE_WINDOW = 25_000   # method and sample are described near the start of a report
SAMPLE_PROSE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d{2,6})\s+(?:[A-Za-z-]+\s+){0,3}?"
    r"(adults|respondents|households|firms|drivers|participants|financial customers|customers|"
    r"interviewees|businesses|enterprises|MSMEs|borrowers|owners)\b", re.IGNORECASE)
SAMPLE_CUES = re.compile(r"sample|responses|interviewed|participated|involving|surveyed|completed", re.IGNORECASE)
FIELDWORK_CUES = re.compile(r"\b(?:conducted|fieldwork|field work|survey period|interviewed|carried out|collected)\b",
                            re.IGNORECASE)
QUAL_CUES = ("focus group", "fgd", "in-depth interview", "qualitative", "case study", "ethnograph")
QUANT_CUES = ("survey", "questionnaire", "respondents", "quantitative", "random sampl")


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", flat) if s.strip()]


def _prose_method(text: str) -> str | None:
    t = text[:PROSE_WINDOW].lower()
    qual = sum(t.count(c) for c in QUAL_CUES)
    quant = sum(t.count(c) for c in QUANT_CUES)
    if qual >= 3 and quant >= 3:
        return "mixed"
    if quant > qual:
        return "quant"
    return "qual" if qual else None


def _prose_sample(sentences: list[str]) -> int | None:
    candidates = []
    for sentence in sentences:
        for m in SAMPLE_PROSE.finditer(sentence):
            n = int(m.group(1).replace(",", ""))
            if 1900 <= n <= 2100 and "," not in m.group(1):
                continue   # a year, not a sample
            window = sentence[max(0, m.start() - 80): m.end() + 40]
            candidates.append((0 if SAMPLE_CUES.search(window) else 1, len(candidates), n))
    return min(candidates)[2] if candidates else None


def _prose_fieldwork(sentences: list[str], text: str) -> date | None:
    for sentence in sentences:
        if FIELDWORK_CUES.search(sentence):
            found = _dates(sentence)
            if found:
                return max(found)
    cover = _dates(text[:400])   # last resort: the report date on the cover (flagged at review)
    return max(cover) if cover else None


def _prose_regions(sentences: list[str], text: str) -> list[str]:
    head = text[:PROSE_WINDOW].lower()
    if "nationally representative" in head or "nationwide" in head:
        return ["Nationwide"]
    for sentence in sentences:
        if SAMPLE_CUES.search(sentence) and SAMPLE_PROSE.search(sentence):
            found = [r for r in _locations(sentence.replace("National Capital Region", "NCR")) if r != "Nationwide"]
            if found:
                return found
    return []


def _section(text: str, heading: str) -> list[str]:
    match = re.search(rf"^##\s+{heading}\s*$(.*?)(?=^##\s|\Z)", text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    return [line.strip() for line in match.group(1).splitlines() if line.strip()] if match else []


def extract(report_text: str) -> StudyCardExtraction:
    fields: dict[str, str] = {}
    for line in report_text.splitlines():
        m = re.match(r"^\s*([A-Za-z ]{3,20}):\s*(.+?)\s*$", line)
        if m and m.group(1).strip().lower() not in fields:
            fields[m.group(1).strip().lower()] = m.group(2)

    title_match = re.search(r"^#\s+(.+)$", report_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled study"
    method_type = _method(fields.get("method", "") + " " + title)

    sample_line = fields.get("sample", "")
    participants = re.search(r"([\d,]+)\s+participants", sample_line)
    n_match = BASE_N.search(sample_line)
    sample_size = None
    if method_type == "qual" and participants:
        sample_size = int(participants.group(1).replace(",", ""))
    elif n_match:
        sample_size = int(n_match.group(1).replace(",", ""))
    elif participants:
        sample_size = int(participants.group(1).replace(",", ""))

    fieldwork = _dates(fields.get("fieldwork", ""))
    coverage = fields.get("coverage", "")
    ages = AGE_RANGE.search(coverage)
    population = ExtractedPopulation(
        age_min=int(ages.group(1)) if ages else None,
        age_max=int(ages.group(2)) if ages else None,
        regions=_locations(coverage),
        segment=fields.get("segment"),
    )

    findings: list[ExtractedFinding] = []
    for line in _section(report_text, "Key findings"):
        if not line.startswith(("-", "*")):
            continue
        text = line.lstrip("-* ").strip()
        value, unit = None, None
        if method_type != "qual":
            pct, rank, change = PERCENT.search(text), RANK.search(text), CHANGE.search(text)
            if change:
                value, unit = float(change.group(2)), "%"
            elif pct:
                value, unit = float(pct.group(1)), "%"
            elif rank:
                value, unit = float(rank.group(1)), "rank"
        base = BASE_N.search(text)
        findings.append(ExtractedFinding(
            text=text,
            finding_type="quant_stat" if value is not None else "qual_theme",
            theme=None,
            metric_key=_metric(text),
            value=value,
            unit=unit,
            base_n=int(base.group(1).replace(",", "")) if base else None,
            subgroup=_subgroup(text),
            direction=_direction(value, unit),
        ))
    for line in report_text.splitlines():
        if not line.lstrip().startswith(">"):
            continue
        quote, _, attribution = line.lstrip("> ").partition("—")
        regions = _locations(attribution)
        findings.append(ExtractedFinding(
            text=quote.strip().strip('"“”'),
            finding_type="verbatim",
            theme=None,
            metric_key=_metric(quote),
            value=None,
            unit=None,
            base_n=None,
            subgroup=ExtractedSubgroup(
                age_band=None,
                region=regions[0] if regions else None,
                segment=attribution.split(",")[0].strip() or None,
            ) if attribution.strip() else None,
            direction=None,
        ))

    if "method" not in fields or "sample" not in fields or "fieldwork" not in fields:
        sentences = _sentences(report_text[:PROSE_WINDOW])
        if "method" not in fields:
            method_type = method_type or _prose_method(report_text)
        if "sample" not in fields:
            sample_size = sample_size or _prose_sample(sentences)
        if "fieldwork" not in fields and not fieldwork:
            end = _prose_fieldwork(sentences, report_text)
            fieldwork = [end] if end else []
        if "coverage" not in fields and not population.regions:
            population.regions = _prose_regions(sentences, report_text)

    summary_lines = _section(report_text, "Summary")
    return StudyCardExtraction(
        title=title,
        summary=" ".join(summary_lines),
        method_type=method_type,
        sample_size=sample_size,
        fieldwork_end=max(fieldwork).isoformat() if fieldwork else None,
        population=population,
        findings=findings,
    )
