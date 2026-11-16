# Pitch script: ALAMKansya

Oreo Bread · BPI DataWave 2026 · Strategy & Insights challenge · recorded presentation, 10–15 minutes

Say the name as **a-LAM-kan-sya**: *alam* (know) inside *alkansya* (piggy bank).

**Target: about 14½ minutes.** Slides only. Slide numbers match
`Evidence-Brief-Pitch-Deck.pdf` (19 slides). The time on each heading is the running total at the end
of that slide, at a relaxed 125 words a minute. The limit is 15 minutes; if a take runs long, shorten slide 6 to its first and last sentences.

## Before you record

- Open `Evidence-Brief-Pitch-Deck.pdf` full screen, one slide per page.
- Suggested split: Speaker 1 slides 1–7, Speaker 2 slides 8–12, Speaker 3 slides 13–19.
- Each speaker reads only the indented lines. Pause a beat on each slide change.

---

## Slide 1 · ALAMKansya (0:28)

> Good day. We're Oreo Bread, and this is ALAMKansya: the alkansya, the piggy bank, of what BPI already knows. Anyone in a business unit can ask a question in plain words and, in about eleven seconds, get an answer from BPI's approved research, with every statement linked to the page it came from.

## Slide 2 · The problem (1:04)

> Research at BPI has one problem that shows up three ways. Studies sit in silos: a study belongs to the unit that paid for it, so other units rarely know it exists. Search needs the exact words: a question asked differently misses the right study. So business units go straight to S&I, and analysts re-answer questions existing studies already cover. Meanwhile, business units compete with fintechs on speed.

## Slide 3 · The slow loop (1:39)

> Say SME Banking wants to know why owners give up on the online loan application. "Loan" returns dozens of files; "drop-off" misses the study that says "abandon". The best study belongs to another unit, so they ask for access file by file, then wait for S&I, or decide anyway, or pay for research BPI already has. And nobody can see how many questions existing research could already answer.

## Slide 4 · The solution (2:13)

> ALAMKansya fixes each cause. Silos: it searches every approved study from every team, and shows the ones you can't open yet, with a button to ask for access. Exact words: it matches meaning, in English, Filipino or Taglish. The queue: you get the answer first, with every statement linked to its source, and one click sends it to an analyst when that isn't enough.

## Slide 5 · The brief on one screen (2:47)

> The answer comes in three wordings: for an executive, for an analyst, or in plain language. The facts are the same in all three. The key figures are copied straight from the studies; the AI never writes a number. The brief also says how sure it is, based on how strong the studies are. And the charts, quotes and gaps are one click away.

## Slide 6 · In use (3:32)

> Ben, in SME Banking, asks why owners drop off loan applications and gets a brief with its sources. He follows up: "What about owners in Mindanao?" It keeps the subject, and it's honest: no approved study covers Mindanao owners yet. Then he asks about sari-sari store credit. Nothing answers that either, so the app remembers his question. Later, Ana in S&I reviews a new Mindanao report; the app checks it for personal details and repeats, and she approves it. Ben's screen says: a new study answers your earlier question.

## Slide 7 · The loop (4:21)

> That's the loop we close. Before a new study goes live, the app flags any personal details and shows past studies it repeats, and an analyst decides. Anyone who asked a question the study now answers gets an alert, but only if their team is allowed to read it. And S&I sees it all on a gap map: what teams ask about, what's covered, and where new research would be used first. None of this adds to the AI bill. It reuses work the AI already did when each study and question came in.

## Slide 8 · Role of AI (5:17)

> So where is the AI? Under the hood, this is RAG: retrieval-augmented generation. The AI retrieves the findings that match the question's meaning, and an LLM, a large language model, generates the answer in plain words from only those findings, citing each one. But it's RAG built for a bank.
>
> Everything else is fixed rules. Before any search, the database hides the studies this person may not read. Rules compare the studies, check every sentence the AI writes, and build the charts and the confidence from the studies' own numbers. The AI never makes up a number, never decides that studies disagree, never sees a restricted study, and never approves anything.

## Slide 9 · Why AI here (6:03)

> We used AI only where it clearly beats a simpler tool. Word matching misses questions asked in different words; meaning search finds the right study anyway. Fill-in-the-blank templates can pull in unrelated figures; the LLM sticks to what the studies measured. On real public reports from the BSP, fixed rules missed most of the findings; the LLM pulled them out, each with its page. We'll show the numbers in a moment. And for numbers, access, confidence and personal details, we kept plain rules, because those have to be exact.

## Slide 10 · Versus an AI assistant (7:04)

> A fair question: why not give everyone an AI assistant, like Microsoft 365 Copilot? That's priced per seat: about eighteen hundred and ninety pesos a person every month, used or not. For twenty thousand people, about thirty-seven million pesos a month. ALAMKansya is priced per question, about one peso forty-five each; even fifty thousand questions a month is about seventy-two thousand pesos. It's quicker to trust, too: an assistant drafts in seconds, but you still open the files to check every number; ALAMKansya's brief arrives already checked, in about eleven seconds. And the job is different: an assistant searches every file you can open, hides studies you can't, and writes numbers itself. So ALAMKansya sits next to it, as the research desk.

## Slide 11 · Risks and safeguards (8:19)

> For each risk, a safeguard. Made-up figures: numbers are copied from the studies, and every source is checked. Focus-group opinions read as if everyone thinks so: the answer has to say "some participants", and can never claim how many people feel that way. Bias toward the places and groups studies cover most: every brief says who was surveyed and where, and gaps are named, not filled in. A restricted study leaking to another team: it's hidden before the AI sees anything, so the AI can't leak what it never saw. Personal details in a report: flagged, and approval waits. Hidden instructions for the AI inside a report: an analyst reviews every report first. People trusting a brief too much: how sure it is and what's missing come first, and every action is permanently recorded. And bank data only goes to AI models inside AWS, never to an outside AI company.

## Slide 12 · People decide (8:58)

> AI helps, but people make the final call. There are four checkpoints. An analyst approves every study, after the checks for personal details and repeats. The team that owns a study decides every access request. Any brief can go to an analyst in one click. And no new research is ordered until a person sends the request. Every decision lands in an audit log, with the person's name and note, and nobody can edit it.

## Slide 13 · Benefits (9:35)

> For business units, today means searching, asking for files and waiting on S&I; now it's a cited answer in about eleven seconds, including studies from other units, and an alert when new research answers an old question. For S&I, fewer repeat questions, repeat studies caught before they go live, and a gap map of where to research next. And the bank gets more from research it has already paid for.

## Slide 14 · What we measured (10:25)

> Every number here comes from checking the app against an answer key we wrote first. On the prototype: search finds ninety-four percent of the right studies even when questions use different words, and puts one first ninety-three percent of the time. A full brief typically takes eleven seconds. In eighteen test runs on Amazon's AI service, the AI never failed over to the backup templates. And in about thirty briefs written to try to break it, nothing restricted leaked. This is synthetic test data: it shows the pipeline works. Real value has to be measured with real users.

## Slide 15 · Proving the impact (11:07)

> So we propose an eight-week pilot with about three hundred people: marketing council members, product managers and other executives. The targets: half of questions answered without an analyst, ninety-five percent of statements rated accurate by S&I, zero leaks, and time to a checked answer, compared with today and with an AI assistant. And the app measures its own impact: the audit page already counts questions answered without an analyst, studies reused across teams, alerts opened, and an estimate of analyst hours saved.

## Slide 16 · Feasible today, built to scale (12:11)

> It's feasible today, and built to grow. It's already built and working on Amazon's AI service, with two hundred and fifteen automated tests. There's no data to move, no AI to train, and it runs on a standard database and web app that bank IT already knows. And it grows cheaply. Each report is read once, so the AI cost follows questions: one LLM call per brief, about four thousand five hundred tokens in and eleven hundred out, about one peso and forty-five centavos. Search stays quick as the library grows, adding a unit is a setup task, and switching AI models is one setting. If the AI is down, the app falls back to fill-in-the-blank templates, with the same sources and checks, so it keeps working.

## Slide 17 · What it depends on (12:49)

> To be clear about what this depends on. We assume about two briefs per person a month, list prices, and sixty-three pesos to the dollar. Today it reads text PDFs, not scans; Taglish search is weaker than English; and our thresholds still need S&I's sign-off. And it depends on people and partners: S&I reviewing each new report, teams deciding access, Amazon's AI service, and BPI deciding where the data may be kept.

## Slide 18 · Pilot first, then the whole bank (14:05)

> First, two weeks to set up a BPI test space: staff sign in with their normal BPI accounts, and S&I's approved reports are loaded and reviewed.
>
> Stage one is an eight-week pilot with about three hundred people: marketing council members, product managers and other executives. They ask their real questions here instead of emailing S&I. S&I grades the briefs and answers what the app can't, and we report the targets every week.
>
> Once the pilot meets its targets, stage two is the whole bank: about twenty thousand people, on the same app. At about two briefs each, we plan for fifty thousand briefs a month: about two hundred and eighty million tokens, and about seventy-two thousand five hundred pesos, under four pesos per person. As use grows, tokens and cost rise with questions, the servers and database scale up on AWS, and S&I's review work grows with new reports, not with users.

## Slide 19 · Close (14:31)

> So our ask: let business units ask the research. From S&I: real questions, with names removed, to test on, and sign-off on our rules. From IT and Risk: a test space on AWS, and approval to use Amazon's AI service and where the data is kept. Thank you.

---

**Timing check:** about 14½ minutes at a relaxed pace, about 12½ briskly, inside the 10–15 minute window.
