"""Amazon Bedrock providers (model-serve branch): request shapes with fake clients, no AWS calls.

Specs: .kiro/specs/bedrock-providers/requirements.md (R1-R6).
"""

from __future__ import annotations

import io
import json
import math
from types import SimpleNamespace

import pytest

from app.config import DEV_JWT_SECRET, Settings
from app.embeddings import EMBEDDING_DIM, BedrockEmbedder, build_embedder
from app.llm import ClaudeLLM, bedrock_model_id, build_llm
from app.llm_types import BriefRequest
from app.schemas import EvidenceBrief

EMPTY = EvidenceBrief(claims=[], context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])


class FakeMessages:
    def __init__(self):
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=EMPTY)


def request() -> BriefRequest:
    return BriefRequest(question="Why do SME owners drop off?", findings=[], groups=[], chartable=[], computed_gaps=[])


def settings(**overrides) -> Settings:
    base = dict(database_url="", jwt_secret=DEV_JWT_SECRET, demo_mode=True, llm_provider="bedrock",
                llm_model="claude-opus-5-5", llm_effort="high", commissioning_adapter="noop",
                commissioning_webhook_url=None, commissioning_webhook_headers={}, cors_origins=(),
                aws_region="ap-southeast-1")
    return Settings(**{**base, **overrides})


# R1: same request as the Anthropic API, without the server-side fallback Bedrock rejects.
def test_bedrock_requests_match_the_anthropic_path_minus_server_side_fallback():
    anthropic_client, bedrock_client = FakeMessages(), FakeMessages()
    ClaudeLLM("claude-opus-5-5", "high", client=anthropic_client).write_brief(request())
    ClaudeLLM("anthropic.claude-opus-5-5", "high", client=bedrock_client, provider="bedrock").write_brief(request())
    first, bedrock = anthropic_client.calls[0], bedrock_client.calls[0]
    assert first["fallbacks"] == "default" and "fallbacks" not in bedrock and "betas" not in bedrock
    for key in ("system", "messages", "output_format", "output_config", "max_tokens"):
        assert bedrock[key] == first[key]
    assert bedrock["model"] == "anthropic.claude-opus-5-5"
    # The findings block is still a cached prefix on Bedrock.
    assert bedrock["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


# R2: model IDs.
@pytest.mark.parametrize("given, expected", [
    ("claude-opus-5-5", "anthropic.claude-opus-5-5"),
    ("anthropic.claude-sonnet-5", "anthropic.claude-sonnet-5"),
    ("global.anthropic.claude-opus-5-5", "global.anthropic.claude-opus-5-5"),   # cross-region profile
])
def test_bedrock_model_ids(given, expected):
    assert bedrock_model_id(given) == expected


# R3: construction needs a region, uses the Mantle client, and names the provider.
def test_build_llm_for_bedrock(monkeypatch):
    pytest.importorskip("botocore")   # requirements-aws.txt; CI installs it on model-serve
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "example")
    llm = build_llm(settings(bedrock_fallback_model="claude-opus-4-8"))
    assert llm.provider == "bedrock" and llm.name == "bedrock:anthropic.claude-opus-5-5"
    assert type(llm.client).__name__ == "AnthropicBedrockMantle"
    assert "bedrock-mantle.ap-southeast-1" in str(llm.client.base_url)
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        build_llm(settings(aws_region=None))


class FakeBedrockRuntime:
    def __init__(self, dims: int = 512, by_type: bool = False):
        self.calls: list[dict] = []
        self.dims, self.by_type = dims, by_type

    def invoke_model(self, **kwargs):
        self.calls.append({**kwargs, "body": json.loads(kwargs["body"])})
        vector = [float(i % 7) - 3 for i in range(self.dims)]
        embeddings = {"float": [vector]} if self.by_type else [vector]
        return {"body": io.BytesIO(json.dumps({"embeddings": embeddings}).encode())}


# R4: Cohere Embed v4 request shape, document vs query, 512 floats, normalised.
@pytest.mark.parametrize("by_type", [False, True])
def test_bedrock_embedder_request_and_vector(by_type):
    runtime = FakeBedrockRuntime(by_type=by_type)
    embedder = BedrockEmbedder(client=runtime)
    doc = embedder.embed("Fees ranked third of seven drop-off reasons.")
    embedder.embed_query("Are fees a barrier?")
    (d, q) = runtime.calls
    assert d["modelId"] == "cohere.embed-v4:0" and embedder.name == "bedrock:cohere.embed-v4:0"
    assert d["body"]["input_type"] == "search_document" and q["body"]["input_type"] == "search_query"
    assert d["body"]["output_dimension"] == 512 and d["body"]["embedding_types"] == ["float"]
    assert len(doc) == EMBEDDING_DIM and math.isclose(math.sqrt(sum(v * v for v in doc)), 1.0, rel_tol=1e-6)
    # Repeated text is served from the cache, not a second call.
    embedder.embed("Fees ranked third of seven drop-off reasons.")
    assert len(runtime.calls) == 2


def test_smaller_bedrock_vectors_are_zero_padded():
    vector = BedrockEmbedder(client=FakeBedrockRuntime(dims=256), dimensions=256).embed("x")
    assert len(vector) == EMBEDDING_DIM and vector[256:] == [0.0] * 256


# R5: no region, no AWS call.
def test_build_embedder_for_bedrock_needs_a_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        build_embedder("bedrock")
