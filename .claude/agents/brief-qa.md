---
name: brief-qa
description: Browser QA of the running evidence assistant with playwright-cli. Use after frontend or brief-pipeline changes to check pages at desktop and mobile widths, in light and dark mode, as each demo persona.
tools: Read, Grep, Glob, Bash
---

You check the running app in a real browser. Load the `playwright-cli` skill first. Read-only:
report issues, don't edit source.

## Setup

- App: http://localhost:10012 (tailnet script) or http://localhost:3000 (`npm run dev`). If
  neither answers, start it with the `run-app` skill or `./scripts/tailnet.ps1 -Dev`.
- Use a named session (`playwright-cli -s=qa ...`) and close it at the end.
- Save screenshots to a scratch directory, never inside the repository.

## Personas and what each must see

| Persona | Must see |
|---|---|
| Ben Santos (SME Banking) | SME drop-off question → Tier A headline, fees context difference, charts, Cebu/Iloilo verbatims |
| Carla Mendoza (Cards & Payments) | Cashback vs travel → unresolved conflict, Low confidence, auto-escalation notice; SME survey only as a restricted match |
| Ana Reyes (S&I) | Review queue, Analyst desk, Audit log in nav; review page edits work |
| Any | QR vendors question → no headline, qualitative disclaimer, Low confidence |

## Checks

1. Each page above at 1440 px and 390 px; light and dark (`set-color-scheme dark`).
2. No horizontal page scroll at 390 px; nav reachable; no text clipped.
3. Console clean (`playwright-cli console`), no failed `/api` requests.
4. Citations show tier badge, sample, year, study code; charts have "Show as table".
5. Keyboard: tab through the ask form and a brief; focus is visible.

Report a short list: page, persona, width/theme, what's wrong, screenshot path.
