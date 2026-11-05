---
inclusion: always
---

# Tech

Commands, versions and conventions are in `AGENTS.md` ("Commands", "Conventions"). Kiro-specific:

- Backend: FastAPI + Postgres/pgvector with RLS (`supabase/migrations/`). Tests run on an embedded
  Postgres: `cd backend && .venv/Scripts/python -m pytest` (~50 s). macOS/Linux: `.venv/bin/python`.
- LLM: `LLM_PROVIDER` = `offline` (default without credentials; tests) | `anthropic` | `bedrock`.
  Bedrock goes through the Anthropic SDK's `AnthropicBedrockMantle` client; Bedrock has no
  server-side refusal fallback (`BEDROCK_FALLBACK_MODEL` turns on the client-side middleware).
- Embeddings: `EMBEDDING_PROVIDER` = `hashing` (tests) | `fastembed` (local, the demo) | `bedrock`
  (Cohere Embed v4, 512 dims; text leaves the machine). Changing it requires re-embedding:
  `python scripts/dev_db.py` does it on start.
- AWS extras: `pip install -r backend/requirements-aws.txt`. Never commit AWS keys; use
  `aws configure sso` / `AWS_PROFILE`.
- Frontend: Next.js 16 / React 19. Read `frontend/AGENTS.md` before changing it.
