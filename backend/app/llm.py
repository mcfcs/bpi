"""LLM clients.

ClaudeLLM calls Claude with structured output (Pydantic schemas from app/schemas.py). OfflineLLM is
deterministic: it writes claims from the reviewed finding texts and the code-computed divergences,
for tests and for demos without Claude credentials. Both go through the same validators.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import offline_extract
from .config import Settings, metric_label
from .describe import explain_group, fmt_value, subgroup_label, join_words
from .divergence import DivergenceGroup
from .llm_types import LLM, BriefRequest, LLMError
from .prompts import (
    BRIEF_SYSTEM,
    EXTRACT_SYSTEM,
    SCOPE_SYSTEM,
    render_brief_prompt,
    render_extract_prompt,
    render_feedback,
    render_scope_prompt,
)
from .retrieval import Source
from .schemas import Claim, ContextNote, EvidenceBrief, Evidence, ScopeDraft, StudyCardExtraction
from .validators import QUAL_FORBIDDEN, has_hedge

T = TypeVar("T", bound=BaseModel)


class ClaudeLLM:
    def __init__(self, model: str, effort: str, client=None):
        import anthropic

        self._anthropic = anthropic
        # A brief is a draft plus at most one regeneration, behind the frontend's 300 s proxy
        # timeout: bound each call and retry once.
        self.client = client or anthropic.Anthropic(timeout=120.0, max_retries=1)
        self.model = model
        self.effort = effort
        self.name = model

    def _parse(self, system: str, content: str | list[dict], schema: type[T]) -> T:
        anthropic = self._anthropic
        try:
            # Server-side fallback re-runs a declined request on Anthropic's recommended fallback
            # model inside the same call.
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise LLMError("The Claude API rate limit was reached; try again shortly.") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMError("The Claude API took too long to answer.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Claude API.") from exc
        except ValidationError as exc:
            raise LLMError(f"The model's output did not match the schema: {exc.error_count()} errors.") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model's answer was cut off.")
        if response.parsed_output is None:
            raise LLMError("The model returned no structured output.")
        return response.parsed_output

    def write_brief(self, request: BriefRequest, feedback: list[str] | None = None) -> EvidenceBrief:
        # The findings block is marked for caching: a regeneration after failed checks resends the
        # same system prompt and findings with the problems appended, so it is mostly a cache read.
        content = [{"type": "text", "text": render_brief_prompt(request), "cache_control": {"type": "ephemeral"}}]
        if feedback:
            content.append({"type": "text", "text": render_feedback(feedback)})
        return self._parse(BRIEF_SYSTEM, content, EvidenceBrief)

    def extract_study_card(self, report_text: str, known_metric_keys: list[str]) -> StudyCardExtraction:
        return self._parse(EXTRACT_SYSTEM, render_extract_prompt(report_text, known_metric_keys), StudyCardExtraction)

    def write_scope(self, title: str, objectives: list[dict]) -> str:
        return self._parse(SCOPE_SYSTEM, render_scope_prompt(title, objectives), ScopeDraft).recommended_new_scope


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _lower_first(text: str) -> str:
    first = text.split()[0] if text.split() else ""
    return text if first.isupper() or first[:2].isupper() else text[:1].lower() + text[1:]


def _short_population(s: Source) -> str:
    from .geography import describe

    pop = s.population or {}
    parts = [describe(pop.get("regions"))]
    if pop.get("age_min") is not None and pop.get("age_max") is not None:
        parts.append(f"ages {pop['age_min']}–{pop['age_max']}")
    if s.fieldwork_end:
        parts.append(str(s.fieldwork_end.year))
    return ", ".join(parts)


def _population_phrase(s: Source) -> str:
    """Who a figure describes, e.g. "NCR, ages 20–40"; code, year and n are in the citation badge."""
    from .geography import describe

    pop = s.population or {}
    parts = [describe(pop.get("regions"))]
    if pop.get("age_min") is not None and pop.get("age_max") is not None:
        parts.append(f"ages {pop['age_min']}–{pop['age_max']}")
    return ", ".join(parts)


def _base(s: Source) -> str:
    n = s.base_n or s.sample_size
    return f"n={n:,}" if n else "n not stated"


def _with_details(text: str, details: str) -> str:
    """Append study details to a finding sentence, merging into a closing parenthesis if present."""
    text = _sentence(text)
    if text.endswith(")."):
        return text[:-2] + f"; {details})."
    return text[:-1] + f" ({details})."


class OfflineLLM:
    name = "offline-template"

    MAX_BREAKDOWNS = 6

    def write_brief(self, request: BriefRequest, feedback: list[str] | None = None) -> EvidenceBrief:
        claims: list[Claim] = []
        used: set[str] = set()
        quant = [
            (ref, s) for ref, s in request.findings
            if s.finding_type == "quant_stat" and s.is_quant and s.value is not None
        ]
        ab_quant = [(ref, s) for ref, s in quant if s.effective_tier in ("A", "B")]

        # Headline: the most relevant Tier A/B study, and its largest reported figure.
        if ab_quant:
            lead_study = ab_quant[0][1].study_id
            pool = [(r, s) for r, s in ab_quant if s.study_id == lead_study and not s.subgroup] or \
                   [(r, s) for r, s in ab_quant if s.study_id == lead_study]
            ref, lead = max(pool, key=lambda rs: (rs[1].unit == "%", float(rs[1].value)))
            agreeing = [
                (r, s) for r, s in ab_quant
                if s.study_id != lead.study_id and s.metric_key == lead.metric_key and not s.subgroup
                and s.resolved_direction() == lead.resolved_direction()
            ]
            text = _sentence(lead.text)
            for _, s in agreeing:
                text += f" {s.study_code} ({_short_population(s)}) reports {fmt_value(s.value, s.unit)} on the same measure."
            claims.append(Claim(
                text=text, kind="headline",
                evidence=[Evidence(finding_id=r, stance="supports") for r in [ref] + [r for r, _ in agreeing]],
            ))
            used.update([ref] + [r for r, _ in agreeing])

        # Breakdowns: subgroup splits first, then figures involved in divergences, then the rest.
        breakdowns = 0
        by_split: dict[tuple, list[tuple[str, Source]]] = {}
        for ref, s in quant:
            if ref not in used and s.subgroup:
                by_split.setdefault((s.study_id, s.metric_key), []).append((ref, s))
        for rows in by_split.values():
            if len(rows) < 2 or breakdowns >= self.MAX_BREAKDOWNS:
                continue
            first = rows[0][1]
            parts = "; ".join(f"{subgroup_label(s.subgroup)}: {fmt_value(s.value, s.unit)} ({_base(s)})" for _, s in rows)
            claims.append(Claim(
                text=f"{metric_label(first.metric_key)} by subgroup in {first.study_code} ({_short_population(first)}): {parts}.",
                kind="breakdown", evidence=[Evidence(finding_id=r, stance="supports") for r, _ in rows],
            ))
            used.update(r for r, _ in rows)
            breakdowns += 1
        # Figures that take part in a divergence come first (the reader needs them to follow the
        # context notes), then the largest remaining figures, skipping the headline's own metric.
        in_groups = {ref for g in request.groups for ref in g.refs}
        headline_metrics = {s.metric_key for r, s in quant if r in used}
        ordered = sorted(
            (x for x in quant if x[0] not in used and not x[1].subgroup
             and (x[0] in in_groups or x[1].metric_key not in headline_metrics)),
            key=lambda rs: (rs[0] not in in_groups, -float(rs[1].value)),
        )
        for ref, s in ordered:
            if breakdowns >= self.MAX_BREAKDOWNS:
                break
            claims.append(Claim(
                text=_with_details(s.text, _population_phrase(s)),
                kind="breakdown", evidence=[Evidence(finding_id=ref, stance="supports")],
            ))
            used.add(ref)
            breakdowns += 1

        # What people say: qualitative themes, hedged, with their verbatims.
        for ref, s in request.findings:
            if s.finding_type != "qual_theme" or ref in used:
                continue
            text = _sentence(s.text)
            if s.is_qual:
                if QUAL_FORBIDDEN.search(text):
                    continue  # cannot be phrased without incidence language; left for the analyst
                if not has_hedge(text):
                    text = "Indicatively, " + _lower_first(text)
            verbatims = [
                vref for vref, v in request.findings
                if v.finding_type == "verbatim" and v.study_id == s.study_id
                and ((s.metric_key and v.metric_key == s.metric_key) or (not s.metric_key and v.theme == s.theme))
            ][:2]
            claims.append(Claim(text=text, kind="qualitative_insight",
                                evidence=[Evidence(finding_id=ref, stance="supports")], verbatim_ids=verbatims))
            used.add(ref)

        # Divergences: classification and differs_by come from code; only the wording is written here.
        by_ref = dict(request.findings)
        by_id = {s.finding_id: s for s in by_ref.values()}
        context_notes, unresolved = [], []
        for g in request.groups:
            group = DivergenceGroup(g.kind, g.topic, [by_ref[r].finding_id for r in g.refs], list(g.differs_by))
            note = ContextNote(topic=g.topic, finding_ids=list(g.refs), differs_by=list(g.differs_by),
                               explanation=explain_group(group, by_id))
            (context_notes if g.kind == "context_difference" else unresolved).append(note)

        cited_metrics = [
            by_ref[e.finding_id].metric_key for c in claims if c.kind != "qualitative_insight"
            for e in c.evidence if e.finding_id in by_ref
        ]
        charts = [k for k in dict.fromkeys(cited_metrics) if k in request.chartable][:3]
        return EvidenceBrief(claims=claims, context_notes=context_notes, unresolved_conflicts=unresolved,
                             chart_requests=charts, gaps=list(request.computed_gaps))

    def extract_study_card(self, report_text: str, known_metric_keys: list[str]) -> StudyCardExtraction:
        return offline_extract.extract(report_text)

    def write_scope(self, title: str, objectives: list[dict]) -> str:
        gaps = [o["text"] for o in objectives if o["coverage"] == "gap"]
        partial = [o for o in objectives if o["coverage"] == "partial"]
        covered = [o["text"] for o in objectives if o["coverage"] == "covered"]
        sentences = []
        if gaps:
            sentences.append(f"New research is needed for: {'; '.join(gaps)}.")
        if partial:
            sentences.append("Extend the existing evidence for: " + "; ".join(
                f"{o['text']} ({o['evidence_summary']})" for o in partial) + ".")
        if covered:
            sentences.append(f"Approved studies already cover {join_words(covered)}; reuse them rather than asking again.")
        if not gaps and not partial:
            sentences.append("No new fieldwork appears necessary; confirm with S&I before commissioning.")
        return " ".join(sentences)


def build_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "anthropic":
        return ClaudeLLM(settings.llm_model, settings.llm_effort)
    return OfflineLLM()
