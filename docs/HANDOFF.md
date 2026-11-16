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
- **Tests:** 205 backend tests pass (`cd backend && .venv/Scripts/python -m pytest`, ~60 s).
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

### 16 Nov 2026 (later): review checks, follow-ups, unanswered demand, home redesign, deck v3 (uncommitted)

1. **Personal-data check at review** (`app/privacy.py`, `PRIVACY_PATTERNS` in config, proposed):
   pattern rules (PH phone, email, account/card number, TIN, street address, names) over a pending
   study's findings. Approval refuses with 422 until the finding is edited or the decision carries
   `privacy_checked: true`; the approval audit records the flag count. Source text is counted only.
   The Cebu synthetic report now has a quote with a synthetic 0917 555 number so the demo shows it.
2. **Overlap check at review** (`app/overlap.py`, `OVERLAP_CONFIG`): nearest approved findings per
   finding by stored embedding (under the analyst's RLS) or same metric family; populations compared
   in code (age, segment, place, period: repeat / newer wave / same topic) and shared figures put side
   by side from the database. No model call. Shown with the privacy result on `GET /api/studies/{id}`
   for S&I on pending studies (`privacy`, `overlaps`) and in a "Checks before you approve" panel.
3. **Follow-up questions** (`POST /api/briefs/{id}/follow-up`, own briefs only): searched and written
   as "<earlier question> Follow-up: <new>", shown as the reader's words with a link back
   (`payload.follow_up_of`, `briefs.follow_up_of`). UI box under the brief summary.
4. **Unanswered questions on the gap map**: briefs now store `question_embedding` (migration
   `20261116120000_question_embeddings.sql`, no extra call); the gap map places each unanswered
   question on the family most common among its 5 nearest approved findings ("closest topic") and adds
   an Unanswered column; older briefs are embedded once when the map loads.
5. **Site redesign to fit the product**: the ask page is a hero band (alerts, composer, example chips),
   a "Your desk" row of live cards (S&I: review queue, analyst desk, unanswered, access; business units:
   analyst replies, access, studies, commissioning) and a four-step "How a brief is made" strip; every
   page head sits on the same quiet band.
6. **Deck v3** (18 slides; new slide 7 "New study in. Askers told."; demo, AI table, risks,
   checkpoints and benefits updated) and **script PDF** (`deck/Evidence-Brief-Pitch-Script.pdf`,
   about 13½ minutes).
7. Tests: `tests/test_review_aids_and_follow_ups.py` (6); 215 pass. Checked live with Bedrock and in
   the browser at 1440 and 390 px, light and dark. Demo data reset afterwards.

### 16 Nov 2026: answer alerts, research-gap map, value counter (uncommitted at time of writing)

1. **"A new study answers your question"** (`app/alerts.py`, migration `20261116100000_answer_alerts.sql`):
   when S&I approves a study, or an owner grants access to one, briefs from the last 180 days that
   retrieved nothing are searched again **as their askers** (RLS) with the brief's own gates
   (`synthesis.answering_sources`, shared with `ask`). A hit writes one `answer_alerts` row per brief
   and an `answer_alert.created` audit entry under the decider. No brief and no model call is made
   for the asker. `GET /api/alerts`, `POST /api/alerts/{id}/read`; the approval and access-decision
   responses carry `answer_alerts`. UI: a green notice on the ask page ("See the answer" asks again),
   a gold count on "Ask a question", and the review page says how many people were told.
   `ALERT_CONFIG` in `config.py` (proposed).
2. **Research-gap map** (`app/gaps.py`, `GET /api/gaps`, page `/gaps`, S&I only): topic families
   (metric family, `_trend` merged; `FAMILY_LABELS`) by place (`GAP_AREAS` from
   `geography.area_type`: Metro Manila, Provincial, Rural, Nationwide), each cell the commissioning
   rule's coverage state; demand = briefs citing the family in 90 days and their teams; "where new
   research would be used first" lists asked-about families still weak somewhere; plus questions no
   readable study answered.
3. **Value counter** (`usage.value`, top of the audit page): answered without an analyst (and the
   share), briefs reusing another team's research and how many studies, earlier questions answered
   by alerts (opened), commissioning objectives already covered, and analyst hours saved as a
   labelled estimate (`VALUE_CONFIG`, 30 minutes per answer, proposed).
4. Header: analysts see eight links, so "Commissioning" and "Gap map" are shorter labels for them;
   menu breakpoints now measured (eight links fit from 1250px, five from 1040px; the five-link header
   overflowed at 1000px before).
5. Tests: `tests/test_alerts_and_gaps.py` (4 tests, incl. no alert for a restricted study until access
   is granted); 209 pass. Checked live with Bedrock: approving SI-2026-104 (Mindanao sari-sari)
   alerted Ben for two earlier questions. The demo database was then reset (`dev_db.py --reset`).
   **Demo:** as Ben ask "How do sari-sari store owners use supplier credit?" (no answer), as Ana
   approve the Mindanao study in the review queue, back as Ben: the alert and badge.

### 15 Nov 2026: header that never wraps, a brief you can scan (uncommitted at time of writing)

1. **Header** (`components/SiteHeader.tsx`): one row at every width. The persona `<select>` (its
   "name · team" text pushed the links onto two or three lines at 900–1440 px) is now a compact
   button (initials, name over team) with a menu of personas; Escape or an outside click closes it.
   Links fold into a Menu button and a panel under the band below 1200 px for S&I's seven links and
   below 1000 px for business units' five (`data-links` on the header). Phones show initials only.
2. **Brief** (`components/BriefView.tsx`, `Citation.tsx`): a sticky "sections" bar (wraps in place
   on phones) marks the section in view; **key figures** show each charted metric's range across
   groups ("41–52%"), read from chart values only, never from the writer; claim and chart sources
   are compact rows (chip, tier, title on one line, method · date · who) and become chips only
   under 640 px; each study is described once under **Studies behind this brief**; the header says
   "16 findings from 4 studies" and "Drafted by Claude Sonnet 5.5" (`modelLabel` in `lib/format.ts`).
   Desktop brief height about the same, but the repeated six-line study cards are gone; phone
   brief 10,400 → 9,400 px.
   **Second pass (16 Nov), summary first:** the brief opens with a summary card (answer, key
   figures, confidence) and "The evidence" as folding sections, each closed under a one-line summary
   computed from the brief (counts, codes, tiers; never model wording). Conflicts, gaps and
   restricted matches start open; in-page links (#studies, #confidence, a key figure, #analyst) open
   their section first. The pinned section bar (chips) stays above the summary and opens a section when clicked. Desktop brief 6,077 → 2,103 px, phone
   10,400 → 2,926 px. **Print fixed:** `@page` A4 margins, a red memo masthead, page 1 is the summary
   and the evidence starts on page 2, every section prints open, charts print as their tables
   (`MetricChart` always renders the table, `print-only` on screen), sources go under each claim
   instead of a rail A4 cannot fit, and no section-level `break-inside: avoid` (it left half-empty
   pages).
3. Checked with Edge via playwright-core at 1440/1200/1100/900/390/340 px, light and dark: no
   horizontal overflow on any page; typecheck and build pass.
4. **Pitch deck** in `deck/`: `Evidence-Brief-Pitch-Deck.pdf` (17 slides on the five required
   sections, Bantay-Baha layout on a light background in BPI red and gold) and `script.md` (about 13–14 minutes, with a live demo
   on slide 6); the earlier score-sheet deck is in `deck/previous/`. New measurement for it: 6 Bedrock briefs (Sonnet 5.5,
   effort medium, Bedrock search): 1 call per brief, ≈4,500 prompt tokens (max 7,200), ≈1,100 output
   (max 1,600), median 11.2 s, 0 fall-backs, 0 rewrites, $0.023 per brief at list prices.
   Hosting guides (untested on real hosts): docs/hosting/ALAMKansya-Hosting-Guide.pdf (Option B, one EC2 server
   with an IAM role + Caddy) and ALAMKansya-Hosting-Guide-Option-D.pdf (free plans: Vercel frontend, Render backend,
   Supabase, Bedrock access keys). frontend/proxy.ts: optional basic auth (DEMO_BASIC_AUTH=user:password) and,
   with BACKEND_SHARED_SECRET, an X-Demo-Key header the backend then requires on every /api call except /api/health
   (config.backend_shared_secret; test in test_api_errors.py). Both off unless set.
   Project name is ALAMKansya (app header, tab titles, print masthead, favicon "A", deck cover, script).
   Team name is Oreo Bread (slides 1 and 18, script). The cover is title only; the close asks S&I and IT/Risk.
   Deck is now for a slides-only video (no live demo, no consultation mentions, no footer captions,
   AI cost only: 20,000 users max, ~2 briefs each, planned at 50,000 briefs ≈ ₱72,500 / US$1,150 a month; pesos first at ₱63 = US$1). Script ≈ 14 min. 19 slides (feasibility and scale on 16, "What it depends on" on 17; aligned with the score sheet): slide 10 compares against an AI-assistant seat for everyone (M365 Copilot US$30 list).
5. **This PC** (not in the repo): `backend/.venv` is Python 3.12 (pgserver has no 3.13 wheels) and its
   `sitecustomize.py` works around Smart App Control blocking psycopg's DLL and a network whose
   NAT64 IPv6 addresses time out (IPv4 first). Bedrock runs through the SSO profile
   `Data_Wave_Participant-291520811820` in `backend/.env.local`.

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
4. **Bedrock search measured and given floors**: `retrieval_eval.py` and `coverage_eval.py` take
   `--provider bedrock` for the Cohere embedder committed in `009ddfa`; retrieval_eval embeds each
   question once per run (sweeps no longer re-embed 300 times). New `EMBEDDER_FLOORS` entry in
   `config.py` (results below). `extraction_eval.py --claude` also runs with `LLM_PROVIDER=bedrock`.
5. **Faster briefs.** `BRIEF_SYSTEM` ends with an explicit check of the qualitative wording rules
   (every rewrite in the first eval was one of them). Sonnet 5.5 at effort **medium** on the same 12
   questions: 0 rewrites, 0 dropped claims, median 12 s, max 52 s, $0.025 per brief, against 2 / 1 /
   18 s / 70 s / $0.042 at high; wording read as good. `LLM_EFFORT=medium` set in the local
   `.env.local` (code default stays `high`). At high effort Sonnet still wrote "all" in focus-group
   claims despite the rule.
6. **"No study covers this" for off-topic questions** (`topicality.answers_question`,
   `TOPICALITY_CONFIG["brief_needs_concept"]`): with a semantic embedder, a question none of whose
   findings shares its concept gets no brief. Bedrock search: blocks 3 of the 4 off-topic questions
   that still retrieved findings, wrongly blocks 0 of 52 answerable ones. Fastembed: blocks 3 of 6;
   before the "merchant = vendor" fix it wrongly blocked 2 (one, a Taglish delivery-rider question,
   had retrieved the wrong studies anyway). Normalisation fixes in `topicality.py`: SMS = text,
   phishing = scam, merchant = vendor, "impersonate" meets "impersonation".
7. **QA gaps from 30 Oct fixed:** the headline honours a place the question names
   (`geography.question_area` / `in_area`; validator `headline_ignores_place` asks for one rewrite
   and never drops; the template writer leads with that place's figures); disputed figures are marked
   wherever they appear (`disputed` on claims and chart bars, a flag chip and dashed bars in the UI;
   the template writer states a disputed pair as one claim; validator `breakdown_hides_conflict`);
   the analyst desk threads a person's follow-ups on the same question (`thread_id`); a new brief that
   joins an open check says "Joined an existing check". A claim's sources list shows one card per
   study page and place (two figures from one table showed two identical cards).
8. **Confidence counts only conflicts that bear on the question** (C6, `confidence.py`): cited by
   the headline, sharing the question's concept, or a generic question. A conflict elsewhere caps at
   Medium with a reason instead of forcing Low.
9. **Demo robustness:** the ask page shows the real step (`GET /api/briefs/progress`, in-memory per
   user, `app/progress.py`), including "Rewriting once: N checks failed"; `/api/health` reports
   `llm_ready` and `search_ready` (free STS / models-list checks, cached a minute) and the ask page
   warns when either is down; an unreachable Bedrock search model now gives a plain 503 instead of a
   500 (asking failed outright when the SSO login expired on 14 Nov).
10. **S&I usage summary** on the audit page (`GET /api/audit/summary`, `app/usage.py`): briefs by
   confidence and team, questions no readable study answered (demand to weigh before commissioning),
   restricted matches, analyst requests, access requests, rewrites and template fall-backs.
11. **Two-part questions** (A9, `retrieval.split_question`): "fees and approval time ..." and "... and
   how do workshops ..." are searched part by part, each with its own relative floor, and merged in
   turn. The 64 eval questions score exactly as before (fastembed micro F1 0.70, hashing 0.63); on
   five two-part checks it rescued the missing half once per embedder (typhoon + delivery-rider
   income with fastembed; QR + scams with hashing) and lost nothing.

**After 5-11, measured with Bedrock** (Sonnet 5.5, effort medium, same 12 questions): 0 fall-backs,
0 rewrites, 0 dropped claims, median 10.5 s, max 20 s, $0.026 per brief. `extraction_eval.py
--claude` with Bedrock on the 37 synthetic reports: every field right, finding recall 99% and page
99% (one finding missed in SI-2026-060, one page wrong in SI-2025-059); the offline extractor is at
100% on these by construction.

**Real reports** (`extraction_eval.py --claude --only public`; only the two BSP PDFs are here, see
below): Sonnet on Bedrock finds 67-83% of the hand-labelled findings, the offline extractor 0%. Its
findings were paraphrases, so pages came out 0-20% right; extraction now also asks for each
finding's `source_text` (the report's own words, copied exactly) and places the finding by that
first (`documents.map_finding_pages`). After that, Consumer Expectations pages were 100% right. The
Financial Inclusion Survey still scores 0% against the labels, but every page it gives contains the
quoted sentence word for word: that report states each finding twice, in its highlights (pp.10-15,
which the labels cite) and in its chapters (pp.22-35, where the model quoted from). One run per
report, so treat the percentages as rough.

**Public PDFs here:** `bsp-financial-inclusion-survey-2021.pdf` and
`bsp-consumer-expectations-survey-q4-2025.pdf` are the labelled reports and are seeded as
PUB-BSP-FIS21 and PUB-BSP-CES25Q4. Four other PDFs in `data/public/pdfs/` are different documents
(the Philippine Development Plan 2023-2028, ADB Asia SME Monitor 2020 volume 1, CGAP's 2015
multi-country synthesis, a CGAP COVID-19 G2P case study) and are deliberately not named as the
labelled reports: their cards cite pages in other documents. The World Bank Enterprise Survey 2023,
ADB Philippines fintech note and the two CGAP Philippines papers are still missing (URLs in
`data/public/manifest.json`; save as `<slug>.pdf`).

**Checked in the browser (14 Nov, 1440 px and a 390 px frame, light and dark):** live progress steps;
the ATM question's headline gives the provincial figures; the cashback brief marks both disputed
pairs on claims and chart bars, with Low confidence; asking it again shows "Joined an existing
check"; the analyst desk nests follow-ups; the audit page shows the usage summary; the mortgage
question gets "No approved study you can read answers this" with no model call. Found and fixed
while checking: duplicate source cards, and a `.thread` class clash that hid the desk indent.

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
| Bedrock Cohere Multilingual v3, floors 0.48 / 0.7 | 0.85 | 0.83 | 0.79 | 0.88 | 0.90 | 0.50 | **0.86** |

On the original 43 questions the larger corpus cost micro F1 0.80 → 0.75 (fastembed) and
0.76 → 0.68 (hashing). The loss is off-topic questions: 0/6 had hits before, now 4/6 (fastembed:
mortgage rates → solar/literacy/typhoon studies at 0.52; retiree savings goals → household budgeting
studies at 0.48). A floor can't remove a 0.52 hit without losing real answers: the tune-half sweep's
best fastembed setting (floor 0.42, relative 0.8) raises held-out micro F1 0.67 → 0.72 and precision
0.72 → 0.88, but drops held-out canonical recall 1.00 → 0.75 and leaves off-topic hits unchanged
there. Floors kept at 0.38 / 0.7: a writer can say a finding doesn't answer the question, but it
can't cite a study retrieval missed. (Hashing's best, 0.2 / 0.6, removes off-topic hits by
cutting paraphrase recall 0.73 → 0.41; not adopted.) Coverage checks are
unchanged (fastembed 13/13, hashing 12/13, public PDFs absent). "Ilan ang nakakatanggap ng pekeng
text mula sa bangko?" finds nothing with either local embedder; fastembed also finds nothing for the
Tagalog fisherfolk and compound-interest questions.
**Bedrock search beats fastembed** once it has its own floors (`EMBEDDER_FLOORS` entry
`bedrock:cohere.embed-multilingual-v3`, added 14 Nov). Without them it ran on the hashing defaults
(0.12) and every off-topic question got hits. Tune-half sweep best 0.48 / 0.8; 0.48 / 0.7 chosen to
keep canonical recall 1.00 on both halves. Held-out micro F1 0.83 vs fastembed 0.67; all 64: 0.86 vs
0.70; Taglish 0.88 vs 0.67. Still failing: 3 of 6 off-topic questions (mortgage rates, tellers'
shifts, retiree savings goals; best match ~0.5) and the metal-card near-miss. Coverage eval
(`--provider bedrock`) 13/13 for every coverage floor 0.50–0.62, so the coverage (0.56) and
restricted-hint (0.52) floors are mid-range picks the cases can't separate. Cost: Cohere is billed
per call (one per finding when seeding, one per question); fractions of a cent for the eval.
Bedrock embeddings also send every question and finding text to AWS, where fastembed sends nothing.

**Cohere Embed v4** (`EMBEDDING_MODEL=global.cohere.embed-v4:0`, 512 dims natively; floors added
14 Nov: 0.34 / 0.7, coverage 0.46, restricted 0.38). Against v3 at its floors, all 64 questions:
micro F1 0.87 vs 0.86 (held-out 0.88 vs 0.83), paraphrase recall 0.94 vs 0.85, precision 0.91 vs
0.79, top result right 0.93 vs 0.83, off-topic questions with hits 1 of 6 vs 3 of 6, but Taglish
recall 0.77 vs 0.88. Coverage 13/13. With the brief concept gate both end with one off-topic question
answered, and v4 wrongly blocks none of 54 answerable ones. v4 gives cleaner English results; v3
handles Taglish better. Switching is two lines in `backend/.env.local` (`EMBEDDING_MODEL`) and a
restart, which re-embeds.

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

1. Sign in to AWS (`aws sso login`), restart, and rerun the brief eval with Sonnet at medium effort
   after the 14 Nov changes; compare Cohere Embed v4 (`cohere.embed-v4:0`, 512 dims natively) with
   the cut-down v3; run `eval/extraction_eval.py --claude` with Bedrock (public PDFs need
   `dev_db.py --fetch-public` first). Write coverage cases that separate coverage floors.
2. Check the CI run in the GitHub Actions tab.
3. Pitch deck: the consultation example before/after, the retrieval table, the four checkpoints,
   documents with page citations, and the AWS slide from `docs/AWS_PLAN.md`.
4. S&I to confirm the new proposed rules: "no study covers this" for off-topic questions, the
   conflict rule for confidence (C6) and the place rule for headlines.
5. Supabase Auth in the frontend for a non-demo deployment (S6).

## Known gaps not to forget

From the final browser QA (30 Oct), still open (the headline place, disputed figures, follow-up
threading and "joined an existing check" were fixed 14 Nov):
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
