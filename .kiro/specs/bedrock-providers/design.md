# Design: Bedrock providers

## Overview

Two small additions behind existing seams; no change to the pipeline, schema or frontend.

```
synthesis.BriefService ──► LLM protocol ──► ClaudeLLM(provider="anthropic")  Anthropic()            (today)
                                        └─► ClaudeLLM(provider="bedrock")    AnthropicBedrockMantle (new)
                                        └─► OfflineLLM                                              (tests)

retrieval / ingestion  ──► Embedder     ──► HashingEmbedder (tests) · FastEmbedEmbedder (demo)
                                        └─► BedrockEmbedder → bedrock-runtime InvokeModel, Cohere v4 (new)
```

## Claude on Bedrock (`backend/app/llm.py`)

- `ClaudeLLM(model, effort, client, provider)`; `_parse` builds one request and adds
  `_fallback_params()` only for `provider == "anthropic"` (server-side `fallbacks="default"` +
  `server-side-fallback-2026-07-01`). Bedrock serves the same Messages API, so structured output
  (`beta.messages.parse` with `output_format=<Pydantic model>`), `output_config.effort` and
  `cache_control` are unchanged (Bedrock supports all three).
- `build_bedrock_client(settings)` → `anthropic.AnthropicBedrockMantle(aws_region=…, aws_profile=…,
  timeout=120, max_retries=1, middleware=…)`. Endpoint: `https://bedrock-mantle.<region>.api.aws/anthropic`.
  Optional `BetaRefusalFallbackMiddleware([{"model": bedrock_model_id(BEDROCK_FALLBACK_MODEL)}])`.
- `bedrock_model_id()` prefixes first-party IDs with `anthropic.`; prefixed IDs and inference profiles
  pass through.
- `ClaudeLLM.name` is `bedrock:<model>` so briefs and the audit log show which platform wrote them.

### Region and model choice (from docs/AWS_PLAN.md, check in the console before use)

| Setting | Value | Why |
|---|---|---|
| `AWS_REGION` | `ap-southeast-1` (Singapore) | Nearest region; no AWS region in the Philippines |
| `LLM_MODEL` | `claude-opus-5-5` → `anthropic.claude-opus-5-5`, or a `global.` profile | Opus 5.5 is offered from Singapore only through global cross-region inference (routes anywhere) |
| Alternative | `claude-sonnet-5` | In-region in Singapore since 29 Sep 2026; use if data must stay in-region |
| `LLM_EFFORT` | `high` | Keep explicit (Opus 5.5's API default is `medium`) |

## Embeddings on Bedrock (`backend/app/embeddings.py`)

- `BedrockEmbedder(model="cohere.embed-v4:0", region, client, dimensions=512)`; body
  `{"texts": [t], "input_type": "search_document"|"search_query", "embedding_types": ["float"],
  "output_dimension": 512, "truncate": "RIGHT"}`; reads `embeddings` (list, or `{"float": [...]}`);
  L2-normalises; zero-pads to 512; per-process cache.
- Region check happens before importing boto3, so tests and CI need no AWS packages for that path.
- `EMBEDDER_FLOORS` has no entry for `bedrock:cohere.embed-v4:0`: the hashing defaults would be wrong,
  so R5.3 requires a sweep before use.

## Testing

`backend/tests/test_bedrock.py`, fake clients only: request parity with the Anthropic path (R1),
model IDs (R2), Mantle construction and region check (R3, skipped without `botocore`), embedder
request shape, normalisation, padding, cache (R4), region check (R5). CI installs
`requirements-aws.txt` on `model-serve`.

## Risks

- Global inference routes outside Singapore: a data-residency question for BPI (AWS_PLAN section 7).
- Bedrock pricing for Claude was not listed when the plan was written; measure from the bill.
- Embeddings send finding text to AWS; only synthetic/public data on this branch.
