# Handoff

Current state of the project for whoever picks it up next (human or agent). Update this at the end
of every working session: what changed, what is running, what is next.

_Last updated: 14 Nov 2026._

## Where things stand

- **Prototype covers the DataWave brief and both S&I consultations**: ask → cited brief (segment
  statements, quant first, qualitative colour with emotion cues, audience modes, page citations into
  report PDFs) with computed confidence; four human checkpoints (study review incl. PDF upload,
  access decisions, ask an analyst with a generated draft, commissioning with coverage states and an
  S&I inbox); RLS-enforced permissions on findings and documents; append-only audit log.
- **Deadlines:** submission 13 Nov 2026 (pitch deck + prototype); top-5 pitch 27 Nov. Next
  consultation 4 Nov: bring the open questions below.
- **Tests:** 181 backend tests pass (`cd backend && .venv/Scripts/python -m pytest`, ~50 s).
  Frontend typechecks and builds. CI: `.github/workflows/ci.yml` (first run not checked: private repo).
- **LLM:** Claude on Amazon Bedrock works (`LLM_PROVIDER=bedrock`, Singapore, global inference
  profiles). 12-question comparison below: Opus 5.5 and Sonnet 5.5 never fell back to templates.
- **Data:** 33 synthetic studies (13 original + 20 added 14 Nov on scams, complaints, financial
  literacy, typhoons, gig work, fisherfolk, green products, accessibility, data privacy, payday
  budgeting, workplace wellness, corporate treasury; 3 of the 20 restricted) + 6 synthetic report
  PDFs in the review queue; 5 public reports
  (BSP FIS 2021, BSP CES Q4 2025, World Bank Enterprise Survey 2023, two CGAP qualitative studies)
  seeded as "Public source" when their PDFs are downloaded (`dev_db.py --fetch-public`; ADB blocks
  scripted downloads). Real BPI data must never be loaded.
- **Runs on the tailnet:** `./scripts/tailnet.ps1` → `http://100.102.10.69:10012`, fastembed
  semantic search, offline template writer (no Anthropic key). Firewall rule
  "BPI Evidence Assistant (Tailscale) 10012" is installed.

## Session log

### 14 Nov 2026: 20 more studies, Claude on Bedrock, writer and Bedrock-search evals

1. **20 synthetic studies** in `data/synthetic/corpus.json` (SI-2022-051 … SI-2026-065; 10 quant,
   8 qual, 2 mixed). Each gets a report PDF like the others. Two carry within-study trends
   (`literacy_trend:`, `privacy_trend:`) and one pair is a context difference (data sharing:
   urban 21–34 vs provincial 45–70). Labels and stance phrases in `config.py`; 21 eval questions in
   `eval/questions.json` (now 64). `report_pdf.py`: qual studies can set their own recruitment
   sentence. `offline_extract.py`: "rose from 38% to 61%" now extracts the latest figure
   (extraction eval 100% on all 37 synthetic reports; SI-2026-025 was 33% recall).
   Committed in `009ddfa` together with the Bedrock work below.
2. **Claude on Bedrock through `ClaudeLLM`** (`app/llm.py`): same structured output, effort and
   prompt caching as the Claude API, minus server-side fallback (not offered on Bedrock: a refusal
   becomes a template brief). Client: `AnthropicBedrock` (bedrock-runtime). The newer
   bedrock-mantle endpoint answers "model does not exist" for Opus 5.5 / Sonnet 5.5 in
   ap-southeast-1; Singapore serves them only through **global** inference profiles
   (`global.anthropic.claude-opus-5-5`), which can route a request to any AWS region. The
   earlier Converse-based `BedrockLLM` forced a tool choice, which these models reject. The hackathon
   SSO role can't subscribe to `anthropic.claude-sonnet-5` (403), but the global 5.5 profiles work.
3. **`eval/brief_eval.py`**: same questions and retrieval (fastembed), different writer; records
   fall-backs, regenerations with the validator feedback, dropped claims, seconds, tokens and cost;
   `--blind` writes an A/B file for people to judge wording. Results below.
4. **`eval/retrieval_eval.py --provider bedrock`** for the Cohere embedder committed in `009ddfa`,
   and each question is embedded once per run (sweeps no longer re-embed 300 times).
   `extraction_eval.py --claude` also runs with `LLM_PROVIDER=bedrock`.

### 30 Oct 2026: consultation 2, documents, redesign, multi-agent pass

Work ran as parallel agents in git worktrees, merged into `main` by the lead (see `git log`).

1. **Design** (Archivo + Fragment Mono replace the old serif/Plex trio; light by default with a
   Light/Dark switch; study-card citations; inviting ask page). BPI red/gold kept.
2. **Consultation rules in the pipeline** (`divergence.py`, `describe.py`, `synthesis.py`,
   `validators.py`, `confidence.py`, `tiers.py`, `emotion.py`, `geography.py`):
   - context differences read as segment statements ("Fees: a driver of drop-off among 20–40 in
     Metro Manila; not among 41–60 nationwide"), never "studies disagree";
   - quant and qual are never compared as a divergence; qual that runs against a survey is colour
     in "What people say" (`qual_contrasts`);
   - qualitative tiers by recency (`QUAL_TIER_CONFIG`: B within 12 months, else C);
   - two trends inside one study (`study_patterns`, "61% → 72%"); Metro Manila vs provincial/rural;
   - qual-only themes synthesised across groups with lexicon emotion cues (English + Tagalog);
   - Executive / Analyst / Plain-language summaries; "Prepared for" persona framing;
   - ask-an-analyst draft (`GET /api/briefs/{id}/escalation-draft`), escalation threads;
   - coverage states covered / covered_stale / partial / gap ("new problem") with caveats.
3. **Documents** (`documents.py`, `documents_api.py`, `report_pdf.py`, migration
   `20261030100000_study_documents.sql`): report PDFs stored per study under RLS, findings pinned to
   pages, signed "open at page N" links, `GET /api/studies` catalogue, PDF upload for S&I, public
   reports with hand-labelled cards, `eval/extraction_eval.py`, `eval/evidence_weighing.py`.
4. **Frontend for all of it**: `/studies`, `/studies/[id]`, citation chips "SI-2026-014 · p.3",
   audience switch, segment lines, emotion labels, `/analyst/new` prefilled handoff page, coverage
   states, S&I inbox of submitted checks.
5. **Bug hunt** (read-only adversarial pass): no restricted leaks found in ~30 briefs. Fixed: 500s on
   malformed ids/NUL bytes/tokens; coverage false "Covered"; headline on a disputed figure; headline
   not answering the question; junk questions getting High confidence; charts showing uncited studies;
   duplicate/overwritten escalations; past-dated grants; access requests on unreviewed studies;
   unlabelled restricted text in exports; stale "ask again"; replies missing from briefs; S&I never
   seeing submitted checks; awkward generated wording.
6. **Retrieval precision** (`retrieval.py`, `topicality.py`, migration
   `20261030120000_restricted_match_concepts.sql`): product and topic facet rerank; coverage needs
   the objective's concept; restricted hints need it too. See results below.
7. **AWS + Kiro plan** (`docs/AWS_PLAN.md`): plan only, nothing built.

### 29 Oct 2026: initialisation and first improvement pass

Tailscale one-port deployment (`scripts/tailnet.ps1`), continuity files (`AGENTS.md`, `CLAUDE.md`,
`.claude/agents`, `.claude/skills/run-app`), first frontend audit, Claude prompt caching and tests,
retrieval eval harness and the local semantic embedder, BPI colours, theme switch.

## Retrieval results

`python -m eval.retrieval_eval --provider all` (43 questions with a tune/holdout split: canonical,
paraphrase, Taglish, off-topic and near-negative; study-level scoring as the S&I analyst):

| | fastembed (demo) | hashing (tests) |
|---|---|---|
| Micro F1, all 43 (no facets → facets) | 0.67 → 0.80 | 0.72 → 0.76 |
| Paraphrase hit@1 / precision | 0.71 / 0.59 → 0.90 / 0.84 | 0.71 / 0.54 → 0.81 / 0.58 |
| Micro F1, held-out half | 0.61 → 0.76 | 0.68 → 0.75 |
| Off-topic false positives | 0.00 | 0.00 |

Coverage eval (`eval/coverage_eval.py`, 14 cases): fastembed 14/14, hashing 13/14. Floors unchanged
(fastembed 0.38 / 0.7). Both halves are ~20 questions: indicative only. Still failing: questions that
name a covered product but ask what no study measures ("metal card design"); "How long do merchants
wait…" pulls card/QR studies; the generic "abandon digital applications" has low recall.

**After the 20 new studies (14 Nov, 64 questions, floors unchanged):**

| | Para recall | Para hit@1 | Para precision | Taglish recall | MRR | Off-topic FP | Micro F1 |
|---|---|---|---|---|---|---|---|
| fastembed (demo) | 0.87 | 0.79 | 0.75 | 0.67 | 0.87 | 0.67 | 0.70 |
| hashing (tests) | 0.75 | 0.69 | 0.46 | 0.81 | 0.82 | 0.50 | 0.63 |
| Bedrock Cohere Multilingual v3, no floors of its own | 1.00 | 0.83 | 0.41 | 1.00 | 0.93 | 1.00 | 0.39 |

On the original 43 questions the larger corpus cost micro F1 0.80 → 0.75 (fastembed) and
0.76 → 0.68 (hashing). The loss is off-topic questions: 0/6 had hits before, now 4/6 (fastembed:
mortgage rates → solar/literacy/typhoon studies at 0.52; retiree savings goals → household budgeting
studies at 0.48). A floor can't remove a 0.52 hit without losing real answers. Coverage checks are
unchanged (fastembed 13/13, hashing 12/13, public PDFs absent). "Ilan ang nakakatanggap ng pekeng
text mula sa bangko?" finds nothing with either local embedder; fastembed also finds nothing for the
Tagalog fisherfolk and compound-interest questions.
Bedrock Cohere finds everything (recall 1.00, Taglish included) but has no `EMBEDDER_FLOORS` entry,
so it runs on the hashing defaults (0.12) and every off-topic question gets hits. Its floor sweep
was still running at the time of writing. Until it has floors, keep `EMBEDDING_PROVIDER=fastembed`
for demos.

## Brief writers (Bedrock, 14 Nov)

`python -m eval.brief_eval --writer bedrock:global.anthropic.claude-opus-5-5 --writer
bedrock:global.anthropic.claude-sonnet-5-5 --writer offline --limit 12` (12 answerable questions, as
Ben Santos, SME Banking; retrieval fastembed; effort high):

| Writer | Fell back | Regenerated | Dropped claims | Claims/brief | Median s | Max s | $/brief (est.) |
|---|---|---|---|---|---|---|---|
| Opus 5.5 | 0/12 | 3 | 0 | 3.2 | 32 | 90 | 0.081 |
| Sonnet 5.5 | 0/12 | 2 | 1 | 3.1 | 20 | 76 | 0.042 |
| Templates | 0/12 | 0 | 0 | 4.2 | 0.2 | 0.3 | – |

Confidence came out the same for all three (7 High / 3 Medium / 2 Low): it is computed in code.
Cost is at Anthropic list prices (Bedrock bills its own; global profiles carry no regional
premium); output tokens (~2,300 per call, thinking included) are most of it. A rewrite roughly
doubles the time. All five rewrites were the qualitative wording rules: a qual-only claim said
"all", or a plain-language summary citing only focus groups lacked a hedge. Stating both rules in
`BRIEF_SYSTEM` should cut rewrites (untested). Read side by side, both models scope the answer to
what the studies measured and say what they don't cover; the templates add off-topic card figures
to a merchant question. Twelve questions is indicative only; judge wording with the `--blind` file.

Extraction (offline, `eval/extraction_eval.py`): synthetic PDFs 100% on every field; public PDFs
find only 7% of findings, so real reports need Claude extraction.

## Configuration you need to know

| Setting | Where | Default | Notes |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | `backend/.env.local` | `hashing` | `fastembed` for semantic search; needs `pip install -r requirements-semantic.txt`; `dev_db.py` re-embeds on start |
| `EMBEDDING_MODEL` | `backend/.env.local` | see `app/embeddings.py` | Any fastembed model ≤512 dims; add floors in `EMBEDDER_FLOORS` after running the eval |
| `ANTHROPIC_API_KEY` | `backend/.env.local` | unset | Without it (and without `LLM_PROVIDER=bedrock`), briefs use the deterministic template writer |
| `LLM_PROVIDER` | `backend/.env.local` | `anthropic` with a key, else `offline` | `bedrock` = Claude on Amazon Bedrock with the AWS credential chain (`AWS_PROFILE`) |
| `AWS_REGION` / `AWS_BEDROCK_MODEL` | `backend/.env.local` | `ap-southeast-1` / `global.anthropic.claude-opus-5-5` | In Singapore use the `global.` IDs; `anthropic.claude-sonnet-5-5` without the prefix is refused there |
| `LLM_MODEL` / `LLM_EFFORT` | `backend/.env.local` | `claude-opus-5-5` / `high` | Keep effort explicit (Opus 5.5's API default is `medium`) |
| `BACKEND_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` | Where Next proxies `/api` |
| Thresholds | `backend/app/config.py` | proposed | `TIER_CONFIG`, `QUAL_TIER_CONFIG`, `COVERAGE_STATE_CONFIG`, `TOPICALITY_CONFIG`, `DOCUMENT_CONFIG`, facet weights |

Models download to `%LOCALAPPDATA%\si-evidence-assistant\models`; the dev database lives in
`%LOCALAPPDATA%\si-evidence-assistant\pgdata`; public PDFs in `data/public/pdfs/` (git-ignored).

## Open questions for S&I (4 Nov consultation)

1. Qualitative tiers: is "B within 12 months, else C" right? Is 24 months the right line for
   "covered but old" in coverage checks?
2. Survey tiers: every n ≥ 1,000 scores the same (n=640 pulse and a 5,489-household national sample
   are both A), and "mixed" labelling costs points. Should design (probability sample, national
   frame) count? (`eval/evidence_weighing.py` prints the table.)
3. Team metric families used for "Prepared for" framing, and the emotion word list: please review.
4. Their commissioning system and required fields (`WebhookAdapter.payload`).
5. Fixed vocabularies for regions, age bands, metric keys and product/topic facets?
6. Real (anonymised) BU questions to evaluate retrieval on, held out from tuning.
7. Brand: confirm sampled red/gold and whether the crest may appear (IMPROVEMENTS S9).
8. Licences: CGAP reports are "all rights reserved", the World Bank survey non-commercial; the repo
   holds only URLs, cards and short quotes. OK for a pitch demo?

## Next steps, in order

1. Pick the Bedrock model after reading the blind A/B file (`eval/brief_eval.py --blind`); then
   state the two qualitative wording rules in `BRIEF_SYSTEM` and rerun the brief eval to see whether
   rewrites drop. Run `eval/extraction_eval.py --claude` with Bedrock on the public PDFs.
   Bedrock search: add `EMBEDDER_FLOORS` from the sweep (and a coverage-eval run) before using
   `EMBEDDING_PROVIDER=bedrock` in a demo.
2. Check the CI run in the GitHub Actions tab.
3. Pitch deck: the consultation example before/after, the retrieval table, the four checkpoints,
   documents with page citations, and the AWS slide from `docs/AWS_PLAN.md`.
4. Confidence should count only unresolved conflicts among findings relevant to the question (the
   facet rerank fixed the known case; the rule itself is still "any conflict → Low").
5. Supabase Auth in the frontend for a non-demo deployment (S6).

## Known gaps not to forget

From the final browser QA (30 Oct), not yet fixed:
- "Are long ATM queues a problem outside Metro Manila?": the headline is the Metro Manila figure;
  the provincial figures are only in Breakdown. Headline choice should honour a place in the question.
- Cashback brief: the two disputed figures also appear as plain breakdown claims and as two chart bars
  with the same label; the Plain-language summary leads on cashback while the headline is on travel.
  Mark claims and bars that belong to an unresolved conflict.
- Analyst desk shows a follow-up as a new card instead of threading it under the first question.
- Asking again joins the open escalation, but the new brief doesn't say "joined an existing check".
- Public study cards (World Bank PUB-WB-ES23): several "Wording in the report" excerpts are table
  fragments that don't show the figure; re-label `data/public/cards/*.json` excerpts.
- A study's sources list shows one card per study, so a two-trends section lists one source.
- Chart bars carry no `page` / `provenance`; restricted catalogue rows show year only.
- Ticked analyst gaps are stored inside the escalation note (no column yet).
- Scanned PDFs are refused (no OCR); Textract is in the AWS plan.
- `.claude/settings.json` (permission allowlist) was not created: the agent's write was blocked as
  self-modification. Create it yourself or run `/fewer-permission-prompts`.
- Stale agent worktrees under `.claude/worktrees/` (git-ignored) can be removed once no process holds
  them: `git worktree prune`.
