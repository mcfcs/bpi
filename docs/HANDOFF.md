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
7. **BPI colours**: red `#9A191E` and gold `#D5B625` sampled from the current logo; red header band
   with a gold rule, white page, red primary actions. Links and charts stay slate blue on purpose.
   The logo itself is not used in the app.
8. **Light / dark switch** in the header (Match device, Light, Dark), saved per browser, applied
   before first paint so there is no flash; printing is always light.

### 30 Oct 2026 — frontend for report PDFs and the study catalogue

1. **Citations open the report at the cited page**: chips read "SI-2026-014 · p.3" and open the PDF
   in a new tab through the signed two-minute link (`openReport` in `frontend/lib/api.ts`; the tab is
   opened during the click so pop-up blockers allow it). No page → page 1; no document → no link.
   Public studies say "Public source · <publisher>" in the card meta. Study titles link to the study.
2. **Studies** (`/studies`, in the nav for everyone): filters (method, owner, year, source) and
   search-as-you-type, mirrored to the URL; restricted studies show a lock and the request-access
   flow (`components/RequestAccess.tsx`, shared with the brief's Restricted matches).
3. **Study page** (`/studies/[id]`): findings grouped by report page with p.N links, study card with
   tier breakdown, licence and original URL for public sources.
4. **PDF upload** on the review queue; `/review/[id]` has Open report and a page chip per finding.
5. **Fixes**: example questions always write a fresh brief (reopening an old one hid newly granted
   studies); the analyst's status and reply now show on every brief, with a follow-up question.
6. Payload gaps for the backend: chart bars lack `page`/`document_url` (looked up via
   `brief.sources`, which misses some bars); `brief.escalation` is only the latest escalation, so a
   reply disappears from the brief once a follow-up is sent; no group count for "6 FGDs" labels.

### 30 Oct 2026 — frontend for brief intelligence (consultation 2)

1. **Answer with audience modes**: Executive / Analyst / Plain language switch above the headline
   (`components/brief/AudienceAnswer.tsx`), citing the summary's studies; the choice is kept per
   browser (`si-evidence:audience`). "Prepared for <name> · <team>" with the framing note.
2. **Segment statements** (`lib/segments.ts` parses the backend's deterministic explanations back into
   lines; falls back to the prose if the wording differs): "It depends on who was asked" shows each
   group as who/where/when → result; "Two trends in the same study" names the target respondents;
   unresolved conflicts show what each study found and the analyst's status.
3. **What people say**: emotion words on qualitative claims and quotes (`components/Emotion.tsx`,
   "Detected from participants' words"); qualitative views that run against a survey show who said
   them next to what the survey measured, never as a conflict. Study cards read
   "6 FGDs · 48 participants · **Sep 2025** (1 year 1 month ago)"; the tier badge's tooltip gives the
   tier basis.
4. **Ask an analyst page** (`/analyst/new?brief=<id>`), prefilled from the escalation draft: found,
   study codes, difference chips, gap checkboxes, editable question, who it is for, needed by, note,
   and a "What happens next" stepper. The brief's panel shows the whole thread and a follow-up form.
5. **Before you commission**: four coverage states (word + icon), newest fieldwork with its age,
   conflict and restricted-study caveats (request access inline), a "New problems" summary, and the
   existing submission on a repeat send. `?check=<id>` opens a check.
6. **Analyst desk**: "Coverage checks sent to S&I" inbox for S&I, linking to each check.
7. Payload problems for the backend: a brief whose conflict was linked to an earlier open escalation
   has `escalation: null` on GET (the UI says "Sent to an analyst" for business users); QR claim text
   says "frustration and worry" while its `emotions` are Worry and Convenience; a gap `ask` names a
   study the brief does not cite (SI-2026-025 in the Gen Z brief); coverage marks "crypto savings
   among OFWs" covered (stale) by the World Bank enterprise survey and "pet insurance add-on" covered
   by SI-2026-027 for Carla; awkward generated wording ("on prefers cashback rewards", "Long ATM
   queues moves in two directions", "Fees differs by ...").

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
6. Brand guidelines: confirm the sampled red/gold, the typeface, and whether the crest may appear
   in the prototype (IMPROVEMENTS S9).

## Next steps, in order

1. Run one session with a real `ANTHROPIC_API_KEY` and record validator/regeneration/cost numbers (A7).
2. Check the first CI run in the GitHub Actions tab (`.github/workflows/ci.yml`; not verified yet).
3. Pitch deck: lead with the paraphrase-search before/after (eval table above) and the four checkpoints.
4. Supabase Auth in the frontend for a non-demo deployment (S6).

## Known gaps not to forget

- Project `.claude/settings.json` (a permission allowlist for routine test/build commands) was not
  created: the agent's write was blocked as self-modification. Create it yourself or run
  `/fewer-permission-prompts` if prompts get noisy.
- Floors for the semantic embedder were tuned in-sample on 24 synthetic questions.
