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
class BriefRequest:
    question: str
    findings: list[tuple[str, Source]]   # (ref, source), most relevant first
    groups: list[PromptGroup]
    chartable: list[str]
    computed_gaps: list[str]


class LLM(Protocol):
    name: str

    def write_brief(self, request: BriefRequest, feedback: list[str] | None = None) -> EvidenceBrief: ...

    def extract_study_card(self, report_text: str, known_metric_keys: list[str]) -> StudyCardExtraction: ...

    def write_scope(self, title: str, objectives: list[dict]) -> str: ...
