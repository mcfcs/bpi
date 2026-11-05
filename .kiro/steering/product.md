---
inclusion: always
---

# Product

`AGENTS.md` (always loaded) is the source of truth: read "What this is" there. This file only adds
what matters when working in Kiro.

- An evidence assistant for BPI Strategy & Insights (S&I), BPI DataWave 2026: business teams ask a
  question; the app answers from approved research their team may read, with citations, computed
  confidence and four human checkpoints.
- How S&I want briefs written (consultation 2): see "Session log" in #[[file:docs/HANDOFF.md]].
  Segment statements, never "the studies disagree"; quantitative first, qualitative as colour.
- All data is synthetic or labelled public research. Never load real BPI data.
- Branch `model-serve` is the AWS experiment (#[[file:docs/AWS_PLAN.md]]); `main` is the demo that
  gets submitted. Keep AWS-only work on `model-serve` until it meets the plan's exit criteria.
