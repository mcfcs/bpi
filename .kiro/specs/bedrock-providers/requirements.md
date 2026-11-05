# Requirements: Bedrock providers

Phase (a) of `docs/AWS_PLAN.md`: try Claude and embeddings on Amazon Bedrock behind the existing
protocols, from a laptop, with synthetic data, without changing what anyone can see.

## Introduction

BPI said it may "experiment with AWS (no migration)". The app already talks to Claude through one
class (`ClaudeLLM`) and embeds text through one protocol (`Embedder`). This feature adds Bedrock as a
provider of each, switchable by environment variable, so the team can compare quality, latency and
cost against the Anthropic API and local fastembed, and switch back with one variable.

## Requirements

### R1. Claude on Bedrock uses the same request

**User story:** As the team, I want briefs written by Claude on Bedrock to go through exactly the same
prompt, structured output and validators, so that any difference we measure is the platform's.

1. WHEN `LLM_PROVIDER=bedrock` THE SYSTEM SHALL send the same system prompt, messages, structured
   output schema, effort and `max_tokens` as the Anthropic API path.
2. WHEN `LLM_PROVIDER=bedrock` THE SYSTEM SHALL NOT send the server-side `fallbacks` parameter or its
   beta header, which Bedrock rejects.
3. WHEN the findings block is sent THE SYSTEM SHALL mark it for prompt caching on both providers.
4. IF Bedrock declines, times out, rate-limits or errors THEN THE SYSTEM SHALL raise `LLMError`, and
   the brief SHALL be written from templates and say so (existing behaviour).

### R2. Bedrock model IDs

1. WHEN `LLM_MODEL` is a first-party ID (`claude-…`) THE SYSTEM SHALL prefix it with `anthropic.`.
2. WHEN `LLM_MODEL` already has a prefix (`anthropic.`, `global.anthropic.`, a regional profile) THE
   SYSTEM SHALL use it unchanged.

### R3. Configuration

1. WHEN `LLM_PROVIDER=bedrock` and `AWS_REGION` is unset THE SYSTEM SHALL refuse to start with a
   message naming `AWS_REGION`.
2. THE SYSTEM SHALL take AWS credentials from the standard AWS chain (`AWS_PROFILE`, SSO, env vars)
   and SHALL NOT read or store keys itself.
3. WHEN `BEDROCK_FALLBACK_MODEL` is set THE SYSTEM SHALL retry refusals on that model with the SDK's
   client-side refusal fallback middleware.

### R4. Bedrock embeddings

1. WHEN `EMBEDDING_PROVIDER=bedrock` THE SYSTEM SHALL embed findings as `search_document` and questions
   as `search_query` with Cohere Embed v4 (`cohere.embed-v4:0`) at 512 dimensions.
2. THE SYSTEM SHALL normalise each vector and zero-pad shorter ones to the 512-dimension column.
3. THE SYSTEM SHALL cache repeated texts within a process.

### R5. Safety and tests

1. THE SYSTEM SHALL keep `OfflineLLM` and `HashingEmbedder` as the test defaults; Bedrock paths SHALL be
   tested with fake clients and make no network calls in tests.
2. THE SYSTEM SHALL NOT change what any user can read: retrieval and RLS stay in Postgres; restricted
   findings never reach any model (AGENTS.md invariants 1–3).
3. WHEN Bedrock embeddings are selected THE SYSTEM SHALL have no calibrated floors until the retrieval
   eval sweep has been run and recorded.

### R6. Evidence for the decision

1. THE TEAM SHALL record, for the three README demo questions on each provider: validator failures,
   regenerations, dropped claims, latency and cost per brief (IMPROVEMENTS A7).
2. THE TEAM SHALL adopt Bedrock embeddings only if `eval.retrieval_eval --provider bedrock` matches
   fastembed with zero off-topic hits.
