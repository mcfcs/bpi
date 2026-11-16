# Pitch script: ALAMKansya

Oreo Bread · BPI DataWave 2026 · Strategy & Insights challenge · recorded presentation, 10–15 minutes

Say the name as **a-LAM-kan-sya**: *alam* (know) inside *alkansya* (piggy bank).

**Target: about 14 minutes.** Slides only. Slide numbers match
`Evidence-Brief-Pitch-Deck.pdf` (18 slides). The time on each heading is the running total at the end
of that slide, at a relaxed 125 words a minute. The limit is 15 minutes; if a take runs long, drop the last paragraph on slide 8.

## Before you record

- Open `Evidence-Brief-Pitch-Deck.pdf` full screen, one slide per page.
- Suggested split: Speaker 1 slides 1–7, Speaker 2 slides 8–12, Speaker 3 slides 13–18.
- Each speaker reads only the indented lines. Pause a beat on each slide change.

---

## Slide 1 · ALAMKansya (0:28)

> Good day. We're Oreo Bread, and this is ALAMKansya: the alkansya, the piggy bank, of what BPI already knows. Anyone in a business unit can ask a question in plain words and, in about eleven seconds, get an answer from BPI's approved research, with every statement linked to the page it came from.

## Slide 2 · The problem (1:26)

> Research at BPI has one problem that shows up three ways.
>
> First, studies sit in silos. A study belongs to the unit that paid for it, so another unit that could use it often doesn't know it exists. Second, search needs the exact words. SharePoint matches keywords, so a question asked a different way misses the right study. And third, because of both, business units go straight to S&I, and analysts spend their time on questions that existing studies already answer. Sometimes two units even pay for research that reaches the same answer.
>
> Business units compete with fintechs on speed. A decision made without research BPI already owns is slower, more expensive, or both.

## Slide 3 · The slow loop (2:13)

> Say SME Banking wants to know why owners give up on the online loan application. Searching "loan" returns dozens of files. Searching "drop-off" misses the study that says "abandon". The best study belongs to another unit, so they ask for access, one file at a time. Then they ask S&I and wait. Or they decide anyway. Or they pay for new research that repeats what BPI already knows.
>
> Today, nobody can measure how long this takes. And that is the real problem: nobody can see how many questions existing research could already answer.

## Slide 4 · The solution (2:51)

> ALAMKansya turns that loop into one step. Ask in English, Filipino or Taglish. It understands what you mean, not just the words you typed, and looks across every approved study your team is allowed to read. It gives the answer first, then the figures, who was surveyed, and what's missing, and every statement shows where it came from. You can ask a follow-up, or send it to an analyst in one click.

## Slide 5 · The brief on one screen (3:25)

> The answer comes in three wordings: for an executive, for an analyst, or in plain language. The facts are the same in all three. The key figures are copied straight from the studies; the AI never writes a number. The brief also says how sure it is, based on how strong the studies are. And the charts, quotes and gaps are one click away.

## Slide 6 · In use (4:18)

> Here is how it plays out. Ben, in SME Banking, asks why owners drop off loan applications, and gets a brief with its sources. He follows up: "What about owners in Mindanao?" The follow-up remembers what he was asking about, and it's honest: no approved study covers Mindanao owners yet. Then he asks about sari-sari store credit. No approved study answers that either, so the app remembers his question. Later, Ana in S&I reviews a new Mindanao report. The app checks it for personal details and for repeats of past studies, and she approves it. And Ben's screen says: a new study answers your earlier question.

## Slide 7 · The loop (5:07)

> That's the loop we close. Before a new study goes live, the app flags any personal details and shows past studies it repeats, and an analyst decides. Anyone who asked a question the study now answers gets an alert, but only if their team is allowed to read it. And S&I sees it all on a gap map: what teams ask about, what's covered, and where new research would be used first. None of this adds to the AI bill. It reuses work the AI already did when each study and question came in.

## Slide 8 · Role of AI (6:15)

> So where is the AI? Under the hood, this is RAG: retrieval-augmented generation. The AI retrieves the findings that match the question's meaning, and an LLM, a large language model, generates the answer in plain words from only those findings, citing each one. But it's RAG built for a bank.
>
> Everything else is fixed rules. Before any search, the database hides the studies this person may not read. Rules compare the studies, check every sentence the AI writes, and build the charts and the confidence from the studies' own numbers. The AI never makes up a number, never decides that studies disagree, never sees a restricted study, and never approves anything.
>
> Because the AI only ever sees what this person is allowed to read, there is nothing restricted for it to leak, however the question is worded.

## Slide 9 · Why AI here (7:01)

> We used AI only where it clearly beats a simpler tool. Word matching misses questions asked in different words; meaning search finds the right study anyway. Fill-in-the-blank templates can pull in unrelated figures; the LLM sticks to what the studies measured. On real public reports from the BSP, fixed rules missed most of the findings; the LLM pulled them out, each with its page. We'll show the numbers in a moment. And for numbers, access, confidence and personal details, we kept plain rules, because those have to be exact.

## Slide 10 · Versus an AI assistant (8:27)

> A fair question: why not give everyone an AI assistant, like Microsoft 365 Copilot? That's priced per seat: about eighteen hundred and ninety pesos per person, every month, whether they use it or not. For twenty thousand people, that's about thirty-seven million pesos a month. ALAMKansya is priced per question: about one peso and forty-five centavos each, only when someone asks. Even fifty thousand questions a month comes to about seventy-two thousand pesos. It's quicker to trust, too: an assistant drafts in seconds, but you still open the files to check every number. ALAMKansya gives a brief already checked against the studies in about eleven seconds. And the job is different. A general assistant searches every file you can open, drafts included; studies you can't open stay invisible; and it writes the numbers itself. ALAMKansya searches only approved studies, shows what you can ask access to, copies every number from a study, and tells you when new research answers your question. So it sits next to an AI assistant, as the research desk.

## Slide 11 · Risks and safeguards (9:31)

> For each risk, a safeguard. Made-up figures: numbers are copied from the studies, and every source is checked. Focus-group opinions read as if everyone thinks so: the answer has to say "some participants", and can never claim how many people feel that way. A restricted study leaking to another team: it's hidden before the AI sees anything, so the AI can't leak what it never saw. Personal details in a report: flagged, and approval waits. Hidden instructions for the AI inside a report: an analyst reviews every report first. People trusting a brief too much: how sure it is and what's missing come first, and every action is permanently recorded. And bank data only goes to AI models inside AWS, never to an outside AI company.

## Slide 12 · People decide (10:01)

> AI helps, but people make the final call. There are four checkpoints. An analyst approves every study, after the checks for personal details and repeats. The team that owns a study decides every access request. Any brief can go to an analyst in one click. And no new research is ordered until a person sends the request.

## Slide 13 · Benefits (10:30)

> Business units get answers in seconds, find studies from other units, and are told when new research answers an old question. S&I gets fewer repeat questions, catches repeat studies before they go live, and gets a gap map of where to research next. And the bank gets more from research it has already paid for.

## Slide 14 · What we measured (11:20)

> Every number here comes from checking the app against an answer key we wrote first. On the prototype: search finds ninety-four percent of the right studies even when questions use different words, and puts one first ninety-three percent of the time. A full brief typically takes eleven seconds. In eighteen test runs on Amazon's AI service, the AI never failed over to the backup templates. And in about thirty briefs written to try to break it, nothing restricted leaked. This is synthetic test data: it shows the pipeline works. Real value has to be measured with real users.

## Slide 15 · Proving the impact (11:48)

> So we propose an eight-week pilot with about three hundred people: marketing council members, product managers and other executives. The targets: half of questions answered without an analyst, ninety-five percent of statements rated accurate by S&I, zero leaks, and time to a checked answer, compared with today and with an AI assistant.

## Slide 16 · Feasible today, built to scale (12:46)

> It's feasible today, and built to grow. It's already built and working on Amazon's AI service, with two hundred and fifteen automated tests. There's no data to move, no AI to train, and it runs on a standard database and web app that bank IT already knows. And it grows cheaply. Each report is read once, so the AI cost follows questions: about one peso and forty-five centavos a brief. Search stays quick as the library grows, adding a unit is a setup task, and switching AI models is one setting. If the AI is down, the app falls back to fill-in-the-blank templates, with the same sources and checks, so it keeps working.

## Slide 17 · Pilot first, then the whole bank (13:47)

> First, two weeks to set up a BPI test space: staff sign in with their normal BPI accounts, and S&I's approved reports are loaded and reviewed.
>
> Stage one is an eight-week pilot with about three hundred people: marketing council members, product managers and other executives. They ask their real questions here instead of emailing S&I. S&I grades the briefs and answers what the app can't, and we report the targets every week.
>
> Once the pilot meets its targets, stage two is the whole bank: about twenty thousand people, on the same app. At about two briefs each, we plan for fifty thousand briefs a month. The AI costs about seventy-two thousand five hundred pesos a month: under four pesos per person.

## Slide 18 · Close (14:13)

> So our ask: let business units ask the research. From S&I: real questions, with names removed, to test on, and sign-off on our rules. From IT and Risk: a test space on AWS, and approval to use Amazon's AI service and where the data is kept. Thank you.

---

**Timing check:** about 14 minutes at a relaxed pace, about 12½ briskly, inside the 10–15 minute window.
