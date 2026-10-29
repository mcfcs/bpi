# S&I evidence assistant (BPI DataWave 2026 prototype)

An evidence assistant for BPI Strategy & Insights (S&I) and authorised business-unit teams. A user
asks a business question in plain language; the system retrieves approved research findings that
user is permitted to see and returns an evidence brief with citations, charts and a computed
confidence level.

**All data in this repository is synthetic.** Never load real BPI data into it.

## What is where

| Path | Contents |
|---|---|
| `supabase/migrations/` | Postgres schema for Supabase: tables, RLS, `can_read()`, hybrid search, audit log |
| `supabase/local/supabase_shim.sql` | Local stand-in for Supabase's `auth` schema and roles (plain Postgres only) |
| `backend/app/` | FastAPI service: retrieval, divergence, synthesis, validators, charts, review, commissioning |
| `backend/tests/` | 84 tests against a real Postgres + pgvector, including the acceptance tests |
| `frontend/` | Next.js app: the brief, review queue (checkpoint 1), access, analyst desk, commissioning, audit log |
| `data/synthetic/` | The demo corpus (`corpus.json`) and two raw reports that go through ingestion |
| `docs/` | Hackathon brief and consultation notes |

## Run it locally

Requirements: Python 3.11+, Node 20+. Postgres is not needed: the dev script runs an embedded
Postgres 16 with pgvector (`pgserver`).

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # macOS/Linux: .venv/bin/pip
.venv/Scripts/python scripts/dev_db.py               # start the local database, migrate, seed; writes .env.local
.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                          # http://localhost:3000
```

`scripts/dev_db.py --stop` stops the local database; `--reset` wipes and reseeds it.

The browser only talks to Next.js: `/api/*` is proxied to the backend (`BACKEND_URL`, default
`http://127.0.0.1:8000`; see `frontend/.env.local.example`), so the backend never needs to be
exposed.

### On your Tailscale tailnet (one port)

From the repo root, in PowerShell:

```powershell
./scripts/tailnet.ps1                 # build and serve on 0.0.0.0:10012; prints the tailnet URL
./scripts/tailnet.ps1 -Dev            # hot reload instead
./scripts/tailnet.ps1 -Stop
./scripts/tailnet.ps1 -OpenFirewall   # once, as Administrator: allow TCP 10012 from 100.64.0.0/10 only
```

Then open `http://<this machine's tailscale ip>:10012` from any device on the tailnet. The backend
stays on loopback. On macOS/Linux: run the backend as above and `npm run build && npm run start:tailnet`.

Sign in as one of the demo personas (each sees only what their team may read):

| Persona | Team | Role |
|---|---|---|
| Ana Reyes | Strategy & Insights | S&I analyst: review queue, analyst desk, audit log |
| Ben Santos | SME Banking | Business unit: can read SME Banking's restricted survey |
| Dino Cruz | SME Banking | Approver: decides access requests for SME Banking studies |
| Carla Mendoza | Cards & Payments | Business unit: sees SME Banking's survey only as a restricted match |

Questions that exercise the client's rules:

- *Why do SME owners drop off during online loan applications?* (as Ben): Tier A headline, a fees
  context difference (age, region, period, method), charts, and the Cebu and Iloilo focus groups under
  "What people say".
- *How do market vendors feel about accepting QR payments?*: qualitative only, so there is no
  headline, the disclaimer is shown and confidence is Low.
- *Do young professionals prefer cashback or travel rewards on credit cards?* (as Carla): an
  unresolved conflict, Low confidence, routed to an analyst automatically.

### Using Claude

Without credentials the backend uses a deterministic template writer (`OfflineLLM`), which is
also what the tests use. To use Claude, set in `backend/.env.local` (or the environment):

```
ANTHROPIC_API_KEY=...
LLM_PROVIDER=anthropic          # default when ANTHROPIC_API_KEY is set
LLM_MODEL=claude-opus-5-5       # default
LLM_EFFORT=high                 # low | medium | high | xhigh | max
```

Calls use structured output (`client.beta.messages.parse` with the Pydantic schemas in
`app/schemas.py`) and server-side refusal fallback (`fallbacks="default"`). If a call fails, the
brief is written from templates instead and the brief says so.

## Deploying to Supabase

1. Apply `supabase/migrations/*.sql` with the Supabase CLI (`supabase db push`). Do **not** apply
   `supabase/local/supabase_shim.sql`; Supabase already provides what it stubs.
2. Run the API with `DATABASE_URL` (the project's Postgres connection string) and
   `SUPABASE_JWT_SECRET`. Each request runs as the caller (`set local role authenticated` plus the
   JWT claims), so RLS applies exactly as it does through Supabase's own API.
3. Leave `DEMO_MODE` unset in production; the frontend should then sign in with Supabase Auth and
   send its access token. Token verification is HS256 with the project JWT secret; projects using
   asymmetric signing keys need JWKS verification added in `app/auth.py`.

## How a brief is built

1. **Retrieve** (`app/retrieval.py`): hybrid pgvector and full-text search (`match_findings`,
   `SECURITY INVOKER`, so RLS applies), with a relevance floor, then reranked by robustness tier.
   Lower tiers rank lower but are never excluded. Verbatims that belong to retrieved qualitative
   themes are attached. Restricted studies are surfaced as metadata only.
2. **Classify divergences in code** (`app/divergence.py`): two findings diverge when they show
   opposite directions on the same `metric_key` (or theme). If their populations differ by age,
   region, segment, period (more than 18 months apart) or method, it is a *context difference*;
   otherwise an *unresolved conflict*.
3. **Write** (`app/llm.py`, `app/prompts.py`): the LLM receives only the retrieved findings (as refs
   F1, F2, ...), the fixed divergence classifications, the chartable metric keys and code-detected
   gaps. It never supplies numbers for charts.
4. **Validate** (`app/validators.py`): citation IDs must be in the retrieved set; qualitative-only
   claims must be hedged and must not state incidence; a headline needs Tier A or B quant evidence;
   "conflict" is reserved for unresolved conflicts. A failing brief is regenerated once with the
   problems listed, then any claim that still fails is dropped. Context notes always take their
   topic, findings and `differs_by` from the classifier.
5. **Compute confidence** (`app/confidence.py`) and **build charts** from database values
   (`app/charts.py`).
6. **Store** the brief, route unresolved conflicts to an analyst, and write the audit log.

## Governance

Row-level security with `can_read()` is the single read rule: a study is readable when it is
approved and is open, or owned by the reader's team, or granted to that team, or the reader is
S&I. The audit log is append-only (writes go through `log_audit()` and triggers; updates, deletes
and truncation are refused).

The four human checkpoints, as implemented:

1. **Study review**: S&I analysts check every extracted study card and its findings before anything is searchable. This is where tier overrides are set, each with a required, audited reason.
2. **Access decisions**: a restricted study is shared only when the owning team's approver or S&I approves a request that states its purpose.
3. **Ask an analyst**: users can escalate any brief, and unresolved conflicts are routed automatically.
4. **Commissioning**: the requester decides whether to send a coverage check to S&I; the system never commissions anything itself.

## Tunable rules (proposed defaults, not yet validated by S&I)

All thresholds live in `backend/app/config.py`:

- `TIER_CONFIG`: method points, sample-size bands, recency bands and tier cut-offs. Tiers are
  recomputed on ingestion, when method, sample size or fieldwork end changes, and nightly
  (`python -m app.jobs.recompute_tiers`, or `POST /api/admin/recompute-tiers` as an S&I analyst).
- `DIVERGENCE_CONFIG`: minimum age and region overlap, and the period window.
- `RETRIEVAL_CONFIG`, `COVERAGE_CONFIG`: similarity floors, tier rerank boosts.
- `CHART_CONFIG`, `METRIC_LABELS`: chart minimums and display labels.
- `app/geography.py`: locations mapped to regions and island groups.

## Commissioning hand-off

"Before you commission" checks each objective against approved studies and stores
`{objectives: [{text, coverage, finding_ids}], recommended_new_scope}`. Set `COMMISSIONING_ADAPTER`:

- `noop` (default): store the result and offer JSON and PDF export.
- `webhook`: POST the result to `COMMISSIONING_WEBHOOK_URL`, with optional headers in
  `COMMISSIONING_WEBHOOK_HEADERS` (JSON). This could be a Power Automate HTTP trigger, but nothing
  about the receiver is assumed. The target system and its fields still need confirming with S&I
  (see the TODO in `app/commissioning.py`).

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest
```

Tests run against a real Postgres with pgvector and the actual migrations; each test gets a fresh
copy of a seeded template database. `test_acceptance.py` maps one-to-one to the acceptance criteria;
`test_permissions.py` and `test_redteam.py` cover RLS, grants, the audit log, and that restricted
findings never reach the LLM.

## Open questions (kept configurable)

- Tier thresholds and weights, pending S&I validation.
- S&I's commissioning system and the fields it needs.
- Whether regions, age bands and metric keys should come from fixed lists supplied by S&I.

## Known limitations

- The default embedder (`app/embeddings.py`) is lexical feature hashing with a small glossary, so it
  misses paraphrases. For semantic search, `pip install -r requirements-semantic.txt` and set
  `EMBEDDING_PROVIDER=fastembed`: a local multilingual model (no data leaves the machine) that, on
  the evaluation set in `backend/eval/`, raises paraphrase recall from 0.69 to 0.90 and Taglish
  recall from 0.81 to 0.88 with no off-topic matches. Its floors were tuned on 24 synthetic
  questions; recalibrate on real ones (`python -m eval.retrieval_eval --sweep`).
- The offline extractor reads the semi-structured synthetic reports only; prose reports need Claude.
- The Claude path is not exercised by the automated tests, which use the deterministic writer and
  scripted fakes to check the validators.
