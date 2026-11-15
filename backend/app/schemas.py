"""Structured-output schemas for the LLM and request bodies for the API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DiffersBy = Literal["age", "region", "segment", "period", "method"]

# ---------------------------------------------------------------------------
# Evidence brief (LLM structured output). In the LLM's output, finding ids are the short refs
# shown in the prompt (F1, F2, ...); the synthesis step maps them back to database ids.
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    finding_id: str
    stance: Literal["supports", "contradicts", "context"]


class Claim(BaseModel):
    text: str
    kind: Literal["headline", "breakdown", "qualitative_insight"]
    evidence: list[Evidence] = Field(min_length=1)
    verbatim_ids: list[str] = []          # finding_type == 'verbatim', qualitative_insight only


class ContextNote(BaseModel):
    topic: str
    finding_ids: list[str]
    differs_by: list[DiffersBy]           # copied from classifier output
    explanation: str


class AudienceSummary(BaseModel):
    """The same facts and citations in a different register. Validated like a claim: cited refs must
    be retrieved, no number may appear that the cited findings don't contain, and a summary that
    rests only on qualitative findings is hedged."""

    audience: Literal["executive", "analyst", "plain"]
    text: str
    finding_ids: list[str]


class EvidenceBrief(BaseModel):
    claims: list[Claim]
    context_notes: list[ContextNote]
    unresolved_conflicts: list[ContextNote]
    chart_requests: list[str]             # metric_keys only; numbers come from the DB, never the LLM
    gaps: list[str]
    study_patterns: list[ContextNote] = []    # within_study groups: two trends in the same study
    summaries: list[AudienceSummary] = []     # executive, analyst, plain


class ScopeDraft(BaseModel):
    recommended_new_scope: str


# ---------------------------------------------------------------------------
# Study-card extraction (LLM structured output at ingestion). The robustness tier is not here:
# it is computed in code from these fields.
# ---------------------------------------------------------------------------


class ExtractedPopulation(BaseModel):
    age_min: int | None
    age_max: int | None
    regions: list[str]
    segment: str | None


class ExtractedSubgroup(BaseModel):
    age_band: str | None
    region: str | None
    segment: str | None


class ExtractedFinding(BaseModel):
    text: str
    finding_type: Literal["quant_stat", "qual_theme", "verbatim"]
    theme: str | None
    metric_key: str | None
    value: float | None
    unit: Literal["%", "rank", "score"] | None
    base_n: int | None
    subgroup: ExtractedSubgroup | None
    direction: Literal["high", "low", "neutral"] | None
    # The report's own words for the finding (sentence, bullet or table row), copied exactly: the
    # finding's page is found by searching the PDF for it. A model's paraphrase in `text` rarely
    # matches the page; the offline extractor's text already is the report's text.
    source_text: str | None = None


class StudyCardExtraction(BaseModel):
    title: str
    summary: str
    method_type: Literal["quant", "qual", "mixed"] | None
    sample_size: int | None
    fieldwork_end: str | None             # YYYY-MM-DD
    population: ExtractedPopulation
    findings: list[ExtractedFinding]


# ---------------------------------------------------------------------------
# API request bodies
# ---------------------------------------------------------------------------


def _has_nul(value) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, (list, tuple)):
        return any(_has_nul(v) for v in value)
    if isinstance(value, dict):
        return any(_has_nul(v) for v in value.values())
    return False


class CleanBody(BaseModel):
    """User-typed text is stripped before length rules apply (so "   a   " is too short), and NUL
    bytes, which Postgres text cannot store, are refused with a 422 instead of a server error."""

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _no_nul(cls, data):
        if _has_nul(data):
            raise ValueError("Text may not contain NUL characters.")
        return data


class AskBody(CleanBody):
    question: str = Field(min_length=5, max_length=500)
    # Optional framing, e.g. "Product manager". Shapes how relevance is framed, never what is visible.
    reader_role: str | None = Field(default=None, max_length=80)


class LoginBody(BaseModel):
    email: str


class Population(BaseModel):
    age_min: int | None = None
    age_max: int | None = None
    regions: list[str] = []
    segment: str | None = None


class StudyPatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    access_level: Literal["open", "restricted"] | None = None
    method_type: Literal["quant", "qual", "mixed"] | None = None
    sample_size: int | None = Field(default=None, gt=0)
    fieldwork_end: date | None = None
    population: Population | None = None
    tier_override: Literal["A", "B", "C"] | None = None
    tier_override_reason: str | None = None
    clear_tier_override: bool = False


class FindingPatch(BaseModel):
    text: str | None = None
    theme: str | None = None
    finding_type: Literal["quant_stat", "qual_theme", "verbatim"] | None = None
    metric_key: str | None = None
    value: float | None = None
    unit: Literal["%", "rank", "score"] | None = None
    base_n: int | None = Field(default=None, gt=0)
    subgroup: dict[str, str] | None = None
    direction: Literal["high", "low", "neutral"] | None = None


class ReviewDecision(BaseModel):
    approve: bool
    note: str | None = None
    # The analyst checked findings the personal-data check flagged (privacy.py) and they identify no one.
    privacy_checked: bool = False


class IngestBody(BaseModel):
    report_text: str = Field(min_length=40)
    owner_team_id: str
    access_level: Literal["open", "restricted"] = "restricted"
    source_name: str | None = None


class AccessRequestBody(CleanBody):
    study_id: str
    purpose: str = Field(min_length=10, max_length=1000)


class AccessDecisionBody(CleanBody):
    approve: bool
    note: str | None = None
    expires_at: date | None = None


class EscalationBody(CleanBody):
    brief_id: str | None = None
    note: str = Field(min_length=3, max_length=2000)
    # From the generated escalation draft: the gaps the user ticked, and the question for the analyst.
    gaps: list[str] = Field(default_factory=list, max_length=12)
    suggested_question: str | None = Field(default=None, max_length=1000)

    @field_validator("gaps")
    @classmethod
    def _gaps(cls, value: list[str]) -> list[str]:
        kept = [g.strip() for g in value if g and g.strip()]
        if any(len(g) > 500 for g in kept):
            raise ValueError("Keep each gap under 500 characters.")
        return kept


class EscalationResponseBody(CleanBody):
    response: str = Field(min_length=3, max_length=4000)


class CoverageBody(CleanBody):
    title: str = Field(min_length=3, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=12)

    @field_validator("objectives")
    @classmethod
    def _objectives(cls, value: list[str]) -> list[str]:
        kept = [o.strip() for o in value if o and o.strip()]
        if not kept:
            raise ValueError("Give at least one objective.")
        if any(len(o) > 500 for o in kept):
            raise ValueError("Keep each objective under 500 characters.")
        return kept
