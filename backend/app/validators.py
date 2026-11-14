"""Checks run on every generated brief before anyone sees it.

On failure the brief is regenerated once with the problems listed; claims that still fail are
dropped. Divergence notes (context differences, unresolved conflicts, two trends in one study)
always take their topic, findings and differs_by from the code classifier; an explanation that
fails is replaced with a deterministic one. Audience summaries that fail are replaced with the
deterministic templates built from the surviving claims.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .describe import build_summaries, explain_group, numbers_in, source_numbers
from .divergence import DivergenceGroup
from .geography import QUESTION_AREA_PHRASES, in_area, question_area
from .retrieval import Source
from .schemas import AudienceSummary, Claim, ContextNote, EvidenceBrief

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
# S&I: "it's less about saying that the studies disagree but rather what each says". Framing two
# results as a disagreement reads as low confidence; explanations say what each group found.
DISAGREE_WORDS = re.compile(r"\b(?:disagree\w*|contradict\w*|inconsistent|at odds)\b", re.IGNORECASE)

NO_QUANT_MESSAGE = "No quantitative study covers this; qualitative evidence only."
NO_AB_QUANT_MESSAGE = "No Tier A or B quantitative study covers this; the quantitative evidence below is Tier C."
QUAL_DISCLAIMER = "Qualitative findings describe how participants feel and are not representative of the wider population."

AUDIENCES = ("executive", "analyst", "plain")
NOTE_SECTIONS = (("context_notes", "context_difference"), ("unresolved_conflicts", "unresolved_conflict"),
                 ("study_patterns", "within_study"))


@dataclass
class Issue:
    section: str        # claims | context_notes | unresolved_conflicts | study_patterns | summaries | brief
    index: int | None
    code: str
    message: str


def cited_ids(claim: Claim) -> list[str]:
    return [e.finding_id for e in claim.evidence] + list(claim.verbatim_ids)


def _all_qual(ids: list[str], sources: dict[str, Source]) -> bool:
    return bool(ids) and all(i in sources and sources[i].is_qual for i in ids)


def is_qual_only(claim: Claim, sources: dict[str, Source]) -> bool:
    return _all_qual(cited_ids(claim), sources)


def is_ab_quant(source: Source) -> bool:
    return source.is_quant and source.effective_tier in ("A", "B")


def has_hedge(text: str) -> bool:
    return any(p.search(text) for p in QUAL_HEDGES)


def new_numbers(text: str, cited: list[Source]) -> set[float]:
    """Numbers in a text that none of the cited findings contains (so the writer made them up or
    calculated them)."""
    allowed: set[float] = set()
    for s in cited:
        allowed |= source_numbers(s)
    return numbers_in(text) - allowed


def _notes(brief: EvidenceBrief, section: str) -> list[ContextNote]:
    return getattr(brief, section)


def _match_group(note: ContextNote, kind: str, groups: list[DivergenceGroup]) -> DivergenceGroup | None:
    candidates = [g for g in groups if g.kind == kind and g.topic == note.topic]
    if len(candidates) == 1:
        return candidates[0]
    wanted = set(note.finding_ids)
    return next((g for g in candidates if set(g.finding_ids) == wanted), None)


def _qual_rule_issues(section: str, index: int, where: str, text: str) -> list[Issue]:
    issues = []
    match = QUAL_FORBIDDEN.search(text)
    if match:
        issues.append(Issue(section, index, "qual_incidence_language",
                            f"{where} cites only qualitative findings but says \"{match.group(0)}\". Qualitative evidence "
                            f"cannot say how many people; remove counts, percentages and words like most, majority, all, proves."))
    if not has_hedge(text):
        issues.append(Issue(section, index, "qual_missing_hedge",
                            f"{where} cites only qualitative findings and must be hedged with \"indicatively\", "
                            f"\"participants described\", \"suggests\" or \"in the <location> groups\"."))
    return issues


def validate_summary(i: int, summary: AudienceSummary, sources: dict[str, Source],
                     show_id: Callable[[str], str] = str) -> list[Issue]:
    where = f'Summary {i + 1} ({summary.audience}: "{summary.text[:80]}")'
    unknown = [x for x in summary.finding_ids if x not in sources]
    if unknown:
        return [Issue("summaries", i, "unknown_finding_id",
                      f"{where} cites ids that are not in the findings list: {', '.join(map(show_id, unknown))}.")]
    if not summary.finding_ids or not summary.text.strip():
        return [Issue("summaries", i, "summary_without_evidence", f"{where} must cite the refs it relies on.")]
    issues = []
    invented = new_numbers(summary.text, [sources[x] for x in summary.finding_ids])
    if invented:
        shown = ", ".join(sorted(f"{n:g}" for n in invented))
        issues.append(Issue("summaries", i, "summary_new_number",
                            f"{where} states numbers that none of its cited findings contains ({shown}). Summaries "
                            f"repeat the brief's facts; they never calculate or add figures."))
    if _all_qual(summary.finding_ids, sources):
        issues += _qual_rule_issues("summaries", i, where, summary.text)
    if CONFLICT_WORD.search(summary.text):
        issues.append(Issue("summaries", i, "conflict_wording",
                            f"{where} uses the word conflict; say what each study found instead."))
    if DISAGREE_WORDS.search(summary.text):
        issues.append(Issue("summaries", i, "disagreement_wording",
                            f"{where} says studies disagree or contradict; say what each group found instead."))
    return issues


def in_question_area(source: Source, area: str) -> bool:
    _, _, regions, segment = source.population_view()
    return in_area(area, regions, segment)


def place_issue(question: str | None, where: str, claim: Claim, sources: dict[str, Source],
                show_id: Callable[[str], str] = str) -> Issue | None:
    """A headline that leads with another place's figure when the question names a place and Tier A/B
    figures for that place were retrieved ("Are long ATM queues a problem outside Metro Manila?" led
    with the Metro Manila 57%). Section "brief": it asks for a rewrite but never drops the headline."""
    area = question_area(question)
    if not area:
        return None
    local = [fid for fid, s in sources.items() if is_ab_quant(s) and in_question_area(s, area)]
    if not local or any(in_question_area(sources[f], area) for f in cited_ids(claim) if f in sources):
        return None
    place = QUESTION_AREA_PHRASES.get(area, area)
    return Issue("brief", None, "headline_ignores_place",
                 f"{where} leads with figures for another place, but the question asks about {place}. "
                 f"Lead with the findings for {place}: {', '.join(map(show_id, local))}.")


def validate_brief(brief: EvidenceBrief, sources: dict[str, Source], groups: list[DivergenceGroup],
                   show_id: Callable[[str], str] = str, question: str | None = None) -> list[Issue]:
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
            issues += _qual_rule_issues("claims", i, where, claim.text)
        if claim.kind == "headline" and not any(is_ab_quant(sources[e.finding_id]) for e in claim.evidence):
            issues.append(Issue("claims", i, "headline_without_ab_quant",
                                f"{where} is a headline but cites no Tier A or B quantitative finding."))
        if claim.kind == "headline":
            wrong_place = place_issue(question, where, claim, sources, show_id)
            if wrong_place:
                issues.append(wrong_place)
        if claim.kind != "qualitative_insight":
            # A disputed figure stated alone reads as the answer, in a headline or a breakdown alike.
            cited = set(cited_ids(claim))
            for group in groups:
                if group.kind == "unresolved_conflict" and cited & set(group.finding_ids) and not set(group.finding_ids) <= cited:
                    issues.append(Issue("claims", i, f"{claim.kind}_hides_conflict",
                                        f"{where} states one side of an unresolved conflict on {group.topic} as the answer. "
                                        f"Cite every finding in that conflict ({', '.join(map(show_id, group.finding_ids))}) "
                                        f"and say what each study found, for whom."))
        if CONFLICT_WORD.search(claim.text):
            issues.append(Issue("claims", i, "conflict_wording",
                                f"{where} uses the word conflict; only unresolved conflicts may be called that."))
        if DISAGREE_WORDS.search(claim.text):
            issues.append(Issue("claims", i, "disagreement_wording",
                                f"{where} says studies disagree or contradict; say what each group found instead."))

    for section, kind in NOTE_SECTIONS:
        for i, note in enumerate(_notes(brief, section)):
            if _match_group(note, kind, groups) is None:
                issues.append(Issue(section, i, "unknown_divergence",
                                    f"{section}[{i}] (topic {note.topic}) does not match a {kind} given in the input."))
                continue
            if kind != "unresolved_conflict" and CONFLICT_WORD.search(note.explanation):
                issues.append(Issue(section, i, "conflict_wording",
                                    f"{section}[{i}] calls a {kind.replace('_', ' ')} a conflict."))
            if DISAGREE_WORDS.search(note.explanation):
                issues.append(Issue(section, i, "disagreement_wording",
                                    f"{section}[{i}] says the studies disagree or contradict; say what each group found, "
                                    f"for whom, where and when."))

    for group in groups:
        section = next(s for s, k in NOTE_SECTIONS if k == group.kind)
        if not any(_match_group(n, group.kind, groups) is group for n in _notes(brief, section)):
            issues.append(Issue("brief", None, "missing_divergence_note",
                                f"No {section} entry for the {group.kind} on {group.topic}."))

    for i, summary in enumerate(brief.summaries):
        issues += validate_summary(i, summary, sources, show_id)
    return issues


def finalize(brief: EvidenceBrief, issues: list[Issue], sources: dict[str, Source],
             groups: list[DivergenceGroup], chartable: list[str]) -> tuple[EvidenceBrief, list[dict]]:
    """Drop claims that still fail, rebuild divergence notes from the classifier, keep one headline,
    and keep valid audience summaries (filling the rest from templates)."""
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
    claims.sort(key=lambda c: order[c.kind])   # survey evidence first, qualitative support after

    bad_notes = {(i.section, i.index) for i in issues if i.section in dict(NOTE_SECTIONS)}
    explanations: dict[int, str] = {}
    for section, kind in NOTE_SECTIONS:
        for i, note in enumerate(_notes(brief, section)):
            group = _match_group(note, kind, groups)
            if group is not None and (section, i) not in bad_notes and note.explanation.strip():
                explanations.setdefault(id(group), note.explanation.strip())

    rebuilt: dict[str, list[ContextNote]] = {s: [] for s, _ in NOTE_SECTIONS}
    for group in groups:
        section = next(s for s, k in NOTE_SECTIONS if k == group.kind)
        rebuilt[section].append(ContextNote(
            topic=group.topic,
            finding_ids=list(group.finding_ids),
            differs_by=list(group.differs_by),
            explanation=explanations.get(id(group)) or explain_group(group, sources),
        ))

    final = EvidenceBrief(
        claims=claims,
        context_notes=rebuilt["context_notes"],
        unresolved_conflicts=rebuilt["unresolved_conflicts"],
        study_patterns=rebuilt["study_patterns"],
        chart_requests=[k for k in dict.fromkeys(brief.chart_requests) if k in chartable],
        gaps=[g for g in brief.gaps if g.strip() and not CONFLICT_WORD.search(g) and not DISAGREE_WORDS.search(g)],
    )

    bad_summaries = {i.index for i in issues if i.section == "summaries"}
    kept: dict[str, AudienceSummary] = {}
    for i, summary in enumerate(brief.summaries):
        if i not in bad_summaries and summary.audience not in kept:
            kept[summary.audience] = summary
    templates = {s.audience: s for s in build_summaries(final, sources, groups)}
    final.summaries = [kept.get(a) or templates[a] for a in AUDIENCES if a in kept or a in templates]
    return final, dropped
