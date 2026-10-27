"""Test doubles for the LLM."""

from __future__ import annotations

from app.llm import OfflineLLM
from app.llm_types import BriefRequest
from app.prompts import render_brief_prompt
from app.schemas import EvidenceBrief


class SpyLLM(OfflineLLM):
    """Records exactly what would be sent to the model."""

    name = "spy"

    def __init__(self):
        self.requests: list[BriefRequest] = []
        self.prompts: list[str] = []

    def write_brief(self, request: BriefRequest, feedback=None) -> EvidenceBrief:
        self.requests.append(request)
        self.prompts.append(render_brief_prompt(request, feedback))
        return super().write_brief(request, feedback)


class ScriptedLLM(OfflineLLM):
    """Returns drafts produced by `script(request, attempt)`; attempt is 0 for the first call."""

    name = "scripted"

    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.feedback: list[list[str] | None] = []

    def write_brief(self, request: BriefRequest, feedback=None) -> EvidenceBrief:
        attempt = self.calls
        self.calls += 1
        self.feedback.append(feedback)
        return self.script(request, attempt)
