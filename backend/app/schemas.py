"""Structured-output schemas for the LLM and request bodies for the API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

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


class EvidenceBrief(BaseModel):
    claims: list[Claim]
    context_notes: list[ContextNote]
    unresolved_conflicts: list[ContextNote]
    chart_requests: list[str]             # metric_keys only; numbers come from the DB, never the LLM
    gaps: list[str]


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


class AskBody(BaseModel):
    question: str = Field(min_length=5, max_length=500)


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


class IngestBody(BaseModel):
    report_text: str = Field(min_length=40)
    owner_team_id: str
    access_level: Literal["open", "restricted"] = "restricted"
    source_name: str | None = None


class AccessRequestBody(BaseModel):
    study_id: str
    purpose: str = Field(min_length=10, max_length=1000)


class AccessDecisionBody(BaseModel):
    approve: bool
    note: str | None = None
    expires_at: date | None = None


class EscalationBody(BaseModel):
    brief_id: str | None = None
    note: str = Field(min_length=3, max_length=2000)


class EscalationResponseBody(BaseModel):
    response: str = Field(min_length=3, max_length=4000)


class CoverageBody(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=12)
