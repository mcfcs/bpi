"""Context-aware divergence between findings, classified in code before the LLM writes anything.

S&I's experience is that apparent conflicts are usually explained by sampling: different age
bands, regions, segments, periods or methods. Two findings diverge when they report opposite
directions on the same metric_key (or theme). A divergence is a context difference when the
populations differ on at least one of those dimensions; only when they don't is it an
unresolved conflict, which the UI labels as a conflict and routes to an analyst.

Rules from the second consultation:
- Quantitative and qualitative findings are never compared. Survey figures drive the answer and
  group discussions support it; qualitative evidence that runs against a survey is shown as
  colour in "What people say" (describe.qual_contrasts), not as a divergence.
- Opposite directions on one metric inside the same study (two waves, or two subgroups) are two
  trends in the same study (kind "within_study"), explained with who each subgroup is. They are
  never a conflict.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Literal

from . import geography
from .config import DIVERGENCE_CONFIG
from .tiers import months_between

DIFFERS_BY_ORDER = ("age", "region", "segment", "period", "method")

DivergenceKind = Literal["context_difference", "unresolved_conflict", "within_study"]


@dataclass(frozen=True)
class FindingCtx:
    finding_id: str
    study_id: str
    topic: str | None          # metric_key, or "theme:<theme>" when the finding has no metric_key
    direction: str | None      # high | low | neutral
    method_type: str | None
    age_min: int | None
    age_max: int | None
    regions: tuple[str, ...]
    segment: str | None
    fieldwork_end: date | None
    evidence: str | None = None                       # "quant" or "qual"; derived from method_type when None
    subgroup: tuple[tuple[str, str], ...] = ()        # sorted (key, value) pairs of the finding's subgroup


@dataclass
class DivergencePair:
    a: str
    b: str
    differs_by: list[str]


@dataclass
class DivergenceGroup:
    kind: DivergenceKind
    topic: str
    finding_ids: list[str]
    differs_by: list[str]
    pairs: list[DivergencePair] = field(default_factory=list)


def ranges_overlap(a: tuple[int | None, int | None], b: tuple[int | None, int | None],
                   min_ratio: float | None = None) -> bool:
    """True when two age ranges cover substantially the same people (intersection over union of at
    least min_ratio). Unknown bounds count as overlapping: missing data must not invent a context
    difference."""
    min_ratio = DIVERGENCE_CONFIG["age_overlap_min"] if min_ratio is None else min_ratio
    (a_lo, a_hi), (b_lo, b_hi) = a, b
    if None in (a_lo, a_hi, b_lo, b_hi):
        return True
    intersection = min(a_hi, b_hi) - max(a_lo, b_lo)
    if intersection < 0:
        return False
    union = max(a_hi, b_hi) - min(a_lo, b_lo)
    return union == 0 or intersection / union >= min_ratio


def regions_overlap(a: Iterable[str], b: Iterable[str], min_ratio: float | None = None) -> bool:
    """Same rule for places, after expanding cities, provinces and "Nationwide" to regions."""
    min_ratio = DIVERGENCE_CONFIG["region_overlap_min"] if min_ratio is None else min_ratio
    ra, rb = geography.expand(a), geography.expand(b)
    if not ra or not rb:
        return True
    return len(ra & rb) / len(ra | rb) >= min_ratio


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def evidence_kind(f: FindingCtx) -> str | None:
    if f.evidence:
        return f.evidence
    if f.method_type == "qual":
        return "qual"
    return "quant" if f.method_type else None


def cross_method(a: FindingCtx, b: FindingCtx) -> bool:
    """A survey figure and a qualitative theme: never compared directly."""
    ka, kb = evidence_kind(a), evidence_kind(b)
    return bool(ka and kb and ka != kb)


def classify_divergence(a: FindingCtx, b: FindingCtx) -> tuple[DivergenceKind, list[str]]:
    cfg = DIVERGENCE_CONFIG
    differs_by: list[str] = []
    if not ranges_overlap((a.age_min, a.age_max), (b.age_min, b.age_max)):
        differs_by.append("age")
    if not regions_overlap(a.regions, b.regions):
        differs_by.append("region")
    if a.segment and b.segment and _norm(a.segment) != _norm(b.segment):
        differs_by.append("segment")
    if a.fieldwork_end and b.fieldwork_end and abs(months_between(a.fieldwork_end, b.fieldwork_end)) > cfg["period_months"]:
        differs_by.append("period")
    if a.method_type and b.method_type and a.method_type != b.method_type:
        differs_by.append("method")
    return ("context_difference", differs_by) if differs_by else ("unresolved_conflict", [])


def _opposite(a: FindingCtx, b: FindingCtx) -> bool:
    return a.topic is not None and a.topic == b.topic and {a.direction, b.direction} == {"high", "low"}


def diverges(a: FindingCtx, b: FindingCtx) -> bool:
    """Opposite directions on the same metric or theme, from different studies, with the same kind
    of evidence (survey with survey, qualitative with qualitative)."""
    return _opposite(a, b) and a.study_id != b.study_id and not cross_method(a, b)


def _is_wave(value: str) -> bool:
    return bool(re.search(r"\bwave\b", value, re.IGNORECASE))


def subgroup_differs_by(a: FindingCtx, b: FindingCtx) -> list[str]:
    """Which subgroup dimensions separate two findings of the same study. A segment that names a
    survey wave counts as a period."""
    sa, sb = dict(a.subgroup), dict(b.subgroup)
    dims = set()
    for key in set(sa) | set(sb):
        if _norm(sa.get(key)) == _norm(sb.get(key)):
            continue
        if key == "age_band":
            dims.add("age")
        elif key == "region":
            dims.add("region")
        elif key == "segment":
            dims.add("period" if _is_wave(sa.get(key) or "") or _is_wave(sb.get(key) or "") else "segment")
    return [d for d in DIFFERS_BY_ORDER if d in dims]


def same_study_trends(a: FindingCtx, b: FindingCtx) -> bool:
    """Opposite directions on one metric within one study, for different subgroups or waves."""
    return (_opposite(a, b) and a.study_id == b.study_id and not cross_method(a, b)
            and a.subgroup != b.subgroup and bool(subgroup_differs_by(a, b)))


def _ordered_union(lists: Iterable[list[str]]) -> list[str]:
    seen = {item for items in lists for item in items}
    return [d for d in DIFFERS_BY_ORDER if d in seen]


def _ids(pairs: list[DivergencePair]) -> list[str]:
    return list(dict.fromkeys(i for p in pairs for i in (p.a, p.b)))


def analyze(findings: list[FindingCtx]) -> list[DivergenceGroup]:
    """All divergences among retrieved findings: one context-difference group per topic (pairs
    merged), one group per unresolved pair, and one within-study group per study and topic."""
    by_topic: dict[str, list[FindingCtx]] = {}
    for f in findings:
        if f.topic and f.direction in ("high", "low"):
            by_topic.setdefault(f.topic, []).append(f)

    groups: list[DivergenceGroup] = []
    for topic, items in sorted(by_topic.items()):
        context_pairs: list[DivergencePair] = []
        conflict_pairs: list[DivergencePair] = []
        within: dict[str, list[DivergencePair]] = {}
        for a, b in combinations(items, 2):
            if same_study_trends(a, b):
                within.setdefault(a.study_id, []).append(DivergencePair(a.finding_id, b.finding_id, subgroup_differs_by(a, b)))
                continue
            if not diverges(a, b):
                continue
            kind, differs_by = classify_divergence(a, b)
            pair = DivergencePair(a.finding_id, b.finding_id, differs_by)
            (context_pairs if kind == "context_difference" else conflict_pairs).append(pair)
        if context_pairs:
            groups.append(DivergenceGroup(
                "context_difference", topic, _ids(context_pairs), _ordered_union(p.differs_by for p in context_pairs), context_pairs,
            ))
        for pair in conflict_pairs:
            groups.append(DivergenceGroup("unresolved_conflict", topic, [pair.a, pair.b], [], [pair]))
        for pairs in within.values():
            groups.append(DivergenceGroup("within_study", topic, _ids(pairs), _ordered_union(p.differs_by for p in pairs), pairs))
    return groups


def parse_age_band(band: str | None) -> tuple[int | None, int | None]:
    """"20-40", "20–40", "20 to 40", "60+" -> (20, 40), (20, 40), (20, 40), (60, 99)."""
    if not band:
        return None, None
    match = re.match(r"\s*(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*$", band)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r"\s*(\d{1,2})\s*\+\s*$", band)
    if match:
        return int(match.group(1)), 99
    return None, None
