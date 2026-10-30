"""Plain-language labels for studies, populations and values, shared by the brief, the citation
sidebar, the offline writer and the PDF export.

Explanations follow S&I's second consultation: say what each group said, for whom, where and
when ("Fees: a driver of drop-off among applicants aged 20–40 in Metro Manila ...; not a driver
among applicants aged 41–60 nationwide ..."), never that studies "disagree". Every explanation
names who was asked.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from . import emotion, geography
from .config import metric_label, stance_phrases
from .divergence import DivergenceGroup
from .retrieval import Source
from .schemas import AudienceSummary, EvidenceBrief
from .tiers import TIER_BASIS, months_between

METHOD_LABELS = {"quant": "Quantitative", "qual": "Qualitative", "mixed": "Mixed method"}


def join_words(items: Iterable[str], conjunction: str = "and") -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {conjunction} " + items[-1]


def fmt_number(value: Decimal | float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"


def fmt_value(value: Decimal | float | None, unit: str | None) -> str:
    if value is None:
        return ""
    if unit == "%":
        return f"{fmt_number(value)}%"
    if unit == "rank":
        return f"rank {fmt_number(value)}"
    return f"{fmt_number(value)}{' ' + unit if unit else ''}"


def age_phrase(age_min: int | None, age_max: int | None) -> str:
    if age_min is None or age_max is None:
        return ""
    return f"aged {age_min}+" if age_max >= 99 else f"aged {age_min}–{age_max}"


def subgroup_label(subgroup: dict | None) -> str:
    if not subgroup:
        return ""
    parts = []
    if subgroup.get("age_band"):
        parts.append("Ages " + subgroup["age_band"].replace("-", "–"))
    if subgroup.get("region"):
        parts.append(subgroup["region"])
    if subgroup.get("segment"):
        parts.append(subgroup["segment"])
    return ", ".join(parts)


def study_population(source: Source) -> str:
    pop = source.population or {}
    segment = pop.get("segment") or "Respondents"
    age = age_phrase(pop.get("age_min"), pop.get("age_max"))
    place = geography.describe(pop.get("regions"))
    return f"{segment} {age}, {place}".replace("  ", " ").replace(" ,", ",")


def sample_phrase(source: Source) -> str:
    if not source.sample_size:
        return "sample size not stated"
    if source.method_type == "qual":
        return f"{source.sample_size:,} participants"
    return f"n={source.sample_size:,}"


# ---------------------------------------------------------------------------------------------
# Method and date labels: the reader must see that a source is "6 FGDs", not a survey.
# ---------------------------------------------------------------------------------------------

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30}
# (pattern, singular, plural, what the sessions are called in running text)
_QUAL_FORMATS = (
    (r"focus[- ]groups?|fgds?|group discussions?", "FGD", "FGDs", "groups"),
    (r"in-depth interviews?|idis?", "in-depth interview", "in-depth interviews", "interviews"),
    (r"interviews?", "interview", "interviews", "interviews"),
    (r"workshops?", "workshop", "workshops", "workshops"),
)


def qual_format(source: Source) -> tuple[int | None, str, str, str] | None:
    """(count, singular, plural, place word) of a qualitative study's sessions, read from its title
    and summary: "Six focus groups with ..." -> (6, "FGD", "FGDs", "groups")."""
    text = f"{source.study_title or ''}. {source.study_summary or ''}"
    numbers = "|".join(_NUMBER_WORDS)
    for pattern, one, many, place_word in _QUAL_FORMATS:
        match = re.search(rf"\b(\d{{1,3}}|{numbers})\s+(?:[a-z-]+\s+){{0,2}}?(?:{pattern})\b", text, re.IGNORECASE)
        if match:
            raw = match.group(1).lower()
            return (int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]), one, many, place_word
        if re.search(rf"\b(?:{pattern})\b", text, re.IGNORECASE):
            return None, one, many, place_word
    return None


def _is_tracker(source: Source) -> bool:
    return bool(re.search(r"\b(?:tracker|tracking|waves?)\b", f"{source.study_title} {source.study_summary or ''}", re.I))


def method_detail(source: Source) -> str:
    """"Survey · n=1,200", "6 FGDs · 42 participants", "Tracking survey · n=2,000"."""
    n = source.sample_size
    if source.method_type == "qual":
        fmt = qual_format(source)
        if fmt and fmt[0]:
            count, one, many, _ = fmt
            label = f"{count} {one if count == 1 else many}"
        elif fmt:
            label = fmt[2][:1].upper() + fmt[2][1:]
        else:
            label = "Qualitative"
        return f"{label} · {n:,} participants" if n else label
    label = "Mixed method" if source.method_type == "mixed" else "Tracking survey" if _is_tracker(source) else "Survey"
    return f"{label} · n={n:,}" if n else f"{label} · sample size not stated"


def method_short(source: Source) -> str:
    """The method inside running text: "survey of 1,200", "6 FGDs, 42 participants"."""
    detail = method_detail(source)
    if source.method_type == "qual":
        return detail.replace(" · ", ", ")
    noun = detail.split(" · ")[0].lower()
    return f"{noun} of {source.sample_size:,}" if source.sample_size else f"{noun}, sample size not stated"


def fieldwork_label(source: Source) -> str:
    return f"{source.fieldwork_end:%b %Y}" if source.fieldwork_end else "date not stated"


def _people(segment: str | None, default: str) -> str:
    if not segment:
        return default
    return segment if segment.split()[0].isupper() else segment[:1].lower() + segment[1:]


def _is_wave(text: str | None) -> bool:
    return bool(text and re.search(r"\bwave\b", text, re.IGNORECASE))


def qual_place(source: Source) -> str:
    """"in the Cebu and Iloilo groups", "in the Davao City interviews"."""
    regions = (source.population or {}).get("regions") or []
    fmt = qual_format(source)
    word = fmt[3] if fmt else "groups"
    return f"in the {join_words(regions)} {word}" if regions else f"in the {word}"


def who_was_asked(source: Source, *, value: bool = False) -> str:
    """Who a finding speaks for, with the study details a reader needs to weigh it:
    "SME owners aged 20–29 in Metro Manila (SI-2026-014, survey of 1,200, Mar 2026: 44%)"."""
    pop = source.population or {}
    age_min, age_max, regions, segment = source.population_view()
    sub = source.subgroup or {}
    wave = sub.get("segment") if _is_wave(sub.get("segment")) else None
    if wave or source.finding_type == "verbatim":
        segment = pop.get("segment")
    detail = f"{source.study_code}, {method_short(source)}, {fieldwork_label(source)}"
    if value and source.value is not None:
        detail += f": {fmt_value(source.value, source.unit)}"
    if source.method_type == "qual":
        people = _people(segment, "participants")
        where = qual_place(source)
    else:
        people = _people(segment, "respondents")
        where = geography.where_phrase(regions)
    when = f"in {wave[:1].lower() + wave[1:]}" if wave else ""
    return " ".join(p for p in (people, age_phrase(age_min, age_max), where, when, f"({detail})") if p)


def who_short(source: Source) -> str:
    """Who, without the study details: "digital card applicants aged 20–40 in Metro Manila"."""
    text = who_was_asked(source)
    return text[: text.rfind(" (")] if " (" in text else text


def topic_label(topic: str) -> str:
    if topic.startswith("theme:"):
        return topic.split(":", 1)[1].replace("_", " ").capitalize()
    return metric_label(topic)


def lower_label(label: str) -> str:
    """A label inside a sentence: keeps acronyms ("ID verification") and turns "Wants a named
    contact person" into "wanting a named contact person"."""
    for verb, gerund in (("Wants ", "wanting "), ("Prefers ", "preferring "), ("Cited ", "citing ")):
        if label.startswith(verb):
            return gerund + label[len(verb):]
    first = label.split()[0] if label.split() else ""
    return label if first[:2].isupper() else label[:1].lower() + label[1:]


def _unique_studies(sources: Iterable[Source]) -> list[Source]:
    """One finding per study, preferring the study-level figure over a subgroup."""
    seen: dict[str, Source] = {}
    for s in sources:
        if s.study_id not in seen or (seen[s.study_id].subgroup and not s.subgroup):
            seen[s.study_id] = s
    return list(seen.values())


def _metric(topic: str) -> str | None:
    return None if topic.startswith("theme:") else topic


# ---------------------------------------------------------------------------------------------
# Divergence explanations (deterministic; also the fallback when an LLM explanation fails).
# ---------------------------------------------------------------------------------------------

def _subgroup_phrase(source: Source) -> str:
    """How a within-study subgroup is named: "among customers aged 18–34", "in Metro Manila",
    "in wave 2 (Jun 2026)"."""
    sub = source.subgroup or {}
    pop = source.population or {}
    parts = []
    if sub.get("age_band"):
        lo, hi = source.population_view()[:2]
        parts.append(f"among {_people(pop.get('segment'), 'respondents')} {age_phrase(lo, hi)}")
    if sub.get("region"):
        parts.append(geography.where_phrase([sub["region"]]))
    if sub.get("segment"):
        seg = sub["segment"]
        parts.append(f"in {seg[:1].lower() + seg[1:]}" if _is_wave(seg) else f"among {_people(seg, 'respondents')}")
    if not parts:
        parts.append("across the whole sample")
    value = fmt_value(source.value, source.unit)
    # A tracker's value is the latest wave's level; a trend reads as the change ("61% → 72%"),
    # taken from the reviewed finding text, never from the model.
    change = _TREND_CHANGE.search(source.text or "") if _is_tracker(source) else None
    if change:
        value = f"{change.group(1)}% → {change.group(2)}%"
    return " ".join(parts) + (f" ({value})" if value else "")


_TREND_CHANGE = re.compile(r"from (\d+(?:\.\d+)?)%.{0,40}?\bto (\d+(?:\.\d+)?)%")


def segment_statement(group: DivergenceGroup, sources: dict[str, Source], *, short: bool = False) -> str:
    """"Fees: a driver of drop-off among X; not a driver of drop-off among Y." With short=True the
    study details are left out (for summaries)."""
    members = [sources[i] for i in group.finding_ids if i in sources]
    hi, lo = stance_phrases(_metric(group.topic))
    who = who_short if short else (lambda s: who_was_asked(s, value=True))
    high = _unique_studies(s for s in members if s.resolved_direction() == "high")
    low = _unique_studies(s for s in members if s.resolved_direction() == "low")
    return (f"{topic_label(group.topic)}: {hi} among {join_words(who(s) for s in high)}; "
            f"{lo} among {join_words(who(s) for s in low)}.")


def short_statement(group: DivergenceGroup, sources: dict[str, Source]) -> str:
    """One-line form of a divergence for summaries: segment statement, or the two directions inside
    one study ("Long branch queues: a pain point in Metro Manila (57%); not a main pain point in ...")."""
    if group.kind != "within_study":
        return segment_statement(group, sources, short=True)
    members = [sources[i] for i in group.finding_ids if i in sources]
    hi, lo = stance_phrases(_metric(group.topic))
    high = [m for m in members if m.resolved_direction() == "high"]
    low = [m for m in members if m.resolved_direction() == "low"]
    return (f"{topic_label(group.topic)}: {hi} {join_words(_subgroup_phrase(m) for m in high)}; "
            f"{lo} {join_words(_subgroup_phrase(m) for m in low)}.")


def _place_contrast(members: list[Source]) -> str | None:
    high = [s for s in members if s.resolved_direction() == "high"]
    low = [s for s in members if s.resolved_direction() == "low"]
    if not high or not low:
        return None
    return geography.contrast_note(high[0].population_view()[2], low[0].population_view()[2])


def explain_group(group: DivergenceGroup, sources: dict[str, Source]) -> str:
    """Deterministic explanation, used by the offline writer and whenever the LLM's explanation is
    missing or fails validation."""
    members = [sources[i] for i in group.finding_ids if i in sources]
    label = topic_label(group.topic)
    if group.kind == "context_difference":
        area = _place_contrast(members)
        return (f"{segment_statement(group, sources)} Each result describes the people that study asked; "
                f"the groups differ by {join_words(group.differs_by)}" + (f" ({area})" if area else "") + ".")
    if group.kind == "within_study":
        study = members[0]
        hi, lo = stance_phrases(_metric(group.topic))
        high = [s for s in members if s.resolved_direction() == "high"]
        low = [s for s in members if s.resolved_direction() == "low"]
        trends = "period" in group.differs_by or _is_tracker(study)
        area = _place_contrast(members) if "region" in group.differs_by else None
        return (f"{label}: {'two trends' if trends else 'two patterns'} in the same study, {study.study_code}, which asked "
                f"{_people((study.population or {}).get('segment'), 'respondents')} "
                f"{age_phrase((study.population or {}).get('age_min'), (study.population or {}).get('age_max'))} "
                f"{geography.where_phrase((study.population or {}).get('regions'))} ({method_short(study)}, {fieldwork_label(study)}). "
                f"{hi[:1].upper() + hi[1:]} {join_words(_subgroup_phrase(s) for s in high)}; "
                f"{lo} {join_words(_subgroup_phrase(s) for s in low)}"
                + (f". The split is {area}" if area else "")
                + f". Each {'trend' if trends else 'pattern'} holds for its own group.").replace("  ", " ")
    a, b = members[0], members[1]
    gap = abs(months_between(a.fieldwork_end, b.fieldwork_end)) if a.fieldwork_end and b.fieldwork_end else None
    within = f"within {gap} months of each other" if gap is not None else "in the same period"
    return (
        f"{label}: {a.study_code} found {fmt_value(a.value, a.unit) or a.resolved_direction()} "
        f"({method_short(a)}, {fieldwork_label(a)}) and {b.study_code} found "
        f"{fmt_value(b.value, b.unit) or b.resolved_direction()} ({method_short(b)}, {fieldwork_label(b)}). "
        f"Both asked {who_short(a)}, {within}, so who was asked does not explain the difference. "
        f"An S&I analyst is checking both studies; don't rely on either figure alone until then."
    )


# ---------------------------------------------------------------------------------------------
# Qualitative evidence: contrasts with surveys, themes across groups, feelings.
# ---------------------------------------------------------------------------------------------

def qual_contrasts(sources: list[Source]) -> list[dict]:
    """Qualitative themes that run opposite to a survey finding on the same topic. They are colour
    for "What people say", never a divergence: survey and group evidence are not compared."""
    quant = [s for s in sources if s.is_quant and s.finding_type == "quant_stat" and s.topic]
    out = []
    for q in sources:
        if q.finding_type != "qual_theme" or q.is_quant or q.resolved_direction() not in ("high", "low"):
            continue
        opposite = [s.finding_id for s in quant if s.topic == q.topic
                    and {s.resolved_direction(), q.resolved_direction()} == {"high", "low"}]
        if opposite:
            out.append({"finding_id": q.finding_id, "topic": q.topic, "quant_finding_ids": opposite})
    return out


def contrast_sentence(theme: Source, quant: list[Source]) -> str:
    codes = join_words(sorted({s.study_code for s in quant}))
    return (f"This view comes from {who_was_asked(theme)} and runs against the survey figures on "
            f"{lower_label(topic_label(theme.topic or ''))} in {codes}; it adds colour and does not "
            f"measure how common the view is.")


def emotions_for(texts: Iterable[str | None]) -> list[dict]:
    return emotion.detect_many(texts)


def synthesize_themes(themes: list[Source], verbatims: list[Source] = ()) -> str | None:
    """What came up across the qualitative groups, newest fieldwork first, with the feelings voiced.
    Hedged by construction ("Participants described ...") and free of incidence language."""
    themes = sorted((t for t in themes if t.topic), key=lambda s: s.fieldwork_end or date.min, reverse=True)
    if len(themes) < 2:
        return None
    by_topic: dict[str, list[Source]] = {}
    for t in themes:
        by_topic.setdefault(t.topic, []).append(t)
    studies = _unique_studies(themes)

    def place(s: Source) -> str:
        return f"{qual_place(s)[3:]} ({fieldwork_label(s)})"   # "the Cebu and Iloilo groups (Aug 2026)"

    labels = [lower_label(topic_label(t)) for t in by_topic]
    text = f"Participants described {join_words(labels)}"
    shared = [t for t, items in by_topic.items() if len({s.study_id for s in items}) > 1]
    if len(studies) == 1 or len(by_topic) == 1:
        text += f" in {join_words(place(s) for s in studies)}."
    elif shared:
        first = topic_label(shared[0]) if len(shared) == 1 else join_words(topic_label(t) for t in shared)
        sharing = _unique_studies(s for t in shared for s in by_topic[t])
        text += f". {first[:1].upper() + first[1:]} came up across {join_words(place(s) for s in sharing)}."
    else:
        text += f", in {join_words(place(s) for s in studies)}."
    feelings = emotions_for([t.text for t in themes] + [v.text for v in verbatims])
    if feelings:
        text += f" Feelings voiced include {join_words(f['label'].lower() for f in feelings)}."
    return text


# ---------------------------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------------------------

def compute_gap_items(sources: list[Source], today: date) -> list[dict]:
    """Gaps that can be stated from the evidence itself, each with a stable code and a specific
    question an analyst could answer ("ask")."""
    findings = [s for s in sources if s.finding_type != "verbatim"]
    if not findings:
        return []
    gaps: list[dict] = []
    studies = _unique_studies(findings)
    if not any(s.is_quant and s.effective_tier in ("A", "B") for s in findings):
        gaps.append({"code": "no_ab_quant",
                     "text": "No Tier A or B quantitative study measures this, so how widespread these views are is unknown.",
                     "ask": "Is there a survey, approved or in progress, that measures how widespread this is?"})
    covered = {g for s in studies for g in geography.island_groups((s.population or {}).get("regions"))}
    missing = [g for g in geography.ISLAND_GROUPS if g not in covered]
    if missing:
        gaps.append({"code": "region_missing", "text": f"No study in this evidence covers {join_words(missing, 'or')}.",
                     "ask": f"Has S&I studied this in {join_words(missing, 'or')}, or is it not yet researched there?"})
    quant_groups = {
        g for s in studies if s.is_quant for g in geography.island_groups((s.population or {}).get("regions"))
    }
    qual_only_groups = [g for g in geography.ISLAND_GROUPS if g in covered and g not in quant_groups]
    if qual_only_groups and quant_groups:
        gaps.append({"code": "qual_only_region",
                     "text": f"Evidence for {join_words(qual_only_groups)} is qualitative only; no survey measures it there.",
                     "ask": f"Is there survey evidence for {join_words(qual_only_groups)}, or only the group discussions?"})
    nationwide_quant = [s for s in studies if s.is_quant and geography.is_nationwide((s.population or {}).get("regions"))]
    if nationwide_quant and not any(s.is_quant and (s.subgroup or {}).get("region") for s in findings):
        gaps.append({"code": "no_region_breakdown",
                     "text": ("The nationwide survey is" if len(nationwide_quant) == 1 else "The nationwide surveys are")
                             + " not broken down by region, so island groups cannot be compared directly.",
                     "ask": f"Can {join_words(sorted({s.study_code for s in nationwide_quant}))} be broken down by region?"})
    dated = [s.fieldwork_end for s in studies if s.fieldwork_end]
    if dated and months_between(max(dated), today) > 18:
        gaps.append({"code": "stale", "text": f"The most recent fieldwork ended in {max(dated):%B %Y}; later behaviour is not covered.",
                     "ask": f"Is there anything more recent than {max(dated):%B %Y} on this?"})
    return gaps


def compute_gaps(sources: list[Source], today: date) -> list[str]:
    return [g["text"] for g in compute_gap_items(sources, today)]


# ---------------------------------------------------------------------------------------------
# Audience summaries (offline templates; also the fallback for an LLM summary that fails checks)
# ---------------------------------------------------------------------------------------------

def _first_sentence(text: str) -> str:
    match = re.search(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return text[: match.start()] if match else text


def _hedged(text: str) -> str:
    from .validators import has_hedge   # local import: validators imports this module

    if has_hedge(text):
        return text
    return "Indicatively, " + (text if text.split()[0][:2].isupper() else text[:1].lower() + text[1:])


def build_summaries(brief: EvidenceBrief, sources: dict[str, Source], groups: list[DivergenceGroup]) -> list[AudienceSummary]:
    """Executive, analyst and plain-language versions of the brief: the same facts and citations
    in a different register, built only from the validated claims and the code-classified groups.
    They add no number that the cited findings don't contain."""
    claims = brief.claims
    if not claims:
        return []
    headline = next((c for c in claims if c.kind == "headline"), None)
    breakdowns = [c for c in claims if c.kind == "breakdown"]
    quals = [c for c in claims if c.kind == "qualitative_insight"]
    context = [g for g in groups if g.kind == "context_difference" and all(i in sources for i in g.finding_ids)]
    patterns = [g for g in groups if g.kind == "within_study" and all(i in sources for i in g.finding_ids)]
    conflicts = [g for g in groups if g.kind == "unresolved_conflict" and all(i in sources for i in g.finding_ids)]

    def ids(*items) -> list[str]:
        out: list[str] = []
        for item in items:
            if item is None:
                continue
            out += [e.finding_id for e in item.evidence] if hasattr(item, "evidence") else list(item.finding_ids)
        return list(dict.fromkeys(i for i in out if i in sources))

    qual_ids = ids(*quals)
    qual_texts = [sources[i].text for i in qual_ids] + [sources[v].text for c in quals for v in c.verbatim_ids if v in sources]
    feelings = [f["label"].lower() for f in emotions_for(qual_texts)]
    lead_claim = headline or (breakdowns[0] if breakdowns else None)
    extra_groups = context[:1] or patterns[:1]

    def conflict_line(plain: bool = False) -> str:
        g = conflicts[0]
        label = lower_label(topic_label(g.topic))
        if plain:
            return f"Two surveys of the same people gave different answers on {label}, so an analyst is checking them."
        return f"On {label}, two surveys of the same group report different results; an S&I analyst is checking them."

    if lead_claim is None:
        # Qualitative evidence only: hedged in every register.
        lead = _hedged(_first_sentence(quals[0].text))
        tail = " It shows how participants feel, not how many hold the view."
        exec_text = lead + tail
        lead_src = sources[qual_ids[0]] if qual_ids else None
        analyst_text = lead
        if lead_src:
            analyst_text = (f"Qualitative evidence only: {join_words(sorted({sources[i].study_code for i in qual_ids}))} "
                            f"({method_detail(lead_src)}, {fieldwork_label(lead_src)}, Tier {lead_src.effective_tier or 'not set'}, "
                            f"tiered by recency). {lead} No survey measures how widespread this is.")
        plain_text = lead + (f" People voiced {join_words(feelings)}." if feelings else "") + " This shows how some people feel, not how many."
        return [AudienceSummary(audience="executive", text=exec_text, finding_ids=qual_ids),
                AudienceSummary(audience="analyst", text=analyst_text, finding_ids=qual_ids),
                AudienceSummary(audience="plain", text=plain_text, finding_ids=qual_ids)]

    lead_ids = ids(lead_claim)
    lead_src = next((sources[i] for i in lead_ids if sources[i].is_quant), sources[lead_ids[0]])
    first = _first_sentence(lead_claim.text)

    # Executive: the answer, then what it depends on.
    if headline or lead_src.effective_tier in ("A", "B"):
        exec_parts = [first]
    else:
        exec_parts = [f"Only Tier C survey evidence covers this: {lower_label(first)}"]
    headline_covers = bool(headline) and any(set(g.finding_ids) <= set(ids(headline)) for g in conflicts)
    exec_parts += [short_statement(g, sources) for g in extra_groups]
    if conflicts and not headline_covers:
        exec_parts.append(conflict_line())
    exec_ids = ids(lead_claim, *extra_groups, *conflicts[:1])

    # Analyst: sources, methods, tiers, then the qualifications.
    analyst_parts = [f"Lead evidence: {lead_src.study_code} ({method_detail(lead_src)}, {fieldwork_label(lead_src)}, "
                     f"Tier {lead_src.effective_tier or 'not set'}). {first}"]
    support = sorted({sources[i].study_code for c in breakdowns for i in ids(c)} - {lead_src.study_code})
    if support:
        analyst_parts.append(f"Further survey figures: {join_words(support)}.")
    if qual_ids:
        qual_studies = _unique_studies(sources[i] for i in qual_ids)
        analyst_parts.append("Qualitative support, not compared with the survey figures: " + join_words(
            f"{s.study_code} ({method_detail(s)}, {fieldwork_label(s)})" for s in qual_studies) + ".")
    for g in context:
        analyst_parts.append(f"On {lower_label(topic_label(g.topic))}, the groups asked differ by {join_words(g.differs_by)}.")
    for g in patterns:
        analyst_parts.append(f"{sources[g.finding_ids[0]].study_code} shows two trends on "
                             f"{lower_label(topic_label(g.topic))}, by {join_words(g.differs_by)}.")
    for g in conflicts:
        analyst_parts.append(f"Unresolved, with an analyst: {topic_label(g.topic)} in "
                             f"{join_words(sorted({sources[i].study_code for i in g.finding_ids}))}.")
    analyst_ids = ids(lead_claim, *breakdowns, *quals, *context, *patterns, *conflicts)

    # Plain language: short words, the same facts.
    if headline_covers:
        plain_parts = [conflict_line(plain=True)]
    else:
        where = (f"a survey of {lead_src.sample_size:,} people ({lead_src.study_code})" if lead_src.sample_size
                 else lead_src.study_code)
        plain_parts = [f"In short, from {where}: {first}"]
    for g in extra_groups:
        lead_in = "It depends on who you ask." if g.kind == "context_difference" else "Different groups went different ways."
        plain_parts.append(f"{lead_in} {short_statement(g, sources)}")
    if conflicts and not headline_covers:
        plain_parts.append(conflict_line(plain=True))
    if qual_ids:
        plain_parts.append(f"In group discussions, people voiced {join_words(feelings)}." if feelings
                           else "Group discussions add the reasons in people's own words.")
    plain_ids = ids(lead_claim, *extra_groups, *conflicts[:1], *quals)

    return [AudienceSummary(audience="executive", text=" ".join(exec_parts), finding_ids=exec_ids),
            AudienceSummary(audience="analyst", text=" ".join(analyst_parts), finding_ids=analyst_ids),
            AudienceSummary(audience="plain", text=" ".join(plain_parts), finding_ids=plain_ids)]


# ---------------------------------------------------------------------------------------------
# Facts a summary may quote, and the citation sidebar
# ---------------------------------------------------------------------------------------------

_CODE = re.compile(r"\b[A-Z]{2,}-\d{4}-\d{2,4}\b|\bF\d+\b")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str | None) -> set[float]:
    """Numbers in a text, ignoring study codes and prompt refs (SI-2026-014, F3)."""
    if not text:
        return set()
    out = set()
    for raw in _NUMBER.findall(_CODE.sub(" ", text)):
        try:
            out.add(float(raw.replace(",", "").rstrip(".")))
        except ValueError:
            continue
    return out


def source_numbers(source: Source) -> set[float]:
    """Every number a statement citing this finding may quote."""
    pop = source.population or {}
    nums = numbers_in(source.text) | numbers_in(source.study_title) | numbers_in(method_detail(source))
    nums |= numbers_in(" ".join(str(v) for v in (source.subgroup or {}).values()))
    for v in (source.value, source.base_n, source.sample_size, pop.get("age_min"), pop.get("age_max")):
        if v is not None:
            nums.add(float(v))
    if source.fieldwork_end:
        nums.add(float(source.fieldwork_end.year))
    lo, hi = source.population_view()[:2]
    nums |= {float(x) for x in (lo, hi) if x is not None}
    return nums


def source_view(source: Source) -> dict:
    """What the citation sidebar shows for one finding."""
    pop = source.population or {}
    return {
        "finding_id": source.finding_id,
        "study_id": source.study_id,
        "study_code": source.study_code,
        "study_title": source.study_title,
        "owner_team": source.owner_team,
        "access_level": source.access_level,
        "text": source.text,
        "finding_type": source.finding_type,
        "metric_key": source.metric_key,
        "value": None if source.value is None else float(source.value),
        "unit": source.unit,
        "base_n": source.base_n,
        "subgroup": source.subgroup,
        "subgroup_label": subgroup_label(source.subgroup),
        "method_type": source.method_type,
        "method_label": METHOD_LABELS.get(source.method_type or "", "Method not stated"),
        "method_detail": method_detail(source),
        "evidence_kind": "quant" if source.is_quant else "qual",
        "sample_size": source.sample_size,
        "fieldwork_end": source.fieldwork_end.isoformat() if source.fieldwork_end else None,
        "fieldwork_label": fieldwork_label(source),
        "region_label": geography.describe(pop.get("regions")),
        "area_label": geography.area_label(source.population_view()[2]),
        "population_label": study_population(source),
        "tier": source.effective_tier,
        "tier_overridden": bool(source.tier_override),
        "tier_basis": TIER_BASIS.get(source.method_type or "", None),
        "emotion": emotion.detect(source.text) if source.finding_type in ("qual_theme", "verbatim") else None,
    }
