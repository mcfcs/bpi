"""LLM clients.

ClaudeLLM calls Claude with structured output (Pydantic schemas from app/schemas.py), through the
Claude API or Claude in Amazon Bedrock (LLM_PROVIDER=bedrock). OfflineLLM is
deterministic: it writes claims from the reviewed finding texts and the code-computed divergences,
for tests and for demos without Claude credentials. Both go through the same validators.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import geography, offline_extract
from .config import Settings, metric_label
from . import topicality
from .describe import (
    contrast_sentence,
    explain_group,
    fieldwork_label,
    fmt_value,
    join_words,
    method_short,
    qual_place,
    subgroup_label,
    synthesize_themes,
    who_short,
)
from .divergence import DivergenceGroup, parse_age_band
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
from .validators import QUAL_FORBIDDEN, has_hedge, in_question_area

T = TypeVar("T", bound=BaseModel)


class ClaudeLLM:
    """Claude through the Claude API or Claude in Amazon Bedrock. Both serve the same Messages API, so
    one code path (structured output, effort, prompt caching) runs on either; only the client and
    server-side fallback differ (platform="anthropic" or "bedrock")."""

    def __init__(self, model: str, effort: str, client=None, platform: str = "anthropic"):
        import anthropic

        self._anthropic = anthropic
        # A brief is a draft plus at most one regeneration, behind the frontend's 300 s proxy
        # timeout: bound each call and retry once.
        self.client = client or anthropic.Anthropic(timeout=120.0, max_retries=1)
        self.model = model
        self.effort = effort
        self.name = model
        self.platform = platform
        self._service = "Bedrock" if platform == "bedrock" else "The Claude API"

    def _parse(self, system: str, content: str | list[dict], schema: type[T]) -> T:
        anthropic = self._anthropic
        # Server-side fallback re-runs a declined request on Anthropic's recommended fallback model
        # inside the same call. Bedrock doesn't offer it: a refusal there becomes an LLMError and the
        # brief is written from templates.
        fallback = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                    if self.platform == "anthropic" else {})
        service = self._service
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": self.effort},
                **fallback,
            )
        except anthropic.RateLimitError as exc:
            raise LLMError(f"{service} rate limit was reached; try again shortly.") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMError(f"{service} took too long to answer.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"{service} error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Could not reach {'Bedrock' if self.platform == 'bedrock' else 'the Claude API'}.") from exc
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
    """Who a figure describes, e.g. "NCR, ages 20–40" (the subgroup where the figure is for one);
    code, year and n are in the citation badge."""
    from .geography import describe

    age_min, age_max, regions, _ = s.population_view()
    parts = [describe(regions)]
    if age_min is not None and age_max is not None:
        parts.append(f"ages {age_min}–{age_max}" if age_max < 99 else f"ages {age_min}+")
    return ", ".join(parts)


def _subgroup_order(subgroup: dict | None) -> tuple:
    sub = subgroup or {}
    lo, _ = parse_age_band(sub.get("age_band"))
    return (lo if lo is not None else 999, sub.get("region") or "", sub.get("segment") or "")


def _base(s: Source) -> str:
    n = s.base_n or s.sample_size
    return f"n={n:,}" if n else "n not stated"


def _with_details(text: str, details: str) -> str:
    """Append study details to a finding sentence, merging into a closing parenthesis if present."""
    text = _sentence(text)
    if text.endswith(")."):
        return text[:-2] + f"; {details})."
    return text[:-1] + f" ({details})."


def _disputed_text(metric_key: str, members: list[Source]) -> str:
    """An unresolved conflict stated as what each study found, never as one answer."""
    return (f"{metric_label(metric_key)}: " + "; ".join(
        f"{m.study_code} found {fmt_value(m.value, m.unit)} among {who_short(m)} ({method_short(m)}, {fieldwork_label(m)})"
        for m in members) + ". An S&I analyst is checking why the results differ before either is used.")


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

        # Headline: the Tier A/B figure that best matches the question's own concept ("Are fees a
        # barrier?" leads with fees), then the most relevant study and its largest figure. It always
        # carries who it describes. When its metric is in an unresolved conflict, the headline says
        # what each study found instead of presenting one figure as the answer.
        by_ref = dict(request.findings)
        focus = topicality.specific_terms(request.question)
        conflicts = {g.topic: g for g in request.groups if g.kind == "unresolved_conflict"}
        area = geography.question_area(request.question)
        in_place = [(r, s) for r, s in ab_quant if area and in_question_area(s, area)]
        if ab_quant:
            # A question about a place ("outside Metro Manila") leads with that place's figures.
            totals = in_place or [(r, s) for r, s in ab_quant if not s.subgroup] or ab_quant
            matching = [(r, s) for r, s in totals if focus & topicality.finding_terms(s)]
            candidates = sorted(matching or totals, key=lambda rs: rs[1].effective_tier or "C")   # stable: keeps rank order
            lead_study = candidates[0][1].study_id
            pool = [(r, s) for r, s in candidates if s.study_id == lead_study]
            ref, lead = max(pool, key=lambda rs: (rs[1].unit == "%", float(rs[1].value)))
            if lead.metric_key in conflicts:
                members = [(r, by_ref[r]) for r in conflicts[lead.metric_key].refs]
                text = _disputed_text(lead.metric_key, [m for _, m in members])
                refs = [r for r, _ in members]
            else:
                agreeing = [
                    (r, s) for r, s in ab_quant
                    if s.study_id != lead.study_id and s.metric_key == lead.metric_key and not s.subgroup
                    and s.resolved_direction() == lead.resolved_direction()
                ]
                text = _with_details(lead.text, _population_phrase(lead))
                for _, s in agreeing:
                    text += f" {s.study_code} ({_short_population(s)}) reports {fmt_value(s.value, s.unit)} on the same measure."
                # The other figures for the asked-for place on the same measure ("In Visayas, 19% ...").
                same_place = [(r, s) for r, s in pool if in_place and r != ref and s.metric_key == lead.metric_key]
                for _, s in sorted(same_place, key=lambda rs: -float(rs[1].value)):
                    text += " " + _sentence(s.text)
                refs = [ref] + [r for r, _ in agreeing] + [r for r, _ in same_place]
            claims.append(Claim(text=text, kind="headline",
                                evidence=[Evidence(finding_id=r, stance="supports") for r in refs]))
            used.update(refs)

        # Breakdowns: subgroup splits first, then figures involved in divergences, then the rest.
        breakdowns = 0
        by_split: dict[tuple, list[tuple[str, Source]]] = {}
        for ref, s in quant:
            if ref not in used and s.subgroup:
                by_split.setdefault((s.study_id, s.metric_key), []).append((ref, s))
        splits = sorted(by_split.values(),
                        key=lambda rows: not (request.reader and request.reader.owns(rows[0][1])))
        for rows in splits:
            if len(rows) < 2 or breakdowns >= self.MAX_BREAKDOWNS:
                continue
            rows = sorted(rows, key=lambda rs: _subgroup_order(rs[1].subgroup))   # ages ascending, then place
            first = rows[0][1]
            parts = "; ".join(f"{subgroup_label(s.subgroup)}: {fmt_value(s.value, s.unit)} ({_base(s)})" for _, s in rows)
            claims.append(Claim(
                text=f"{metric_label(first.metric_key)} by subgroup in {first.study_code} ({_short_population(first)}): {parts}.",
                kind="breakdown", evidence=[Evidence(finding_id=r, stance="supports") for r, _ in rows],
            ))
            used.update(r for r, _ in rows)
            breakdowns += 1
        # A disputed figure the headline doesn't cover: one breakdown with what each study found.
        for topic, group in conflicts.items():
            if breakdowns >= self.MAX_BREAKDOWNS or set(group.refs) & used:
                continue
            members = [by_ref[r] for r in group.refs]
            claims.append(Claim(text=_disputed_text(topic, members), kind="breakdown",
                                evidence=[Evidence(finding_id=r, stance="supports") for r in group.refs]))
            used.update(group.refs)
            breakdowns += 1
        # Figures that take part in a divergence come first (the reader needs them to follow the
        # context notes), then the largest remaining figures, skipping the headline's own metric.
        in_groups = {ref for g in request.groups for ref in g.refs}
        headline_metrics = {s.metric_key for r, s in quant if r in used}
        reader = request.reader
        ordered = sorted(
            (x for x in quant if x[0] not in used and not x[1].subgroup
             and (x[0] in in_groups or x[1].metric_key not in headline_metrics)),
            key=lambda rs: (rs[0] not in in_groups, not (reader and reader.owns(rs[1])), -float(rs[1].value)),
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

        # What people say: qualitative support, newest fieldwork first (S&I weigh qualitative evidence
        # by recency). A synthesis of themes across groups comes first; themes that run against a
        # survey result come last, as colour with their population, never as a divergence.
        by_id = {s.finding_id: s for s in by_ref.values()}
        contrasts = {c.qual_ref: c for c in request.qual_contrasts}
        themes = sorted(
            [(ref, s) for ref, s in request.findings if s.finding_type == "qual_theme" and ref not in used],
            key=lambda rs: (rs[0] in contrasts, -(rs[1].fieldwork_end.toordinal() if rs[1].fieldwork_end else 0)),
        )
        themes = [(ref, s) for ref, s in themes if not (s.is_qual and QUAL_FORBIDDEN.search(s.text))]

        def verbatims_for(s: Source) -> list[str]:
            return [
                vref for vref, v in request.findings
                if v.finding_type == "verbatim" and v.study_id == s.study_id
                and ((s.metric_key and v.metric_key == s.metric_key) or (not s.metric_key and v.theme == s.theme))
            ][:2]

        supporting = [(r, s) for r, s in themes if r not in contrasts and s.is_qual]
        synthesis = synthesize_themes([s for _, s in supporting],
                                      [by_ref[v] for _, s in supporting for v in verbatims_for(s)])
        if synthesis:
            claims.append(Claim(text=synthesis, kind="qualitative_insight",
                                evidence=[Evidence(finding_id=r, stance="supports") for r, _ in supporting]))
        for ref, s in themes:
            text = _sentence(s.text)
            if s.is_qual and not has_hedge(text):
                text += f" Indicatively, this view comes from participants {qual_place(s)}."
            stance = "supports"
            if ref in contrasts:
                text += " " + contrast_sentence(s, [by_ref[r] for r in contrasts[ref].quant_refs])
                stance = "context"
            claims.append(Claim(text=text, kind="qualitative_insight",
                                evidence=[Evidence(finding_id=ref, stance=stance)], verbatim_ids=verbatims_for(s)))
            used.add(ref)

        # Divergences: classification and differs_by come from code; only the wording is written here.
        notes: dict[str, list[ContextNote]] = {"context_difference": [], "unresolved_conflict": [], "within_study": []}
        for g in request.groups:
            group = DivergenceGroup(g.kind, g.topic, [by_ref[r].finding_id for r in g.refs], list(g.differs_by))
            notes[g.kind].append(ContextNote(topic=g.topic, finding_ids=list(g.refs), differs_by=list(g.differs_by),
                                             explanation=explain_group(group, by_id)))

        cited_metrics = [
            by_ref[e.finding_id].metric_key for c in claims if c.kind != "qualitative_insight"
            for e in c.evidence if e.finding_id in by_ref
        ]
        charts = [k for k in dict.fromkeys(cited_metrics) if k in request.chartable][:3]
        # Audience summaries are left to the validator's finalize step, which builds them from the
        # claims that survive validation (describe.build_summaries).
        return EvidenceBrief(claims=claims, context_notes=notes["context_difference"],
                             unresolved_conflicts=notes["unresolved_conflict"], study_patterns=notes["within_study"],
                             chart_requests=charts, gaps=list(request.computed_gaps))

    def extract_study_card(self, report_text: str, known_metric_keys: list[str]) -> StudyCardExtraction:
        return offline_extract.extract(report_text)

    def write_scope(self, title: str, objectives: list[dict]) -> str:
        def q(o: dict) -> str:
            return f"\u201c{o['text'].strip()}\u201d"

        def caveated(o: dict) -> bool:
            return any(c["code"] == "conflict" for c in o.get("caveats") or [])

        gaps = [o for o in objectives if o["coverage"] == "gap"]
        stale = [o for o in objectives if o["coverage"] == "covered_stale"]
        partial = [o for o in objectives if o["coverage"] == "partial"]
        checking = [o for o in objectives if o["coverage"] == "covered" and caveated(o)]
        covered = [o for o in objectives if o["coverage"] == "covered" and not caveated(o)]
        restricted = [o for o in objectives if any(c["code"] == "restricted_match" for c in o.get("caveats") or [])]
        sentences = []
        if gaps:
            sentences.append(f"New research is needed for {join_words(q(o) for o in gaps)}: no approved study covers "
                             f"{'it' if len(gaps) == 1 else 'them'} yet.")
        if stale:
            sentences.append("Refresh older evidence for " + join_words(
                f"{q(o)} ({o['evidence_summary']})" for o in stale) + ".")
        if partial:
            sentences.append("Extend the existing evidence for " + join_words(
                f"{q(o)} ({o['evidence_summary']})" for o in partial) + ".")
        if checking:
            sentences.append(f"Approved studies cover {join_words(q(o) for o in checking)}, but they report different "
                             f"results for the same group; ask an S&I analyst which to rely on before reusing them.")
        if covered:
            sentences.append(f"Approved studies already cover {join_words(q(o) for o in covered)}; reuse them rather "
                             f"than asking again.")
        if restricted:
            sentences.append(f"A restricted study may also cover {join_words(q(o) for o in restricted)}; request access "
                             f"before commissioning.")
        if not gaps and not partial and not stale and not checking:
            sentences.append("No new fieldwork appears necessary; confirm with S&I before commissioning.")
        return " ".join(sentences)


def bedrock_client(region: str):
    """Claude on Amazon Bedrock through the bedrock-runtime endpoint, signed with the AWS credential
    chain (AWS_PROFILE or access keys). It takes the Messages API body, so structured output, effort
    and prompt caching work as on the Claude API.

    Not the newer bedrock-mantle endpoint: in ap-southeast-1 (checked 14 Nov 2026) it answers "model
    does not exist" for Opus 5.5 and Sonnet 5.5, which Singapore serves only through global
    inference profiles (`global.anthropic.claude-opus-5-5`) on bedrock-runtime. A global profile can
    route a request to any AWS region. Same timeout and retry budget as the Claude API client."""
    from anthropic import AnthropicBedrock

    return AnthropicBedrock(aws_region=region, timeout=120.0, max_retries=1)


def writer_ready(llm) -> tuple[bool, str | None]:
    """Whether the brief writer can be reached now, without a billed call. An expired AWS sign-in or a
    dropped connection makes every brief fall back to templates, which a reader only notices in the
    small "drafted by" line, so the ask page warns before anyone asks. Bedrock: the AWS credentials
    (STS, free); Claude API: the models list (free)."""
    platform = getattr(llm, "platform", None)
    try:
        if platform == "bedrock":
            import boto3

            boto3.client("sts").get_caller_identity()
        elif platform == "anthropic":
            llm.client.models.list(limit=1)
        return True, None
    except Exception as exc:   # noqa: BLE001 - any failure means briefs will come from templates
        logging.getLogger(__name__).warning("Brief writer not reachable: %s", exc)
        if platform == "bedrock":
            return False, "The AWS sign-in has expired or the network is down (run aws sso login)."
        return False, "The Claude API cannot be reached."


def build_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "anthropic":
        return ClaudeLLM(settings.llm_model, settings.llm_effort)
    if settings.llm_provider == "bedrock":
        return ClaudeLLM(settings.aws_bedrock_model, settings.llm_effort,
                         client=bedrock_client(settings.aws_region), platform="bedrock")
    return OfflineLLM()
