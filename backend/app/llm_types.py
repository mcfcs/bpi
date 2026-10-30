"""Types shared by the LLM clients and the synthesis step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .retrieval import Source
from .schemas import EvidenceBrief, StudyCardExtraction


class LLMError(RuntimeError):
    """The model could not produce a usable answer (API error, refusal, truncation)."""


@dataclass
class PromptGroup:
    """A classified divergence, expressed with prompt refs (F1, F2, ...)."""

    kind: str
    topic: str
    refs: list[str]
    differs_by: list[str]
    pairs: list[tuple[str, str, list[str]]] = field(default_factory=list)


@dataclass
class Reader:
    """Who the brief is prepared for. Frames relevance (which metrics come first); it never changes
    which findings are included: retrieval under RLS has already decided that."""

    name: str
    team: str
    role: str                                   # profile role, e.g. bu_user
    role_label: str                             # "Business-unit user", or the reader's own description
    focus_prefixes: tuple[str, ...] = ()        # metric families the team owns (config.TEAM_METRIC_FOCUS)
    team_study_codes: tuple[str, ...] = ()      # retrieved studies the reader's team owns

    def owns(self, source: Source) -> bool:
        return source.owner_team == self.team or bool(
            source.metric_key and any(source.metric_key.startswith(p) for p in self.focus_prefixes))


@dataclass
class QualContrast:
    """A qualitative theme whose direction runs against survey findings on the same topic. It is
    shown as colour in "What people say", never as a divergence (refs are prompt refs)."""

    qual_ref: str
    quant_refs: list[str]
    topic: str


@dataclass
class BriefRequest:
    question: str
    findings: list[tuple[str, Source]]   # (ref, source), most relevant first
    groups: list[PromptGroup]
    chartable: list[str]
    computed_gaps: list[str]
    reader: Reader | None = None
    qual_contrasts: list[QualContrast] = field(default_factory=list)


class LLM(Protocol):
    name: str

    def write_brief(self, request: BriefRequest, feedback: list[str] | None = None) -> EvidenceBrief: ...

    def extract_study_card(self, report_text: str, known_metric_keys: list[str]) -> StudyCardExtraction: ...

    def write_scope(self, title: str, objectives: list[dict]) -> str: ...
