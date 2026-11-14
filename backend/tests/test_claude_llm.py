"""ClaudeLLM request shape and error mapping, with a fake Anthropic client (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm import ClaudeLLM
from app.llm_types import BriefRequest, LLMError
from app.schemas import EvidenceBrief

EMPTY = EvidenceBrief(claims=[], context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])


class FakeClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._response = response or SimpleNamespace(stop_reason="end_turn", parsed_output=EMPTY)
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def request() -> BriefRequest:
    return BriefRequest(question="Why do SME owners drop off?", findings=[], groups=[], chartable=[], computed_gaps=[])


def test_findings_block_is_cached_and_feedback_follows_it():
    client = FakeClient()
    llm = ClaudeLLM("claude-opus-5-5", "high", client=client)
    llm.write_brief(request())
    llm.write_brief(request(), feedback=["Claim 1 cites ids that are not in the findings list: F9."])

    first, retry = (c["messages"][0]["content"] for c in client.calls)
    assert first[0]["cache_control"] == {"type": "ephemeral"}
    # The retry shares the cached prefix byte for byte; only the feedback block is new.
    assert retry[0] == first[0]
    assert len(retry) == 2 and "F9" in retry[1]["text"] and "cache_control" not in retry[1]
    call = client.calls[0]
    assert call["output_format"] is EvidenceBrief
    assert call["output_config"] == {"effort": "high"}
    assert call["fallbacks"] == "default"


@pytest.mark.parametrize("stop_reason, message", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_stop_reasons_become_llm_errors(stop_reason, message):
    client = FakeClient(SimpleNamespace(stop_reason=stop_reason, parsed_output=None))
    with pytest.raises(LLMError, match=message):
        ClaudeLLM("claude-opus-5-5", "high", client=client).write_brief(request())


def test_bedrock_runs_the_same_request_without_server_side_fallback():
    # Claude in Amazon Bedrock serves the same Messages API but not the `fallbacks` parameter.
    client = FakeClient()
    ClaudeLLM("global.anthropic.claude-opus-5-5", "high", client=client, platform="bedrock").write_brief(request())
    call = client.calls[0]
    assert call["model"] == "global.anthropic.claude-opus-5-5"
    assert call["output_format"] is EvidenceBrief and call["output_config"] == {"effort": "high"}
    assert call["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in call and "betas" not in call


def test_build_llm_uses_the_bedrock_client_for_the_bedrock_provider(monkeypatch):
    from dataclasses import replace

    from app import llm as llm_module
    from tests.conftest import TEST_SETTINGS

    regions = []
    monkeypatch.setattr(llm_module, "bedrock_client", lambda region: regions.append(region) or FakeClient())
    built = llm_module.build_llm(replace(TEST_SETTINGS, llm_provider="bedrock", llm_effort="high",
                                         aws_bedrock_model="global.anthropic.claude-sonnet-5-5"))
    assert isinstance(built, ClaudeLLM) and built.platform == "bedrock"
    assert built.name == "global.anthropic.claude-sonnet-5-5" and regions == ["ap-southeast-1"]


def test_bedrock_errors_name_bedrock():
    import anthropic
    import httpx

    error = anthropic.APITimeoutError(request=httpx.Request("POST", "https://bedrock-mantle.ap-southeast-1.api.aws"))
    with pytest.raises(LLMError, match="Bedrock took too long"):
        ClaudeLLM("global.anthropic.claude-opus-5-5", "high", client=FakeClient(error=error), platform="bedrock").write_brief(request())


def test_api_errors_become_llm_errors():
    import anthropic
    import httpx

    error = anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(LLMError, match="too long"):
        ClaudeLLM("claude-opus-5-5", "high", client=FakeClient(error=error)).write_brief(request())
