"""Plain-language labels for studies, populations and values, shared by the brief, the citation
sidebar, the offline writer and the PDF export."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from . import geography
from .config import metric_label
from .divergence import DivergenceGroup
from .retrieval import Source
from .tiers import months_between

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


def _people(segment: str | None, default: str) -> str:
    if not segment:
        return default
    return segment if segment.split()[0].isupper() else segment[:1].lower() + segment[1:]


def who_was_asked(source: Source) -> str:
    """"SME owners aged 20–40 in NCR (SI-2026-014, quant, n=1,200, 2026)"."""
    pop = source.population or {}
    regions = pop.get("regions") or []
    age = age_phrase(pop.get("age_min"), pop.get("age_max"))
    year = source.fieldwork_end.year if source.fieldwork_end else "date not stated"
    detail = f"({source.study_code}, {source.method_type or 'method not stated'}, {sample_phrase(source)}, {year})"
    if source.method_type == "qual":
        people = _people(pop.get("segment"), "participants")
        where = f"in the {join_words(regions)} groups" if regions else "in the groups"
    else:
        people = _people(pop.get("segment"), "respondents")
        place = geography.describe(regions)
        where = "nationwide" if place == "Nationwide" else f"in {place}"
    return " ".join(part for part in (people, age, where, detail) if part)


def topic_label(topic: str) -> str:
    if topic.startswith("theme:"):
        return topic.split(":", 1)[1].replace("_", " ").capitalize()
    return metric_label(topic)


def _unique_studies(sources: Iterable[Source]) -> list[Source]:
    seen: dict[str, Source] = {}
    for s in sources:
        seen.setdefault(s.study_id, s)
    return list(seen.values())


def explain_group(group: DivergenceGroup, sources: dict[str, Source]) -> str:
    """Deterministic explanation, used by the offline writer and whenever the LLM's explanation is
    missing or fails validation."""
    members = [sources[i] for i in group.finding_ids if i in sources]
    label = topic_label(group.topic)
    if group.kind == "context_difference":
        high = _unique_studies(s for s in members if s.resolved_direction() == "high")
        low = _unique_studies(s for s in members if s.resolved_direction() == "low")
        return (
            f"{label}: prominent among {join_words(who_was_asked(s) for s in high)}, "
            f"but not among {join_words(who_was_asked(s) for s in low)}. "
            f"The studies differ by {join_words(group.differs_by)}, so the difference reflects who was "
            f"asked rather than a contradiction."
        )
    a, b = members[0], members[1]
    return (
        f"{a.study_code} and {b.study_code} sampled the same population ({study_population(a)}) within "
        f"{abs(months_between(a.fieldwork_end, b.fieldwork_end)) if a.fieldwork_end and b.fieldwork_end else 'a few'} "
        f"months of each other, yet report {fmt_value(a.value, a.unit) or a.resolved_direction()} and "
        f"{fmt_value(b.value, b.unit) or b.resolved_direction()} for “{label}”. Sampling does not "
        f"explain the gap, so an S&I analyst should review both studies before this is used."
    )


def compute_gaps(sources: list[Source], today: date) -> list[str]:
    """Gaps that can be stated from the evidence itself: missing quant, missing regions, old data."""
    findings = [s for s in sources if s.finding_type != "verbatim"]
    if not findings:
        return []
    gaps: list[str] = []
    studies = _unique_studies(findings)
    if not any(s.is_quant and s.effective_tier in ("A", "B") for s in findings):
        gaps.append("No Tier A or B quantitative study measures this, so how widespread these views are is unknown.")
    covered = {g for s in studies for g in geography.island_groups((s.population or {}).get("regions"))}
    missing = [g for g in geography.ISLAND_GROUPS if g not in covered]
    if missing:
        gaps.append(f"No study in this evidence covers {join_words(missing, 'or')}.")
    quant_groups = {
        g for s in studies if s.is_quant for g in geography.island_groups((s.population or {}).get("regions"))
    }
    qual_only_groups = [g for g in geography.ISLAND_GROUPS if g in covered and g not in quant_groups]
    if qual_only_groups and quant_groups:
        gaps.append(f"Evidence for {join_words(qual_only_groups)} is qualitative only; no survey measures it there.")
    nationwide_quant = [s for s in studies if s.is_quant and geography.is_nationwide((s.population or {}).get("regions"))]
    if nationwide_quant and not any(s.is_quant and (s.subgroup or {}).get("region") for s in findings):
        gaps.append("The nationwide surveys are not broken down by region, so island groups cannot be compared directly.")
    dated = [s.fieldwork_end for s in studies if s.fieldwork_end]
    if dated and months_between(max(dated), today) > 18:
        gaps.append(f"The most recent fieldwork ended in {max(dated):%B %Y}; later behaviour is not covered.")
    return gaps


def source_view(source: Source) -> dict:
    """What the citation sidebar shows for one finding."""
    pop = source.population or {}
    return {
        "finding_id": source.finding_id,
        "study_id": source.study_id,
        "study_code": source.study_code,
        "study_title": source.study_title,
        "owner_team": source.owner_team,
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
        "sample_size": source.sample_size,
        "fieldwork_end": source.fieldwork_end.isoformat() if source.fieldwork_end else None,
        "region_label": geography.describe(pop.get("regions")),
        "population_label": study_population(source),
        "tier": source.effective_tier,
        "tier_overridden": bool(source.tier_override),
    }
