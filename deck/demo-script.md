# Live demo script: ALAMKansya

Group Oreo Bread · for a live walkthrough of the app, separate from the slides pitch

**Core demo: about 6 minutes, in three acts.** Business user asks; S&I reviews and approves; the business user is told. Four optional extras (about 1 minute each) follow, for when there is time or a judge asks. The time on each heading is the running total. Spoken lines are in the shaded boxes; everything else is what to click and what to point at.

## Before you start

- **Use fresh demo data.** Approving the Mindanao report uses up the demo. Locally: `./scripts/tailnet.ps1 -Stop`, then `backend/.venv/Scripts/python backend/scripts/dev_db.py --reset`, then `./scripts/tailnet.ps1 -Dev`. Hosted: the reset in the hosting guide.
- **Check the AI is ready.** Open `/api/health` and look for `"llm_ready":true` and `"search_ready":true`. Locally, sign in to AWS first if it has been a few hours.
- **Two browser windows side by side**, both on the app: window 1 signed in as **Ben Santos (SME Banking)**, window 2 as **Ana Reyes (S&I)**. Use the persona menu at the top right. For the extras, a private window for **Carla Mendoza** and **Dino Cruz**.
- Zoom 110%, light theme, notifications off, other tabs closed.
- **Have a backup.** Ask the SME question once before the demo. If the AI is slow on stage, open it from "Your recent briefs" instead of asking live.

---

## Act 1 · Ben asks (2:30)

1. **Window 1, Ben.** Show the ask page: the question box, the example chips, and the "Also for you" cards.
   > I'm Ben, in SME Banking. I have a question, so I just ask it, in plain words.
2. Click the example **"Why do SME owners drop off during online loan applications?"** Point at the progress steps while it works: searching, comparing, writing, checking.
   > It's finding the right findings by meaning, comparing the studies, writing, then checking every sentence.
3. When the brief appears (about 11 seconds), point at the **Answer**, then click **Plain language** and back to **Executive**.
   > The answer comes first, in three wordings. The facts don't change, only the words.
4. Point at the **key figures** (the percentage ranges) and a **citation chip** such as `SI-2026-014 · p.3`.
   > Every figure is copied from a study, never written by the AI, and every statement shows the study and page it came from.
5. Point at the **confidence** line, then click **Who was asked** and **Gaps** in the "On this page" bar.
   > It says how sure it is, who was surveyed, and what's missing.
6. Under the brief, in **Ask a follow-up**, type **"What about owners in Mindanao?"** and send.
   > A follow-up keeps the subject. And it's honest: there's no Mindanao evidence yet.
7. Click **Ask a question** and type **"How do sari-sari store owners use supplier credit?"**
   > Nothing approved answers this. Instead of guessing, it says so, and remembers that I asked.

## Act 2 · Ana reviews (5:00)

8. **Window 2, Ana.** Show the ask page: **Your desk** shows the review queue, analyst questions and the gap map count.
   > Ana is in Strategy and Insights. Her desk shows what's waiting for her.
9. Click **Review queue**, then **Cebu SME Digital Onboarding Focus Groups 2026**. Point at **Checks before you approve**: the highlighted phone number, then the three overlapping studies.
   > Before any study goes live, two checks run. This quote has a phone number, so approval waits until she edits it or confirms it identifies no one. And it overlaps three approved studies, so she can see if it's new research or a repeat.
10. Go back to **Review queue**, open **Mindanao Sari-sari Store Credit Focus Groups 2026**. In **Decision**, type a note, e.g. "Checked findings and pages against the report", and click **Approve**. Point at the message.
    > She approves it. The app says this study answers one question nobody could answer before, and that person has been told. The app never approves on its own.
11. Click **Gap map**. Point at **Where new research would be used first**, the Covered / Partial / Gap cells, and the **Unanswered** column.
    > This is what S&I has never been able to see: what teams ask, what's covered for which places, and where new research would be used first.
12. Click **Audit log**. Point at the **value tiles**, then the newest entries: Ana's approval with her note, and the alert to Ben.
    > Every action is recorded, with who did it and their note. Nobody can edit it. And the app counts its own impact: questions answered without an analyst, research reused across teams.

## Act 3 · Ben is told (6:00)

13. **Window 1, Ben.** Click **Ask a question**. Point at the badge on the menu and the green notice **"A new study answers your earlier question"**. Click **See the answer**.
    > Ben asked before the research existed. Now it exists, and he's told, without anyone remembering to follow up.
14. It asks Ben's question again (about 11 seconds). Point at the new brief and its citation of the Mindanao study.
    > Same question, and this time there's an answer, cited to the new study. That's the loop: ask, review, approve, told.

---

## Extra A · Permissions and access (about 1:15)

1. **Private window, Carla Mendoza (Cards & Payments).** Ask the SME question from Act 1.
   > Carla is in another unit. The SME survey belongs to SME Banking and is restricted.
2. Point at the restricted study: shown only as a **title**, never its content. Click **Request access**, give a reason, **Send request**.
   > The AI never saw that study, so it can't leak it. But Carla learns it exists and can ask for it.
3. Switch the persona to **Dino Cruz (SME Banking approver)** → **Access** → **Approve for Cards & Payments**.
   > The owning team decides. That's a person, not the app.
4. Back as Carla, ask again: the brief now includes the SME survey.

## Extra B · Ask an analyst (about 1:00)

1. **Ben**, on any brief: click **Ask an analyst**. Show the question already drafted from what's missing, and send it.
   > When the brief isn't enough, one click hands it to S&I, with the gaps already written up.
2. **Ana** → **Analyst desk**: open the question and reply. Ben sees the reply on his brief.

## Extra C · Before you commission (about 1:00)

1. **Ben** → **Before you commission**. Title: "SME digital lending refresh". Objectives, one per line, e.g. "Understand why SME owners abandon online loan applications" and "Explore whether SME owners want a named contact person". Run the check.
2. Point at each objective's result (Covered, Covered but old, Partly covered, New problem) and the cited studies.
   > Before paying for new research, it shows what BPI already knows. And nothing is commissioned until a person sends it.

## Extra D · Taglish (about 0:30)

1. **Ben**: ask **"Bakit hindi tinatapos ng mga negosyante ang loan application online?"**
   > Same question in Taglish, and it finds the same studies.
   - Taglish search is weaker than English overall (77% vs 94% in our tests), so use this exact question.

---

## If something goes wrong

- **The brief is slow or fails:** open the backup brief from "Your recent briefs" and carry on. Say: "Here's one we asked earlier."
- **Search error ("Search can't run right now"):** the AWS sign-in expired (local) or the backend is asleep (hosted). Re-sign in or open the health link, then retry.
- **No green alert for Ben:** check Act 1 step 7 happened as Ben, then refresh the page.
- **Mindanao already approved:** the data wasn't reset. Skip step 10 and show the audit log entry instead, then reset before the next demo.
- **After the demo:** reset the data so the next run works.
