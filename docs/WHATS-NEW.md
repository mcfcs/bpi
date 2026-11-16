# What's new

Changes since commit `01b5f3e` ("Design Improvements + Slides"), 16 Nov 2026. All data is still synthetic.

## New name: ALAMKansya
- The app and the pitch are now called **ALAMKansya**: *alam* (know) inside *alkansya* (piggy bank),
  "ang alkansya ng kaalaman". Each answer is still called an evidence brief.
- The header, browser tab titles and the printed brief all use the new name, and the header and
  favicon mark is now an "A".

## New features

### 1. Answer alerts: "a new study answers your earlier question"
- When S&I approves a study, the app checks every question from the last 180 days that found no
  evidence. If the new study now answers one, the person who asked is told.
- The check searches as that person, so they are only told about studies their team may read.
- They see a green notice on the ask page ("See the answer" / "Dismiss") and a badge on
  "Ask a question" in the header.
- Access works the same way: when an owner approves an access request, the requester is told.
- Every alert is written to the audit log (`answer_alert.created`).

### 2. Gap map (S&I only, header link "Gap map")
- A grid of topics against places (Metro Manila, Provincial, Rural, Nationwide). Each cell says
  Covered, Old, Partial or Gap, using the same rule as the commissioning check.
- For each topic it also shows how many briefs cited it in the last 90 days ("Asked"), which teams
  asked, and how many unanswered questions are closest to it ("Unanswered").
- "Where new research would be used first" picks the top three topics that people ask about but
  that are still weak somewhere.
- Below the grid is the list of questions no readable study answered, each with its closest topic.

### 3. Value counter (Audit log page)
- Tiles for the last 30 days: questions answered without an analyst, share of all questions, answers
  that used another team's study, studies reused, alerts sent and opened, and estimated analyst
  hours saved.
- Hours saved assumes 30 analyst minutes per question. That figure is a proposed default, not
  validated by S&I, and is set in `backend/app/config.py`.

### 4. Personal-data check at review
- Before a study is approved, its findings are scanned for phone numbers, emails, account numbers,
  tax IDs, addresses and personal names.
- Approval is blocked until the analyst edits the flagged finding or ticks "I checked the flagged
  findings and they identify no one". The tick is recorded in the audit log.
- It uses pattern rules only: no AI call, and nothing leaves the server.
- To show it in the demo, the synthetic Cebu report now includes a quote with a made-up 0917 number.

### 5. Overlap check at review
- On the same review page, S&I sees which approved studies the new one overlaps. Each overlap is
  labelled a repeat, a newer wave, or the same topic with different people or places.
- Code compares who was asked, where and when. Figures the studies share are shown side by side,
  taken from the database. No AI call.

### 6. Follow-up questions
- Under every brief there is an "Ask a follow-up" box, e.g. "What about owners in Mindanao?". The
  follow-up keeps the original subject, so the user doesn't have to retype it.
- The new brief links back to the first one ("Follow-up to …").
- Users can only continue their own briefs.

## Design changes
- **Ask page redesigned.** It now opens with a band holding the alerts, the ask box and example
  questions as chips. Under it are "Your desk" cards and a short "How a brief is made" strip.
  - S&I cards: review queue, analyst desk, gap map, access decisions.
  - Business-unit cards: analyst replies, access requests, studies, the commissioning check.
  - A card whose number is waiting on you shows that number in red.
- **Every page** opens on the same grey header band, so the site reads as one product.
- **Header**: new "Gap map" link for S&I, and the unread-alert badge.
- **Review page**: a "Checks before you approve" panel with the personal-data and overlap checks.
- **No more coloured side stripes on boxes.** Alerts, review checks, analyst replies, conflicts and
  the gap map now use plain or thin full borders. The phone menu marks the current page with shading
  instead of a gold stripe.

## Pitch deck and script (`deck/`)
- **Slides-only video.** No live demo: slide 6 ("In use") is narrated from screenshots. Nothing
  mentions consultations or what BPI "asked for".
- **Deck: 18 slides.** Feasibility and scale share one slide (16).
  - New slide 10, "Why not give everyone an AI assistant?", compares ALAMKansya with a seat for all
    20,000 users (Microsoft 365 Copilot at its US$30 list price): about ₱37.8M a month against
    about ₱72,500, plus what each one searches, shows and checks.
  - New slide 7, "New study in. Askers told.", covers the review checks, the alert and the gap map.
  - The AI-versus-simpler-tool, risks, checkpoints and benefits slides now include the new features.
  - The test count on the slides is now 215.
- **Cover slide** shows only the title, a one-line subtitle and the team name, **Oreo Bread**.
- **Closing slide** asks S&I and IT/Risk only; the "From us" box is gone.
- **New look, less template-like.** There are no side stripes, tinted cards or drop shadows; sections
  sit under thin black rules. Key lines and the two AI steps are dark panels. Footers show only the
  page number, and the small source captions are gone.
- **Cost is AI only.** Hosting cost is removed. The deck assumes at most 20,000 users at about
  2 briefs each a month (about 40,000 briefs). Planning for 50,000 briefs gives an AI cost of about
  ₱72,500 (US$1,150) a month, under ₱4 per user. Costs are shown in pesos first, at ₱63 per US$1
  (early November 2026 rate).
- **Plain wording throughout.** No technical terms on the slides or in the script: no "embeddings",
  "row-level security", "tokens" or "templates fell back". Scores are shown as percentages.
- **Script**: rewritten for the slides-only flow, about 14 minutes relaxed and 12½ brisk, and
  exported as `Evidence-Brief-Pitch-Script.pdf`.

## For developers
- **Database**: two new migrations.
  - `answer_alerts`, with RLS so users read their own alerts.
  - `briefs.question_embedding` and `briefs.follow_up_of`.
  - Run `backend/.venv/Scripts/python backend/scripts/dev_db.py` to apply them, or add `--reset`
    to get clean demo data.
- **New backend modules**: `alerts.py`, `gaps.py`, `privacy.py`, `overlap.py`.
- **New routes**:
  - `GET /api/alerts`
  - `POST /api/alerts/{id}/read`
  - `GET /api/gaps`
  - `POST /api/briefs/{id}/follow-up`
  - `GET /api/studies/{id}` now includes `privacy` and `overlaps` for pending studies, for S&I only.
- **New settings** in `config.py`, all proposed defaults: `ALERT_CONFIG`, `VALUE_CONFIG`,
  `GAP_CONFIG`, `PRIVACY_PATTERNS`, `OVERLAP_CONFIG`.
- **Tests**: 10 new, 215 in total, all passing.
- **Unchanged guarantees**: the AI still sees only what the user may read, never supplies a number,
  and never approves anything. None of the new features adds an AI call.
