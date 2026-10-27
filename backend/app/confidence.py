"""Brief confidence, computed in code. The LLM does not report its own confidence.

High:   at least one supporting Tier A finding and no unresolved conflicts.
Medium: supporting evidence is Tier B at best, or the brief rests on context only.
Low:    qualitative evidence only, or any unresolved conflict.

Two cases the rules leave open are treated conservatively: a brief with no surviving claims, and one
whose best supporting evidence is Tier C, are both Low.
"""

from __future__ import annotations

from .retrieval import Source
from .schemas import EvidenceBrief


def compute_confidence(brief: EvidenceBrief, sources: dict[str, Source]) -> dict:
    cited = [sources[e.finding_id] for c in brief.claims for e in c.evidence if e.finding_id in sources]
    supporting = [
        sources[e.finding_id] for c in brief.claims for e in c.evidence
        if e.stance == "supports" and e.finding_id in sources
    ]
    context_reason = (
        ["Differences between studies are explained by who was sampled."] if brief.context_notes else []
    )

    if not brief.claims:
        return {"level": "low", "reasons": ["No finding you can read supports an answer."]}
    if brief.unresolved_conflicts:
        return {"level": "low", "reasons": [
            "Studies of the same population and period disagree; an analyst has been asked to review."]}
    if not any(not s.is_qual for s in cited):
        return {"level": "low", "reasons": ["Qualitative evidence only; it cannot show how widespread a view is."]}

    tiers = {s.effective_tier for s in supporting}
    codes = sorted({s.study_code for s in supporting if s.effective_tier == "A"})
    if "A" in tiers:
        return {"level": "high", "reasons": [f"Supported by Tier A evidence ({', '.join(codes)})."] + context_reason}
    if "B" in tiers:
        return {"level": "medium", "reasons": ["The best supporting evidence is Tier B."] + context_reason}
    if supporting:
        return {"level": "low", "reasons": ["The best supporting evidence is Tier C."] + context_reason}
    return {"level": "medium", "reasons": ["The evidence gives context rather than direct support."] + context_reason}
