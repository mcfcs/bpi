# Handoff

Current state of the project for whoever picks it up next (human or agent). Update this at the end
of every working session: what changed, what is running, what is next.

_Last updated: 29 Oct 2026._

## Where things stand

- **Prototype is feature-complete for the DataWave brief**: ask → cited brief with charts and
  computed confidence; four human checkpoints (study review, access decisions, ask an analyst,
  commissioning hand-off); RLS-enforced permissions; append-only audit log.
- **Deadlines:** submission 13 Nov 2026 (pitch deck + prototype); top-5 pitch 27 Nov. Second
  consultation 4 Nov — bring the open questions below.
- **Tests:** 88 backend tests pass (`cd backend && .venv/Scripts/python -m pytest`, ~20 s).
  Frontend typechecks and builds.
- **Runs on the tailnet:** `./scripts/tailnet.ps1` → `http://100.102.10.69:10012` (this PC's
  Tailscale IP). Firewall rule "BPI Evidence Assistant (Tailscale) 10012" is installed.

## Session log

### 29 Oct 2026 — initialisation and first improvement pass

1. Read the codebase and the consultation notes; installed and ran everything (Python 3.14, Node 24).
2. **Tailscale / one-port deployment**: Next proxies `/api/*` to the backend; `scripts/tailnet.ps1`.
3. **Continuity**: `AGENTS.md` (source of truth for any agent), `CLAUDE.md`, `.claude/agents/`
   (`retrieval-evaluator`, `brief-qa`), `.claude/skills/run-app`, this file, `docs/IMPROVEMENTS.md`.
4. **Frontend audit and fixes** (accessibility, silent failures, mobile, brief page): see the commit
   "Fix accessibility, error handling and mobile issues in the frontend".
5. **Claude path**: findings prompt cached for regeneration; timeouts; first tests of `ClaudeLLM`.
6. **Retrieval**: evaluation harness and an optional local semantic embedder. Results below.

## Retrieval results

`python -m eval.retrieval_eval` (24 questions: 3 canonical, 12 paraphrase, 4 Taglish, 5 off-topic;
study-level scoring, as the S&I analyst so permissions don't confound it):

| Embedder | Paraphrase recall | Paraphrase hit@1 | Taglish recall | MRR | Off-topic FP | Micro F1 |
|---|---|---|---|---|---|---|
| hashing (default; tests) | 0.69 | 0.75 | 0.81 | 0.84 | 0.00 | 0.81 |
| **fastembed multilingual MiniLM-L12** (enabled locally) | **0.90** | 0.75 | **0.88** | **0.89** | **0.00** | **0.86** |

Five fastembed models were swept (floors 0–0.90 × relative floors); the multilingual model was the
only one to reach zero off-topic hits with high recall. Its floors (0.38 / 0.7) sit mid-plateau:
every floor from 0.36 to 0.40 gave the same zero false positives. Off-topic questions peaked at
0.355 similarity. Remaining misses: "technical glitches when uploading files" (finds nothing), and
some cross-topic extras (card studies appearing for "physical money over cashless").

The machine running the tailnet demo has `EMBEDDING_PROVIDER=fastembed` in `backend/.env.local`.

## Configuration you need to know

| Setting | Where | Default | Notes |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | `backend/.env.local` | `hashing` | `fastembed` for semantic search; needs `pip install -r requirements-semantic.txt`, then restart `dev_db.py` (re-embeds automatically) |
| `EMBEDDING_MODEL` | `backend/.env.local` | see `app/embeddings.py` | Any fastembed model with ≤512 dimensions; add floors for it in `EMBEDDER_FLOORS` (`app/config.py`) after running the eval |
| `ANTHROPIC_API_KEY` | `backend/.env.local` | unset | Without it, briefs use the deterministic template writer |
| `LLM_MODEL` / `LLM_EFFORT` | `backend/.env.local` | `claude-opus-5-5` / `high` | Opus 5.5 defaults to `medium` effort if unset at the API, so keep it explicit |
| `BACKEND_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` | Where Next proxies `/api` |

Models download to `%LOCALAPPDATA%\si-evidence-assistant\models`; the dev database lives in
`%LOCALAPPDATA%\si-evidence-assistant\pgdata` (both outside the OneDrive-synced repo).

## Open questions for S&I (4 Nov consultation)

1. Tier thresholds and weights (`TIER_CONFIG`) — still proposed defaults.
2. Should a headline be allowed when its metric is part of an unresolved conflict? (IMPROVEMENTS A4)
3. Their commissioning system and required fields (`WebhookAdapter.payload`).
4. Fixed vocabularies for regions, age bands and metric keys?
5. A sample of real (anonymised) BU questions to evaluate retrieval on (IMPROVEMENTS A3).
6. Brand guidelines for the accent colour and typeface (IMPROVEMENTS S9).

## Next steps, in order

1. Run one session with a real `ANTHROPIC_API_KEY` and record validator/regeneration/cost numbers (A7).
2. CI on GitHub Actions: pytest + typecheck + build (P2).
3. Pitch deck: lead with the paraphrase-search before/after (eval table above) and the four checkpoints.
4. Supabase Auth in the frontend for a non-demo deployment (S6).

## Known gaps not to forget

- Project `.claude/settings.json` (a permission allowlist for routine test/build commands) was not
  created: the agent's write was blocked as self-modification. Create it yourself or run
  `/fewer-permission-prompts` if prompts get noisy.
- Floors for the semantic embedder were tuned in-sample on 24 synthetic questions.
