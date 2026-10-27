"""Checks run on every generated brief before anyone sees it.

On failure the brief is regenerated once with the problems listed; claims that still fail are
dropped. Context notes always take their topic, findings and differs_by from the code classifier;
an explanation that fails is replaced with a deterministic one.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .describe import explain_group
from .divergence import DivergenceGroup
from .retrieval import Source
from .schemas import Claim, ContextNote, EvidenceBrief

# The proposed pattern put a trailing \b after "%", which never matches before a space or the end
# of the text; the percentage alternative is therefore anchored separately here.
QUAL_FORBIDDEN = re.compile(r"\b(?:most|majority|all|proves?|percent|per\s?cent)\b|\b\d+(?:\.\d+)?\s?%", re.IGNORECASE)
QUAL_HEDGES = (
    re.compile(r"\bindicatively\b", re.IGNORECASE),
    re.compile(r"\bparticipants described\b", re.IGNORECASE),
    re.compile(r"\bsuggests?\b", re.IGNORECASE),
    re.compile(r"\bin the [A-Za-z][\w ,.&'’-]{0,60}? groups\b", re.IGNORECASE),
)
CONFLICT_WORD = re.compile(r"\bconflict", re.IGNORECASE)

NO_QUANT_MESSAGE = "No quantitative study covers this; qualitative evidence only."
NO_AB_QUANT_MESSAGE = "No Tier A or B quantitative study covers this; the quantitative evidence below is Tier C."
QUAL_DISCLAIMER = "Qualitative findings describe how participants feel and are not representative of the wider population."


@dataclass
class Issue:
    section: str        # claims | context_notes | unresolved_conflicts | brief
    index: int | None
    code: str
    message: str


def cited_ids(claim: Claim) -> list[str]:
    return [e.finding_id for e in claim.evidence] + list(claim.verbatim_ids)


def is_qual_only(claim: Claim, sources: dict[str, Source]) -> bool:
    ids = cited_ids(claim)
    return bool(ids) and all(i in sources and sources[i].is_qual for i in ids)


def is_ab_quant(source: Source) -> bool:
    return source.is_quant and source.effective_tier in ("A", "B")


def has_hedge(text: str) -> bool:
    return any(p.search(text) for p in QUAL_HEDGES)


def _match_group(note: ContextNote, kind: str, groups: list[DivergenceGroup]) -> DivergenceGroup | None:
    candidates = [g for g in groups if g.kind == kind and g.topic == note.topic]
    if len(candidates) == 1:
        return candidates[0]
    wanted = set(note.finding_ids)
    return next((g for g in candidates if set(g.finding_ids) == wanted), None)


def validate_brief(brief: EvidenceBrief, sources: dict[str, Source], groups: list[DivergenceGroup],
                   show_id: Callable[[str], str] = str) -> list[Issue]:
    issues: list[Issue] = []

    for i, claim in enumerate(brief.claims):
        where = f'Claim {i + 1} ({claim.kind}: "{claim.text[:80]}")'
        unknown = [x for x in cited_ids(claim) if x not in sources]
        if unknown:
            # The citation-ID validator: every cited finding must be one that was retrieved for this user.
            issues.append(Issue("claims", i, "unknown_finding_id",
                                f"{where} cites ids that are not in the findings list: {', '.join(map(show_id, unknown))}."))
            continue
        if claim.verbatim_ids and claim.kind != "qualitative_insight":
            issues.append(Issue("claims", i, "verbatim_outside_qual", f"{where} attaches verbatims; only qualitative_insight claims may."))
        not_verbatims = [v for v in claim.verbatim_ids if sources[v].finding_type != "verbatim"]
        if not_verbatims:
            issues.append(Issue("claims", i, "not_a_verbatim",
                                f"{where} lists {', '.join(map(show_id, not_verbatims))} in verbatim_ids but they are not verbatims."))
        if is_qual_only(claim, sources):
            match = QUAL_FORBIDDEN.search(claim.text)
            if match:
                issues.append(Issue("claims", i, "qual_incidence_language",
                                    f"{where} cites only qualitative findings but says \"{match.group(0)}\". Qualitative evidence "
                                    f"cannot say how many people; remove counts, percentages and words like most, majority, all, proves."))
            if not has_hedge(claim.text):
                issues.append(Issue("claims", i, "qual_missing_hedge",
                                    f"{where} cites only qualitative findings and must be hedged with \"indicatively\", "
                                    f"\"participants described\", \"suggests\" or \"in the <location> groups\"."))
        if claim.kind == "headline" and not any(is_ab_quant(sources[e.finding_id]) for e in claim.evidence):
            issues.append(Issue("claims", i, "headline_without_ab_quant",
                                f"{where} is a headline but cites no Tier A or B quantitative finding."))
        if CONFLICT_WORD.search(claim.text):
            issues.append(Issue("claims", i, "conflict_wording",
                                f"{where} uses the word conflict; only unresolved conflicts may be called that."))

    for section, kind, notes in (("context_notes", "context_difference", brief.context_notes),
                                 ("unresolved_conflicts", "unresolved_conflict", brief.unresolved_conflicts)):
        for i, note in enumerate(notes):
            if _match_group(note, kind, groups) is None:
                issues.append(Issue(section, i, "unknown_divergence",
                                    f"{section}[{i}] (topic {note.topic}) does not match a {kind} given in the input."))
            elif kind == "context_difference" and CONFLICT_WORD.search(note.explanation):
                issues.append(Issue(section, i, "conflict_wording",
                                    f"{section}[{i}] calls a context difference a conflict."))

    for group in groups:
        section = "context_notes" if group.kind == "context_difference" else "unresolved_conflicts"
        notes = brief.context_notes if section == "context_notes" else brief.unresolved_conflicts
        if not any(_match_group(n, group.kind, groups) is group for n in notes):
            issues.append(Issue("brief", None, "missing_divergence_note",
                                f"No {section} entry for the {group.kind} on {group.topic}."))
    return issues


def finalize(brief: EvidenceBrief, issues: list[Issue], sources: dict[str, Source],
             groups: list[DivergenceGroup], chartable: list[str]) -> tuple[EvidenceBrief, list[dict]]:
    """Drop claims that still fail, rebuild divergence notes from the classifier, keep one headline."""
    failing: dict[int, list[str]] = {}
    for issue in issues:
        if issue.section == "claims" and issue.index is not None:
            failing.setdefault(issue.index, []).append(issue.code)
    dropped = [{"kind": c.kind, "text": c.text, "reasons": failing[i]} for i, c in enumerate(brief.claims) if i in failing]
    claims = [c.model_copy(deep=True) for i, c in enumerate(brief.claims) if i not in failing]

    seen_headline = False
    for claim in claims:
        if claim.kind == "headline":
            if seen_headline:
                claim.kind = "breakdown"
            seen_headline = True
    order = {"headline": 0, "breakdown": 1, "qualitative_insight": 2}
    claims.sort(key=lambda c: order[c.kind])

    bad_notes = {(i.section, i.index) for i in issues if i.section in ("context_notes", "unresolved_conflicts")}
    explanations: dict[int, str] = {}
    for section, kind, notes in (("context_notes", "context_difference", brief.context_notes),
                                 ("unresolved_conflicts", "unresolved_conflict", brief.unresolved_conflicts)):
        for i, note in enumerate(notes):
            group = _match_group(note, kind, groups)
            if group is not None and (section, i) not in bad_notes and note.explanation.strip():
                explanations.setdefault(id(group), note.explanation.strip())

    context_notes, unresolved = [], []
    for group in groups:
        note = ContextNote(
            topic=group.topic,
            finding_ids=list(group.finding_ids),
            differs_by=list(group.differs_by),
            explanation=explanations.get(id(group)) or explain_group(group, sources),
        )
        (context_notes if group.kind == "context_difference" else unresolved).append(note)

    final = EvidenceBrief(
        claims=claims,
        context_notes=context_notes,
        unresolved_conflicts=unresolved,
        chart_requests=[k for k in dict.fromkeys(brief.chart_requests) if k in chartable],
        gaps=[g for g in brief.gaps if g.strip() and not CONFLICT_WORD.search(g)],
    )
    return final, dropped
