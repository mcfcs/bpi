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

from . import audit, charts, divergence, governance, retrieval, topicality
from .auth import CurrentUser
from .confidence import compute_confidence
from .config import ROLE_LABELS, TEAM_METRIC_FOCUS, retrieval_config, topicality_config
from .db import Database
from .describe import compute_gap_items, emotions_for, qual_contrasts, source_view, topic_label
from .embeddings import Embedder
from .llm_types import LLM, BriefRequest, LLMError, PromptGroup, QualContrast, Reader
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

NO_SOURCES_MESSAGE = ("No approved study you can read answers this. Try describing it another way, "
                      "or ask an analyst whether S&I has covered it.")
ESCALATION_NOTE ="Routed automatically: the brief contains an unresolved conflict between studies."


def _map_ids(brief: EvidenceBrief, mapping: dict[str, str]) -> EvidenceBrief:
    """Replace prompt refs (F1, F2, ...) with finding ids. Unknown refs are left as they are, so the
    citation-ID validator rejects them."""
    def m(x: str) -> str:
        return mapping.get(x.strip(), x)

    data = brief.model_dump()
    for claim in data["claims"]:
        claim["evidence"] = [{**e, "finding_id": m(e["finding_id"])} for e in claim["evidence"]]
        claim["verbatim_ids"] = [m(v) for v in claim["verbatim_ids"]]
    for key in ("context_notes", "unresolved_conflicts", "study_patterns"):
        for note in data[key]:
            note["finding_ids"] = [m(i) for i in note["finding_ids"]]
    for summary in data["summaries"]:
        summary["finding_ids"] = [m(i) for i in summary["finding_ids"]]
    return EvidenceBrief.model_validate(data)


def build_reader(user: CurrentUser, sources: list[Source], role_note: str | None = None) -> Reader:
    """Who the brief is for. Built from the signed-in profile; the optional role note only changes
    how relevance is framed. Team studies are listed from what was retrieved under RLS, so the
    reader never learns about a study they cannot read."""
    role_label = " ".join((role_note or "").split())[:80] or ROLE_LABELS.get(user.role, user.role)
    codes = tuple(dict.fromkeys(s.study_code for s in sources if s.owner_team == user.team_name))
    return Reader(name=user.display_name, team=user.team_name, role=user.role, role_label=role_label,
                  focus_prefixes=TEAM_METRIC_FOCUS.get(user.team_name, ()), team_study_codes=codes)


def prepared_for(reader: Reader, sources: list[Source], cited: set[str]) -> dict:
    """Who the brief is prepared for and how relevance was framed for their team."""
    owned = [s for s in sources if s.finding_id in cited and reader.owns(s) and s.finding_type != "verbatim"]
    labels = list(dict.fromkeys(topic_label(s.topic) for s in owned if s.topic and s.metric_key))
    note = f"Prepared for {reader.name}, {reader.team} ({reader.role_label})."
    if labels:
        note += f" Figures your team owns are listed first: {', '.join(labels[:4])}."
    if reader.team_study_codes:
        note += f" Studies your team owns in this brief: {', '.join(reader.team_study_codes)}."
    return {"name": reader.name, "team": reader.team, "role": reader.role, "role_label": reader.role_label,
            "focus_metrics": list(dict.fromkeys(s.metric_key for s in owned if s.metric_key)),
            "team_study_codes": list(reader.team_study_codes), "note": note}


class BriefService:
    def __init__(self, db: Database, llm: LLM, embedder: Embedder, fallback_llm: LLM,
                 today: Callable[[], date] = date.today):
        self.db = db
        self.llm = llm
        self.embedder = embedder
        self.fallback_llm = fallback_llm
        self.today = today

    def ask(self, user: CurrentUser, question: str, reader_role: str | None = None) -> dict:
        question = question.strip()
        vector = self.embedder.embed_query(question)
        junk = topicality.is_junk(question)
        focus = topicality.specific_terms(question)
        with self.db.as_user(user.id, user.email) as conn:
            sources, restricted = [], []
            if not junk:
                sources = retrieval.search(conn, question, self.embedder, query_embedding=vector)
                if focus and topicality_config(self.embedder.name)["filter_off_topic"]:
                    # Lexical search: findings that share only generic words ("SME", "loan") are false hits.
                    sources = [s for s in sources if topicality.overlap(question, s)]
                sources = retrieval.attach_verbatims(conn, sources)
                if sources or not focus or not topicality_config(self.embedder.name)["filter_off_topic"]:
                    restricted = retrieval.restricted_matches(conn, vector, retrieval_config(self.embedder.name))
            points = charts.load_points(conn, {
                s.metric_key for s in sources if s.finding_type == "quant_stat" and s.is_quant and s.metric_key
            })

        by_id = {s.finding_id: s for s in sources}
        groups = divergence.analyze([s.ctx() for s in sources if s.finding_type != "verbatim"])
        available_charts = {key: charts.build_chart(key, rows) for key, rows in points.items()}
        chartable = [key for key, spec in available_charts.items() if spec]
        gap_items = compute_gap_items(sources, self.today())
        computed_gaps = [g["text"] for g in gap_items]
        reader = build_reader(user, sources, reader_role)
        contrasts = qual_contrasts(sources)

        generated_by, dropped, regenerated, llm_note = None, [], False, None
        if sources:
            brief, generated_by, dropped, regenerated, llm_note = self._write(
                question, sources, groups, chartable, computed_gaps, reader, contrasts)
        else:
            brief = EvidenceBrief(claims=[], context_notes=[], unresolved_conflicts=[], chart_requests=[],
                                  gaps=["No approved study you can read covers this question."])
        if not brief.gaps:
            brief.gaps = computed_gaps

        no_headline_message = None
        if not sources:
            no_headline_message = NO_SOURCES_MESSAGE
        elif not any(c.kind == "headline" for c in brief.claims):
            if not any(is_ab_quant(s) for s in sources):
                no_headline_message = NO_QUANT_MESSAGE if not any(s.is_quant for s in sources) else NO_AB_QUANT_MESSAGE
        qual_only = [is_qual_only(c, by_id) for c in brief.claims]

        notes = brief.context_notes + brief.unresolved_conflicts + brief.study_patterns
        cited = {e.finding_id for c in brief.claims for e in c.evidence} | {
            v for c in brief.claims for v in c.verbatim_ids} | {
            i for n in notes for i in n.finding_ids} | {i for s in brief.summaries for i in s.finding_ids}

        # Charts show only studies the brief cites, so every bar is explained by a claim or note.
        chart_keys = brief.chart_requests or self._default_chart_keys(brief.claims, by_id, chartable)
        cited_studies = {by_id[i].study_id for i in cited if i in by_id}
        chart_specs = [spec for k in chart_keys
                       if (spec := charts.build_chart(k, [r for r in points.get(k, []) if r["study_id"] in cited_studies]))]
        cited_findings = [by_id[i] for i in cited if i in by_id and by_id[i].finding_type != "verbatim"]
        unmatched = sorted(focus) if focus and cited_findings and not any(
            topicality.overlap(question, s) for s in cited_findings) else []
        confidence = compute_confidence(brief, by_id, restricted_matches=len(restricted), unmatched_terms=unmatched)

        def claim_emotions(claim) -> list[dict]:
            if claim.kind != "qualitative_insight":
                return []
            ids = [e.finding_id for e in claim.evidence] + list(claim.verbatim_ids)
            return emotions_for(by_id[i].text for i in ids if i in by_id)
        payload = {
            "question": question,
            "generated_by": generated_by,
            "generator_note": llm_note,
            "no_headline_message": no_headline_message,
            "disclaimer": QUAL_DISCLAIMER if any(qual_only) else None,
            "claims": [{**c.model_dump(), "qual_only": q, "emotions": claim_emotions(c)}
                       for c, q in zip(brief.claims, qual_only)],
            "context_notes": [n.model_dump() for n in brief.context_notes],
            "unresolved_conflicts": [n.model_dump() for n in brief.unresolved_conflicts],
            "study_patterns": [n.model_dump() for n in brief.study_patterns],
            "topic_labels": {n.topic: topic_label(n.topic) for n in notes},
            "summaries": {s.audience: {"text": s.text, "finding_ids": s.finding_ids} for s in brief.summaries},
            "prepared_for": prepared_for(reader, sources, cited),
            "qual_contrasts": [c for c in contrasts if c["finding_id"] in cited],
            "chart_requests": brief.chart_requests,
            "gaps": brief.gaps,
            "gap_items": [g for g in gap_items if g["text"] in brief.gaps],
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
            # Route unresolved conflicts to an analyst once per conflict while it is open (asking
            # again links to the open escalation), and never route S&I analysts' own briefs to S&I.
            if brief.unresolved_conflicts and not user.is_si:
                keys = governance.conflict_keys(payload["unresolved_conflicts"])
                escalation = governance.open_conflict_escalation(conn, keys)
                if escalation is None:
                    escalation = conn.execute(
                        "insert into public.escalations (brief_id, requested_by, reason, note) "
                        "values (%s, %s, 'unresolved_conflict', %s) returning id::text as id, status, reason",
                        [row["id"], user.id, ESCALATION_NOTE],
                    ).fetchone()
                    audit.log(conn, "escalation.created", "escalation", escalation["id"],
                              {"brief_id": row["id"], "reason": "unresolved_conflict", "automatic": True,
                               "conflicts": [list(k) for k in sorted(keys)]})
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
               chartable: list[str], computed_gaps: list[str], reader: Reader | None = None,
               contrasts: list[dict] | None = None):
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
            reader=reader,
            qual_contrasts=[QualContrast(refs[c["finding_id"]], [refs[i] for i in c["quant_finding_ids"]], c["topic"])
                            for c in contrasts or []],
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
