# Pitch script: Evidence Brief

BPI DataWave 2026 · Strategy & Insights challenge · recorded presentation, 10–15 minutes

**Target: about 13½ minutes.** Slide numbers match `Evidence-Brief-Pitch-Deck.pdf` (18 slides). The time
on each heading is the running total at the end of that slide, at about 140 words a minute. If a
rehearsal runs long, cut slide 14 first (25 s), then demo step 2.

## Before you record

- Start the app (`./scripts/tailnet.ps1 -Dev`), sign in to AWS, and check `http://localhost:10012/api/health`
  shows `"llm_ready":true` and `"search_ready":true`.
- Reset the demo data so the Mindanao report is waiting in the review queue:
  `./scripts/tailnet.ps1 -Stop`, then `backend/.venv/Scripts/python backend/scripts/dev_db.py --reset`, then start again.
- Browser at 110% zoom, light theme, other tabs closed. Have two windows ready: one signed in as
  **Ben** (SME Banking), one as **Ana** (S&I), using the persona menu at the top right.
- Suggested split: Speaker 1 slides 1–7, Speaker 2 slides 8–11, Speaker 3 slides 12–18.

---

## Slide 1 · Evidence Brief (0:25)

> Good day. We're Oreo Bread, and this is Evidence Brief. Anyone in a business unit can ask a
> question in plain words and, in about eleven seconds, get an answer from BPI's approved research,
> with every claim cited to the page it came from.

## Slide 2 · The problem (1:20)

> In our consultations, S&I described one problem three ways.
>
> Studies live in silos: a study belongs to the unit that paid for it, so another unit that could use
> it often doesn't know it exists. Search needs the exact words: SharePoint matches keywords, so a
> question asked differently misses the right study. And so business units ask S&I directly, and
> analysts spend their time on questions existing studies already answer. Sometimes two units even
> commission research that reaches the same answer.
>
> Business units compete with fintechs on speed. A decision made without research BPI already owns is
> slower, more expensive, or both.

## Slide 3 · The slow loop (2:10)

> Say SME Banking wants to know why owners abandon the online loan application. "Loan" returns dozens
> of files. "Drop-off" misses the study that says "abandon". The best study belongs to another unit,
> so they ask for access file by file. Then they ask S&I and wait, or decide anyway, or commission
> research that repeats what BPI already knows.
>
> S&I told us the time this takes can't be quantified. That is the real problem: nobody can see how
> many questions existing research could already answer.

## Slide 4 · The solution (2:50)

> Evidence Brief replaces that loop with one step. Ask in English, Filipino or Taglish. It searches by
> meaning across every approved study your team may read, answers first, shows the figures, who was
> asked and what's missing, and cites every claim. You can ask a follow-up, or send it to an analyst in
> one click.

## Slide 5 · The brief on one screen (3:25)

> The answer comes in three wordings: executive, analyst or plain language, all from the same evidence.
> The key figures come straight from the studies; the AI writes none of them. Confidence is worked out
> from study strength. And everything else, the charts, quotes and gaps, is one click away.

## Slide 6 · Demo (5:55)

> Let me show you.

**[Switch to the browser. About 2½ minutes. Say what you do as you do it.]**

1. **As Ben, SME Banking.** Click the example *"Why do SME owners drop off during online loan applications?"*
   > You can see each step as it works: searching, comparing, writing, checking. Documentation first,
   > approval time second, with ranges from three studies and high confidence.
2. In **Ask a follow-up**, type *"What about owners in Mindanao?"*
   > The follow-up keeps the subject. And it's honest: no approved study covers Mindanao owners yet.
3. **Ask a question**, then type *"How do sari-sari store owners use supplier credit?"*
   > No approved study answers this. Ben's question is remembered.
4. **Switch to Ana, S&I**, open **Review queue**, then *Cebu SME Digital Onboarding Focus Groups 2026*.
   > Before a study goes live, two checks run. A quote contains a phone number, so approval waits
   > until the analyst edits it or confirms it identifies no one. And it overlaps three approved studies,
   > so S&I can see whether this is new research or a repeat.
5. Back to **Review queue**, open *Mindanao Sari-sari Store Credit Focus Groups 2026*, click **Approve**.
   > It answers one earlier question nobody could answer before, and that person has been told.
6. **Switch to Ben.** Point to the badge and the green notice; click **See the answer**.
   > Ben asked before the research existed. Now it's here, and he's told, without anyone remembering
   > to ask again.

**[Back to the slides.]**

## Slide 7 · The loop (6:35)

> That's the loop we close. A new study is checked: personal data flagged, overlap shown, the analyst
> decides. Whoever asked a question it now answers is told, searched as them, under their own access.
> And S&I sees it all on a gap map: what teams ask, what's covered, and where new research would be
> used first. None of this adds an AI call: it's pattern rules, stored search data and code.

## Slide 8 · Role of AI (7:25)

> So where is the AI? In two places. Finding the right findings by meaning, and Claude writing the
> plain-language answer from those findings, citing each one.
>
> Everything else is code and the database. Permissions are enforced before the AI sees anything.
> Code compares the studies, checks every claim the AI writes, and builds the charts and confidence
> from stored values. The AI never supplies a number, never decides that studies disagree, never sees
> a restricted study, and never approves anything.

## Slide 9 · Why AI here (8:05)

> We used AI only where it measurably beats a simpler tool. Word matching finds three in four reworded
> questions; meaning search finds ninety-four percent. Templates pad answers with unrelated figures;
> Claude keeps to what the studies measured. On real BSP reports, rules found almost nothing; Claude
> found up to eighty-three percent of findings, each with its page. For numbers, access, confidence and
> personal data, we kept plain code, because those have to be exact.

## Slide 10 · Risks and safeguards (9:00)

> For each risk, a check. Invented figures: numbers come from the database and every citation is
> checked. Focus-group opinions dressed as statistics: qualitative claims must be hedged. A restricted
> study leaking: the database filters before the AI sees anything, tested on every change. Personal
> data in a report: flagged, and approval waits. Hidden instructions in an upload: an analyst reviews
> every report first. Over-trust: confidence and gaps come first, and every action goes into an audit log
> nobody can edit. And prompts stay inside AWS.

## Slide 11 · People decide (9:35)

> BPI asked for guardrails from day one, and people making the final call. So there are four
> checkpoints: an analyst approves every study, after the privacy and overlap checks; the owning team
> decides every access request; any brief goes to an analyst in one click; and nothing is commissioned
> until a person sends it.

## Slide 12 · Benefits (10:10)

> Business units get answers in seconds, find studies from other units, and are told when new research
> answers an old question. S&I gets fewer repeat questions, duplicates caught at review, and a gap map of
> where to research next. And the bank gets more from research it already paid for.

## Slide 13 · What we measured (10:50)

> On the prototype: ninety-four percent of reworded questions find the right study, ninety-three percent
> as the top result. A full brief takes a median of eleven seconds, and in eighteen runs on Amazon
> Bedrock none fell back to templates. An adversarial test leaked nothing restricted. This is synthetic
> data: it shows the mechanism works. Value has to be measured with real users.

## Slide 14 · Proving the impact (11:15)

> So we propose an eight-week pilot with S&I and one unit: half of questions answered without an
> analyst, ninety-five percent accuracy rated blind by S&I, zero leaks, and time to answer against today.

## Slide 15 · Feasible today (11:55)

> It's feasible today, not someday. It's already built and working on real Bedrock models, with two
> hundred and fifteen automated tests. No data migration: it uses the reports S&I already has. No model
> training. Standard parts bank IT already runs. One AI call per brief, about two US cents.

## Slide 16 · Built to scale (12:35)

> And it scales by design. Cost follows questions, not studies, because each report is processed once.
> Search stays fast as the library grows. A new business unit is a data change, not a code change. The
> model is one setting to swap, with templates if it's down. From five hundred to fifty thousand briefs a
> month, the design stays the same: only the database and an AI bill of twelve to eleven hundred dollars.

## Slide 17 · From one unit to the bank (13:00)

> Two weeks to set up a BPI sandbox. Eight weeks of pilot. Then a department, then the bank.

## Slide 18 · Close (13:25)

> So our ask: let business units ask the research. From S&I, real anonymised questions and sign-off on
> our rules. From IT and Risk, a sandbox and a decision on data residency. Thank you.

---

**Timing check:** about 13½ minutes at a relaxed pace, about 12½ briskly. The demo is the part most
likely to run over; if the AI is slow, open the brief from "Your recent briefs" instead of asking live.
