"""Brief confidence, computed in code. The LLM does not report its own confidence.

High:   at least one supporting Tier A quantitative finding and no unresolved conflicts.
Medium: supporting quantitative evidence is Tier B at best, or the brief rests on context only.
Low:    qualitative evidence only, or an unresolved conflict that bears on the question.

An unresolved conflict bears on the question when the headline cites it, when its findings mention
the question's own concept (topicality.overlap), or when the question names no concept at all. A
conflict elsewhere in the brief (a nearby metric the reader did not ask about) caps confidence at
Medium instead of forcing Low. Proposed rule (IMPROVEMENTS C6), not validated by S&I.

Only quantitative tiers count. Qualitative studies are tiered by recency (a recent focus group can
be Tier B), but that describes how current the voices are, not how widespread a view is, so it
never raises confidence.

Two cases the rules leave open are treated conservatively: a brief with no surviving claims, and one
whose best supporting quantitative evidence is Tier C, are both Low.
"""

from __future__ import annotations

from . import topicality
from .retrieval import Source
from .schemas import ContextNote, EvidenceBrief


def bears_on_question(note: ContextNote, brief: EvidenceBrief, sources: dict[str, Source], question: str | None) -> bool:
    if not question or not topicality.specific_terms(question):
        return True
    headline_ids = {e.finding_id for c in brief.claims if c.kind == "headline" for e in c.evidence}
    if headline_ids & set(note.finding_ids):
        return True
    return any(topicality.overlap(question, sources[f]) for f in note.finding_ids if f in sources)


def compute_confidence(brief: EvidenceBrief, sources: dict[str, Source], *, restricted_matches: int = 0,
                       unmatched_terms: list[str] | None = None, question: str | None = None) -> dict:
    """The level and reasons, then two caps: High drops to Medium when a restricted study also
    matches the question (the answer reflects only what the reader can read; nothing about the
    restricted study is revealed), and when no cited finding mentions the question's own concept."""
    result = _base_confidence(brief, sources, question)
    caps = []
    nearby = [n for n in brief.unresolved_conflicts if not bears_on_question(n, brief, sources, question)]
    if nearby and result["level"] != "low":
        topics = ", ".join(dict.fromkeys(n.topic.split(":")[-1].replace("_", " ") for n in nearby))
        caps.append(f"Studies differ on a related figure ({topics}); an analyst has been asked to check them.")
    if restricted_matches:
        caps.append("This reflects only the studies you can read; a restricted study also matches this question.")
    if unmatched_terms:
        caps.append(f"None of the studies found mentions {', '.join(sorted(unmatched_terms)[:3])} directly; "
                    f"check they answer your question.")
    if caps and result["level"] == "high":
        result = {"level": "medium", "reasons": result["reasons"] + caps}
    elif caps:
        result = {**result, "reasons": result["reasons"] + caps}
    return result


def _base_confidence(brief: EvidenceBrief, sources: dict[str, Source], question: str | None = None) -> dict:
    cited =[sources[e.finding_id] for c in brief.claims for e in c.evidence if e.finding_id in sources]
    supporting = [
        sources[e.finding_id] for c in brief.claims for e in c.evidence
        if e.stance == "supports" and e.finding_id in sources and sources[e.finding_id].is_quant
    ]
    context_reason = (
        ["Differences between studies are explained by who was sampled."] if brief.context_notes else []
    )

    if not brief.claims:
        return {"level": "low", "reasons": ["No finding you can read supports an answer."]}
    if any(bears_on_question(n, brief, sources, question) for n in brief.unresolved_conflicts):
        return {"level": "low", "reasons": [
            "Two studies of the same population and period report different results; an analyst has been asked to check them."]}
    if not any(not s.is_qual for s in cited):
        return {"level": "low", "reasons": ["Qualitative evidence only; it cannot show how widespread a view is."]}

    tiers = {s.effective_tier for s in supporting}
    codes = sorted({s.study_code for s in supporting if s.effective_tier == "A"})
    if "A" in tiers:
        return {"level": "high", "reasons": [f"Supported by Tier A evidence ({', '.join(codes)})."] + context_reason}
    if "B" in tiers:
        return {"level": "medium", "reasons": ["The best supporting survey evidence is Tier B."] + context_reason}
    if supporting:
        return {"level": "low", "reasons": ["The best supporting survey evidence is Tier C."] + context_reason}
    return {"level": "medium", "reasons": ["The evidence gives context rather than direct support."] + context_reason}
