# Improvement backlog

Prioritised from a review of the code, the running app (Playwright at 1440 and 390 px, light and
dark), the retrieval evaluation harness, and the client consultation notes in
`docs/BPI Datawave 2026.docx`. Status as of 30 Oct 2026. **Done** items link to the commit subject.

Priorities: **P0** affects whether the demo answers the client's pain point; **P1** clearly improves
trust or usability; **P2** polish or later-stage.

## Why these priorities

The consultation named four pains: (1) keyword search misses questions worded differently and returns
false keyword hits; (2) studies are siloed by team, with a manual permission process; (3) BUs wait on
S&I for answers existing studies already hold; (4) studies disagree because of different methods
and samples. The prototype already handles (2)–(4) carefully in code (RLS, divergence classifier,
validators, confidence). (1) was the weakest link: the embedder was lexical, so it reproduced the
exact failure S&I described.

## AI and retrieval

| # | Pri | Item | Status |
|---|---|---|---|
| A1 | P0 | **Semantic retrieval.** Local neural embedder (fastembed, ONNX, no data leaves the machine) behind `EMBEDDING_PROVIDER`, per-embedder similarity floors, `app.jobs.reembed`. Hashing stays the default for tests. | Done — "Add local semantic embeddings…" |
| A2 | P0 | **Retrieval evaluation harness** (`backend/eval/`): canonical, paraphrase, Taglish and off-topic questions; recall, hit@1, MRR, negative false-positive rate, micro-F1; floor sweep. | Done |
| A3 | P1 | Grow the eval set with real BU questions (from S&I's request inbox) and hold some out; current floors are tuned in-sample on 24 synthetic questions. | Open — needs S&I data |
| A4 | P1 | **Headline vs unresolved conflict.** For "cashback or travel?", a confident headline ("54% prefer cashback") sits above an unresolved conflict on the same metric. Proposed rule: a headline may not cite a finding that is part of an unresolved conflict; demote it to a breakdown and say the studies disagree. This is S&I's call, not ours. | Done (consultation 2): a headline on a disputed figure says what each study found, with populations |
| A5 | P1 | Prompt caching for the regeneration call (findings block cached, feedback appended). | Done — "Cache the findings prompt…" |
| A6 | P1 | Test the Claude path with a fake client (request shape, refusal / truncation / timeout mapping). | Done |
| A7 | P1 | Run the brief pipeline once with a real Claude key and record: validator failure rate, regeneration rate, dropped claims, latency, cost per brief. Then decide `LLM_EFFORT` per route (brief vs scope note vs extraction). | Open — needs API key |
| A8 | P2 | Stream the brief (or at least report pipeline stage) so the UI can show real progress instead of a step list and a timer. | Open |
| A9 | P2 | Query understanding for multi-part questions ("fees **and** approval time in Visayas") — split into sub-queries, retrieve per part, merge. | Open |
| A10 | P2 | Coverage check ("Before you commission") floors per embedder were set from the retrieval sweep; evaluate coverage separately with labelled objectives. | Done: `eval/coverage_eval.py` (14 cases) and coverage states covered / stale / partial / new problem |
| A11 | P2 | Ingestion: the offline extractor only reads the semi-structured synthetic reports. Add an extraction eval (field-level accuracy on a few hand-labelled reports) before trusting Claude extraction on prose reports. | Done offline: `eval/extraction_eval.py` (synthetic 100%, public 7% finding recall); Claude run pending a key |

## Site (frontend)

| # | Pri | Item | Status |
|---|---|---|---|
| S1 | P0 | Reachable from other devices: same-origin `/api` proxy, Tailscale launcher on port 10012, firewall rule scoped to 100.64.0.0/10. | Done — "Proxy /api through Next…" |
| S2 | P1 | Accessibility: unlabelled review fields, tier badges unreadable to screen readers, unannounced errors. | Done — "Fix accessibility…" |
| S3 | P1 | Silent failures: load errors shown as empty lists, unhandled rejections, double submits, tier override message lost on remount. | Done |
| S4 | P1 | Mobile: nav links hidden in an invisible scroll strip; tables breaking one word per line; iOS input zoom; page overflow. | Done |
| S5 | P1 | Brief: confidence up top, print / save as PDF, honest progress while generating. | Done |
| S6 | P1 | Production auth: the frontend only has demo sign-in. Add Supabase Auth (the backend already verifies Supabase JWTs) and hide persona switching outside `DEMO_MODE`. | Open |
| S7 | P2 | Pages are all client components, so per-page metadata uses React 19 `<title>`. Moving data loading to server components would need the token in a cookie rather than localStorage; worth it with S6. | Open |
| S8 | P2 | Brief sharing: a stable link a colleague on the same team can open (RLS already decides what they see), and "copy citation" for decks. | Partly: citations open the report PDF at the cited page; brief sharing links still open |
| S9 | P2 | **Visual identity.** BPI colours are in (red `#9A191E` header band with a gold `#D5B625` rule, white page, red actions, gold-on-red icon), sampled from the current logo. Still open: several choices are common generated-UI defaults (hairline broadsheet rules, all-caps tracked mono eyebrows on every page, middle-dot meta strings). With official brand guidelines: drop eyebrows that carry no information, use BPI's typeface if licensed, and decide whether the crest may appear in the header. | Colours done; typeface/logo need brand guidelines |
| S10 | P2 | Analytics for the pitch: which questions were asked, how many hit restricted studies, how many escalated — from the audit log, as an S&I dashboard. | Open |

## Added after consultation 2 (30 Oct 2026)

| # | Pri | Item | Status |
|---|---|---|---|
| C1 | P0 | Segment statements instead of "studies disagree"; quant first; quant and qual never compared | Done |
| C2 | P0 | Report PDFs with page citations; studies catalogue; PDF upload; public research sources | Done |
| C3 | P1 | Qualitative tiers by recency; method labels ("6 FGDs · 48 participants") and fieldwork dates | Done; thresholds for S&I to confirm |
| C4 | P1 | Emotion cues, geography (Metro Manila vs provincial/rural), two trends in one study | Done (lexicon-based emotions) |
| C5 | P1 | Audience modes, "Prepared for", generated ask-an-analyst draft, escalation threads | Done |
| C6 | P1 | Confidence counts only conflicts relevant to the question | Open |
| C7 | P2 | Tier design weighting (probability sample, national frame) beyond n bands | Open, S&I to decide |
| C8 | P2 | AWS experiment: Claude on Bedrock behind the LLM protocol (`docs/AWS_PLAN.md`) | Planned |

## Platform and operations

| # | Pri | Item | Status |
|---|---|---|---|
| P1 | P1 | `.claude/` folder, `AGENTS.md`, `CLAUDE.md`, `docs/HANDOFF.md` for continuity between sessions and agents. | Done |
| P2 | P1 | CI: GitHub Actions running pytest (pgserver works on Linux runners), `npm run typecheck` and `npm run build` on every push. | Added (`.github/workflows/ci.yml`); first run not yet checked — the repo is private and `gh` is not installed here |
| P3 | P2 | Supabase deployment rehearsal: apply migrations to a real project, run the API against it, check RLS with real JWTs. JWKS verification for asymmetric keys (`app/auth.py`). | Open |
| P4 | P2 | Nightly jobs (`recompute_tiers`, and `reembed` after a model change) scheduled outside the API process. | Open |
