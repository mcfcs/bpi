# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor, …) working in this repository.
Read this first, then `docs/HANDOFF.md` for the current state of work.

## What this is

An evidence assistant for BPI Strategy & Insights (S&I), built for BPI DataWave 2026 (submission
13 Nov 2026, pitch 27 Nov for the top 5). A business-unit user asks a question in plain language;
the system retrieves approved research findings **that user's team may read** (Postgres RLS),
classifies divergences between studies in code, has an LLM write a cited brief, validates every
claim, computes confidence in code, and builds charts from database values.

The client's stated pain (see `docs/BPI Datawave 2026.docx`): studies are siloed by team, search
is SharePoint keyword matching that misses paraphrases and returns false keyword hits, and BUs
wait on S&I to answer questions existing studies already cover. Governance and human-in-the-loop
are first-class requirements, not extras.

**All data is synthetic. Never add real BPI data, names or figures.**

## Layout

| Path | What |
|---|---|
| `backend/app/` | FastAPI service. Pipeline: `retrieval` → `divergence` → `llm`/`prompts` → `validators` → `confidence` + `charts` → stored by `synthesis` |
| `backend/tests/` | pytest against a real embedded Postgres + pgvector (pgserver); each test gets a fresh DB copy |
| `backend/eval/` | Retrieval evaluation harness (paraphrase questions → expected studies) |
| `frontend/` | Next.js 16 / React 19 app. **Read `frontend/AGENTS.md`** — Next 16 differs from training data; docs are in `frontend/node_modules/next/dist/docs/` |
| `supabase/migrations/` | Schema, RLS, `can_read()`, `match_findings` hybrid search, append-only audit log |
| `data/synthetic/` | `corpus.json` (seeded studies) and two raw reports that go through ingestion |
| `scripts/tailnet.ps1` | Run the whole stack for Tailscale devices on port 10012 |

## Commands

```bash
# Backend (from backend/)
.venv/Scripts/python -m pytest                       # all tests, ~20 s
.venv/Scripts/python scripts/dev_db.py               # start/migrate/seed local DB; writes .env.local
.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000
.venv/Scripts/python -m eval.retrieval_eval          # retrieval recall/MRR per embedder

# Frontend (from frontend/)
npm run typecheck
npm run build
npm run dev                                           # http://localhost:3000, proxies /api to :8000

# Whole stack on the tailnet (from repo root, PowerShell)
./scripts/tailnet.ps1            # production build on 0.0.0.0:10012
./scripts/tailnet.ps1 -Dev       # hot reload
./scripts/tailnet.ps1 -Stop
```

On macOS/Linux use `.venv/bin/...`. Python 3.11+ (3.14 verified), Node 20+.

## Invariants — do not break these

These are the product's trust guarantees and are covered by `test_acceptance.py`,
`test_permissions.py` and `test_redteam.py`. A change that weakens one is a regression even if
tests are edited to pass.

1. **RLS decides what anyone sees.** Every user query runs through `Database.as_user()`. Never read
   findings for a user via `as_service()`.
2. **Restricted findings never reach the LLM.** The LLM sees only what `retrieval.search` returned
   for that user. Restricted studies surface as catalogue metadata only (`restricted_study_matches`).
3. **The LLM never supplies numbers or classifications.** Chart values come from the DB
   (`charts.py`); divergence kind and `differs_by` come from `divergence.py`; tiers from `tiers.py`;
   confidence from `confidence.py`. The LLM only writes wording and picks chartable metric keys.
4. **Every claim is validated** (`validators.py`): citations must be retrieved IDs; qualitative-only
   claims are hedged and never state incidence; a headline needs Tier A/B quant; "conflict" is
   reserved for unresolved conflicts. Failing briefs are regenerated once, then failing claims dropped.
5. **Humans decide.** Four checkpoints: study review, access decisions, ask-an-analyst escalation,
   commissioning hand-off. The system never approves, grants or commissions on its own.
6. **Audit log is append-only**, written via `log_audit()` / triggers.
7. **Tests use `OfflineLLM` and `HashingEmbedder`** so they are deterministic and offline. Keep them
   that way; test new providers behind the same protocols.

## Conventions

- Tunable thresholds live in `backend/app/config.py`, not inline. They are proposed defaults that
  S&I has not validated; say so when you add one.
- Python: type hints, dataclasses/Pydantic, small modules, docstrings that explain *why*. Match the
  existing plain, precise comment style.
- Frontend: the visual direction is a typeset research memo (Newsreader serif, Public Sans, IBM Plex
  Mono) in **BPI colours**: red `#9A191E` and gold `#D5B625`, sampled from the current logo, on a
  white page. Red carries the header band and primary actions; gold appears only on the red band
  (gold on white fails contrast). Links and chart bars stay slate blue on purpose. Don't introduce
  a component library or gradients, and don't use the BPI logo itself without the owner's say-so.
  Colour tokens live in `frontend/app/globals.css`.
- The browser calls `/api/*` on its own origin; `next.config.mjs` proxies to `BACKEND_URL`. Don't
  hard-code `localhost:8000` in the frontend.
- Copy is plain English for BU readers: short sentences, no hype.

## Verifying changes

- Backend change → `pytest`. Retrieval/embedding change → also `python -m eval.retrieval_eval` and
  record the numbers in the commit message or `docs/HANDOFF.md`.
- Frontend change → `npm run typecheck` and `npm run build`, then check the page in a real browser
  (playwright-cli) at 1440 px and 390 px, light and dark.
- Never commit secrets: `backend/.env.local`, `frontend/.env.local` are git-ignored.

## Continuity

- `docs/HANDOFF.md` — current state, what changed last, open problems, next steps. **Update it at
  the end of every working session.**
- `docs/IMPROVEMENTS.md` — the prioritised improvement backlog with rationale.
- Commit in small, descriptive commits; history is the project log.
