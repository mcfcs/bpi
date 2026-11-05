---
inclusion: always
---

# Structure

The layout table is in `AGENTS.md` ("Layout"). Where things live for the AWS experiment:

| What | Where |
|---|---|
| Claude client (Anthropic API and Bedrock) | `backend/app/llm.py` (`ClaudeLLM`, `build_llm`, `build_bedrock_client`) |
| Embedders (hashing, fastembed, Bedrock) | `backend/app/embeddings.py` (`build_embedder`) |
| Settings and thresholds | `backend/app/config.py` (`Settings`, `EMBEDDER_FLOORS`) |
| Bedrock tests (fake clients) | `backend/tests/test_bedrock.py` |
| Retrieval eval | `backend/eval/retrieval_eval.py --provider bedrock` |
| Plan and specs | `docs/AWS_PLAN.md`, `.kiro/specs/` |
| Continuity | `docs/HANDOFF.md` (update at the end of every session), `docs/IMPROVEMENTS.md` |
