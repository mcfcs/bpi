@AGENTS.md

## Claude Code specifics

- Project agents live in `.claude/agents/`; use `retrieval-evaluator` for search-quality work and
  `brief-qa` for browser checks of the running app.
- The `run-app` skill in `.claude/skills/` starts the stack; prefer it over improvising commands.
- Skills worth loading for this repo: `vercel-react-best-practices` and `web-design-guidelines`
  (frontend), `frontend-design:frontend-design` / `taste-skill:design-taste-frontend` (visual work —
  keep the existing memo direction), `claude-api` (anything touching `backend/app/llm.py`),
  `playwright-cli` (browser verification), `scikit-learn` / `statistical-analysis` (evaluation).
- Commits for this repo: no `Co-Authored-By` trailer (owner's preference). Push to `origin main`.
- At the end of a session, update `docs/HANDOFF.md`.
