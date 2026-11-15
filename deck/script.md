# Pitch script: Evidence Brief (BPI DataWave 2026)

Recording target: **about 13–14 minutes** (the limit is 10–15). Slide numbers match
`Evidence-Brief-Pitch-Deck.pdf`. The clock on each heading is the running total at the end of that
slide. Spoken pace is about 140 words a minute; if you run long, cut slide 13 (~30 s) first,
then shorten the demo.

Before recording:
- Start the app (`./scripts/tailnet.ps1`) and sign in to AWS, then open `http://localhost:10012/api/health`
  and check that it says `"llm_ready":true`.
- Ask the demo question once beforehand, so the brief is already in "Your recent briefs" if the live
  call is slow.
- Close other tabs, set the browser zoom to 110%, and use light mode.

If several people present, a natural split is: Speaker 1 slides 1–6 (problem, solution, demo),
Speaker 2 slides 7–10 (AI and trust), Speaker 3 slides 11–17 (benefits, feasibility, scale, close).

---

## Slide 1 · Evidence Brief (0:30)

> Good day. We're [team name], and this is Evidence Brief.
>
> BPI's Strategy and Insights team has years of approved customer research. Our tool lets anyone in
> a business unit ask a question in plain words and get an answer from that research in about
> eleven seconds, with every claim cited to the page of the report it came from.

## Slide 2 · The problem (1:30)

> In our consultations, S&I described the same problem three ways.
>
> First, studies live in silos. A study belongs to the unit that paid for it, so another unit that
> could use it often doesn't know it exists.
>
> Second, search needs the exact words. SharePoint matches keywords, so a question asked
> differently misses the right study, and a keyword can match a report that's about something else.
>
> Third, because of both, business units ask S&I directly, and analysts spend their time answering
> questions that existing studies already cover. Sometimes two units even commission research that
> reaches the same answer.
>
> And business units are competing with fintechs on speed. A decision made without the research BPI
> already owns is slower, more expensive, or both.

## Slide 3 · The slow loop (2:30)

> Here is that loop. Say SME Banking wants to know why owners abandon the online loan application.
>
> They search "loan" and get dozens of files. They search "drop-off" and miss the study that says
> "abandon". The best study belongs to another unit, so they have to ask for access, file by file.
> So they ask S&I, and wait in the queue with every other request. Or they decide anyway, or
> commission research that repeats what BPI already knows.
>
> When we asked S&I how long this takes, they told us it can't be quantified. That is the real
> problem: nobody can see how many questions the existing research could already answer.

## Slide 4 · The solution (3:15)

> Evidence Brief replaces that loop with one step.
>
> You ask in English, Filipino or Taglish. The system searches by meaning, not keywords, across every
> approved study your team is allowed to read. It writes the answer first, then shows the figures,
> who was asked, and what the evidence doesn't cover. Every claim cites the study and the page. And
> if it isn't enough, one click sends the question to an S&I analyst.

## Slide 5 · The brief on one screen (4:00)

> This is what comes back. At the top, the answer, written for an executive, an analyst, or in
> plain language: same evidence, different wording.
>
> Below it, the key figures. These numbers come straight from the studies in the database; the AI
> doesn't write any of them. Then the confidence, worked out from how strong the studies are. And
> under that, the evidence: charts, quotes, gaps, all one click away. It prints as a one-page memo
> you can forward.

## Slide 6 · Demo (6:15)

> Let me show you.

**[Switch to the browser. About 2¼ minutes. Say what you do as you do it.]**

1. **As Ben, SME Banking** (persona menu, top right). Click the example question *"Why do SME owners
   drop off during online loan applications?"*
   > While it works, you can see each step: searching, comparing, writing, checking.
2. When the brief appears:
   > The answer: documentation requirements first, unclear approval time second. These ranges come
   > from three studies. High confidence, because one of them is a large, recent survey.
3. Open **"It depends on who was asked"**.
   > The studies don't disagree. They asked different people: different ages, Metro Manila versus
   > nationwide, different years. The system works that out in code and says so, instead of calling
   > it a conflict.
4. Click a citation chip such as **SI-2026-014 · p.3**.
   > Every citation opens the report at the page it came from.
5. **Switch to Carla, Cards & Payments**, and ask the same question.
   > Carla's team isn't allowed to read the SME survey. She sees its title under "Restricted
   > matches", nothing from inside it, and she can ask the owning team for access. They decide.
6. **Switch to Ana, S&I**, and open **Review queue**.
   > New reports land here. The AI drafts the study card and findings, but nothing is searchable
   > until an analyst approves it.

**[Back to the slides.]**

## Slide 7 · Role of AI (7:15)

> So where is the AI? In two places only.
>
> Step two: finding the right findings by meaning. Step four: Claude writing the plain-language
> answer from those findings, citing each one.
>
> Everything else is code and the database. Permissions are enforced by the database before the AI
> sees anything. Code compares the studies and scores their strength. Code checks every claim the
> AI writes and drops any that fail. And the charts and confidence come from stored values.
>
> The AI never supplies a number, never decides that studies disagree, never sees a restricted
> study, and never approves anything.

## Slide 8 · Why AI here (8:00)

> We only used AI where it measurably beats a simpler tool.
>
> For finding studies, plain word matching found three in four reworded questions; meaning search
> finds ninety-four percent. For writing, templates are fast but pad the answer with unrelated
> figures; Claude keeps to what the studies measured. For reading real reports, rules found almost
> nothing in two public BSP reports; Claude found up to eighty-three percent of the findings, each
> with its page.
>
> For numbers, access and confidence we kept plain code, because those have to be exact and
> explainable.

## Slide 9 · Risks and safeguards (9:00)

> We looked at what could go wrong, and built a check for each.
>
> An invented figure: numbers come from the database, and every citation is checked. Focus-group
> opinions dressed up as statistics: qualitative claims must be hedged and can never say how common
> a view is. A restricted study leaking: the database filters before the AI sees anything, and we
> run red-team tests on every change. Instructions hidden in an uploaded report: new reports wait
> for an analyst's review. People over-trusting the brief: confidence and gaps come first, an
> analyst is one click away, and every action goes into an audit log nobody can edit. And data
> residency: prompts stay inside AWS, and the model is a setting we can swap.

## Slide 10 · People decide (9:45)

> BPI told us: guardrails from day one, and humans make the final decision. So there are four
> checkpoints.
>
> An analyst approves every study before it's searchable. The owning team decides every access
> request. Any brief can go to an analyst in one click, with the question already drafted. And
> before new research is commissioned, the tool checks what's already covered, but nothing is sent
> until a person sends it.

## Slide 11 · Benefits (10:30)

> What does this change?
>
> Business units get an answer in seconds, in their own words, including studies from other units
> they didn't know about. S&I gets fewer repeat questions and more time for new research, plus data
> on which questions no study answers yet. And the bank gets more value from research it has
> already paid for, fewer duplicate studies, and one governed, auditable way to reach evidence.

## Slide 12 · What we measured (11:15)

> Here is what we've measured on the prototype. Ninety-four percent of reworded questions find the
> right study, and ninety-three percent get it as the top result. A full cited brief takes a median
> of eleven seconds. In eighteen runs on Amazon Bedrock, none fell back to templates. Claude pulled
> ninety-nine percent of findings from thirty-seven reports with the right page, and an adversarial
> test of about thirty briefs leaked nothing restricted.
>
> To be clear, this is on synthetic data. It shows the mechanism works. Real value has to be
> measured with real users.

## Slide 13 · Proving the impact (11:45)

> So we propose an eight-week pilot with S&I and one business unit, on real anonymised questions.
> We'd track the share of questions answered without an analyst, aiming for half; accuracy and
> citations above ninety-five percent as rated by S&I, blind; zero restricted leaks; and time to a
> first answer against today.

## Slide 14 · Feasible today (12:30)

> This is feasible today, not someday. It's already built and working end to end on real Bedrock
> models, with two hundred and five automated tests. It needs no data migration: it uses the PDF
> reports S&I already has. It needs no model training: the models are off the shelf, on Amazon
> Bedrock, so prompts stay in AWS. And it's built from standard parts bank IT already runs.
>
> We measured the cost: one AI call per brief, about four and a half thousand tokens in and eleven
> hundred out, roughly two US cents.

## Slide 15 · Built to scale (13:15)

> And it scales well, by design. Cost follows questions, not studies: a report is processed once,
> and every brief costs about two cents however big the library gets. Search stays fast because the
> indexes live in the database. Adding a business unit is a data change, not a code change, since
> teams and access rules are just rows. It grows on standard AWS services. It doesn't depend on one
> AI model: we can swap it with a setting, and if the AI is down, briefs still come from templates.
>
> From five hundred to fifty thousand briefs a month, the core design stays the same. Only the
> database and the AI bill grow: from about twelve dollars to about eleven hundred a month.

## Slide 16 · From one unit to the bank (13:50)

> The roll-out: two weeks to set up a BPI sandbox, sign-in and the reports. An eight-week pilot with
> S&I and one unit. Then a department of five units, then the bank.

## Slide 17 · Close (14:15)

> So our ask: let business units ask the research.
>
> From S&I, real anonymised questions and sign-off on our rules. From IT and Risk, an AWS sandbox
> and a decision on data residency. From us, the working prototype and weekly pilot numbers.
>
> Thank you.

---

Timing check: the sections add up to about 14¼ minutes at a relaxed pace, and about 13 when
delivered briskly. If a rehearsal runs past 14½ minutes, drop slide 13 and shorten demo steps 4 and 6.
