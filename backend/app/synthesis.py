"""Evidence brief pipeline.

1. Retrieve approved findings the user may read (RLS), reranked by robustness tier.
2. Classify divergences in code (context difference or unresolved conflict).
3. Ask the LLM to write the brief from those fixed inputs.
4. Validate; regenerate once with the problems listed; drop claims that still fail.
5. Compute confidence and build charts from database values.
6. Store the brief, route unresolved conflicts to an analyst and write the audit log.

Restricted findings never reach the LLM: the only content passed to it is what step 1 returned.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from psycopg.types.json import Jsonb

from . import audit, charts, divergence, retrieval
from .auth import CurrentUser
from .confidence import compute_confidence
from .db import Database
from .describe import compute_gaps, source_view, topic_label
from .embeddings import Embedder
from .llm_types import LLM, BriefRequest, LLMError, PromptGroup
from .retrieval import Source
from .schemas import Claim, EvidenceBrief
from .validators import (
    NO_AB_QUANT_MESSAGE,
    NO_QUANT_MESSAGE,
    QUAL_DISCLAIMER,
    finalize,
    is_ab_quant,
    is_qual_only,
    validate_brief,
)

ESCALATION_NOTE = "Routed automatically: the brief contains an unresolved conflict between studies."


def _map_ids(brief: EvidenceBrief, mapping: dict[str, str]) -> EvidenceBrief:
    """Replace prompt refs (F1, F2, ...) with finding ids. Unknown refs are left as they are, so the
    citation-ID validator rejects them."""
    def m(x: str) -> str:
        return mapping.get(x.strip(), x)

    data = brief.model_dump()
    for claim in data["claims"]:
        claim["evidence"] = [{**e, "finding_id": m(e["finding_id"])} for e in claim["evidence"]]
        claim["verbatim_ids"] = [m(v) for v in claim["verbatim_ids"]]
    for key in ("context_notes", "unresolved_conflicts"):
        for note in data[key]:
            note["finding_ids"] = [m(i) for i in note["finding_ids"]]
    return EvidenceBrief.model_validate(data)


class BriefService:
    def __init__(self, db: Database, llm: LLM, embedder: Embedder, fallback_llm: LLM,
                 today: Callable[[], date] = date.today):
        self.db = db
        self.llm = llm
        self.embedder = embedder
        self.fallback_llm = fallback_llm
        self.today = today

    def ask(self, user: CurrentUser, question: str) -> dict:
        question = question.strip()
        vector = self.embedder.embed(question)
        with self.db.as_user(user.id, user.email) as conn:
            sources = retrieval.search(conn, question, self.embedder, query_embedding=vector)
            sources = retrieval.attach_verbatims(conn, sources)
            restricted = retrieval.restricted_matches(conn, vector)
            points = charts.load_points(conn, {
                s.metric_key for s in sources if s.finding_type == "quant_stat" and s.is_quant and s.metric_key
            })

        by_id = {s.finding_id: s for s in sources}
        groups = divergence.analyze([s.ctx() for s in sources if s.finding_type != "verbatim"])
        available_charts = {key: charts.build_chart(key, rows) for key, rows in points.items()}
        chartable = [key for key, spec in available_charts.items() if spec]
        computed_gaps = compute_gaps(sources, self.today())

        generated_by, dropped, regenerated, llm_note = None, [], False, None
        if sources:
            brief, generated_by, dropped, regenerated, llm_note = self._write(
                question, sources, groups, chartable, computed_gaps)
        else:
            brief = EvidenceBrief(claims=[], context_notes=[], unresolved_conflicts=[], chart_requests=[],
                                  gaps=["No approved study you can read covers this question."])
        if not brief.gaps:
            brief.gaps = computed_gaps

        no_headline_message = None
        if not any(c.kind == "headline" for c in brief.claims) and sources:
            if not any(is_ab_quant(s) for s in sources):
                no_headline_message = NO_QUANT_MESSAGE if not any(s.is_quant for s in sources) else NO_AB_QUANT_MESSAGE
        qual_only = [is_qual_only(c, by_id) for c in brief.claims]

        chart_keys = brief.chart_requests or self._default_chart_keys(brief.claims, by_id, chartable)
        chart_specs = [available_charts[k] for k in chart_keys if available_charts.get(k)]
        confidence = compute_confidence(brief, by_id)

        cited = {e.finding_id for c in brief.claims for e in c.evidence} | {
            v for c in brief.claims for v in c.verbatim_ids} | {
            i for n in brief.context_notes + brief.unresolved_conflicts for i in n.finding_ids}
        payload = {
            "question": question,
            "generated_by": generated_by,
            "generator_note": llm_note,
            "no_headline_message": no_headline_message,
            "disclaimer": QUAL_DISCLAIMER if any(qual_only) else None,
            "claims": [{**c.model_dump(), "qual_only": q} for c, q in zip(brief.claims, qual_only)],
            "context_notes": [n.model_dump() for n in brief.context_notes],
            "unresolved_conflicts": [n.model_dump() for n in brief.unresolved_conflicts],
            "topic_labels": {n.topic: topic_label(n.topic) for n in brief.context_notes + brief.unresolved_conflicts},
            "chart_requests": brief.chart_requests,
            "gaps": brief.gaps,
            "charts": chart_specs,
            "confidence": confidence,
            "sources": {fid: source_view(by_id[fid]) for fid in cited if fid in by_id},
            "restricted_matches": restricted,
            "dropped_claims": len(dropped),
            "regenerated": regenerated,
        }

        with self.db.as_user(user.id, user.email) as conn:
            row = conn.execute(
                "insert into public.briefs (user_id, question, payload, confidence, retrieved_finding_ids, model) "
                "values (%s, %s, %s, %s, %s::uuid[], %s) returning id::text as id, created_at",
                [user.id, question, Jsonb(payload), confidence["level"], [s.finding_id for s in sources], generated_by],
            ).fetchone()
            escalation = None
            if brief.unresolved_conflicts:
                escalation = conn.execute(
                    "insert into public.escalations (brief_id, requested_by, reason, note) "
                    "values (%s, %s, 'unresolved_conflict', %s) returning id::text as id, status, reason",
                    [row["id"], user.id, ESCALATION_NOTE],
                ).fetchone()
                audit.log(conn, "escalation.created", "escalation", escalation["id"],
                          {"brief_id": row["id"], "reason": "unresolved_conflict", "automatic": True})
            audit.log(conn, "brief.generated", "brief", row["id"], {
                "question": question,
                "retrieved": len(sources),
                "cited": len(cited),
                "confidence": confidence["level"],
                "model": generated_by,
                "regenerated": regenerated,
                "dropped_claims": [d["reasons"] for d in dropped],
                "restricted_matches": [r["study_id"] for r in restricted],
            })

        return {**payload, "id": row["id"], "created_at": row["created_at"].isoformat(), "escalation": escalation}

    def _write(self, question: str, sources: list[Source], groups: list[divergence.DivergenceGroup],
               chartable: list[str], computed_gaps: list[str]):
        refs = {s.finding_id: f"F{i}" for i, s in enumerate(sources, 1)}
        ids = {ref: fid for fid, ref in refs.items()}
        by_id = {s.finding_id: s for s in sources}
        request = BriefRequest(
            question=question,
            findings=[(refs[s.finding_id], s) for s in sources],
            groups=[
                PromptGroup(g.kind, g.topic, [refs[i] for i in g.finding_ids], list(g.differs_by),
                            [(refs[p.a], refs[p.b], list(p.differs_by)) for p in g.pairs])
                for g in groups
            ],
            chartable=chartable,
            computed_gaps=computed_gaps,
        )
        writer, note = self.llm, None
        try:
            draft = _map_ids(writer.write_brief(request), ids)
        except LLMError as exc:
            writer, note = self.fallback_llm, f"{self.llm.name} unavailable ({exc}); written from templates."
            draft = _map_ids(writer.write_brief(request), ids)

        def show(fid: str) -> str:
            return refs.get(fid, fid)

        issues = validate_brief(draft, by_id, groups, show_id=show)
        regenerated = False
        if issues:
            regenerated = True
            try:
                draft = _map_ids(writer.write_brief(request, feedback=[i.message for i in issues]), ids)
            except LLMError:
                pass  # keep the first draft; claims that fail are dropped below
            issues = validate_brief(draft, by_id, groups, show_id=show)
        final, dropped = finalize(draft, issues, by_id, groups, chartable)
        return final, writer.name, dropped, regenerated, note

    @staticmethod
    def _default_chart_keys(claims: list[Claim], by_id: dict[str, Source], chartable: list[str]) -> list[str]:
        """Charts for the quant metrics the brief cites, when the writer asked for none."""
        cited = [by_id[e.finding_id].metric_key for c in claims if c.kind != "qualitative_insight"
                 for e in c.evidence if e.finding_id in by_id]
        return [k for k in dict.fromkeys(cited) if k in chartable][:3]
