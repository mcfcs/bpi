---
name: run-app
description: Start, stop or restart the S&I evidence assistant (embedded Postgres, FastAPI backend, Next.js frontend) locally or for Tailscale devices on port 10012. Use when asked to run, launch, serve, demo or screenshot the app.
---

# Run the evidence assistant

## One command (Windows, PowerShell, from the repo root)

```powershell
./scripts/tailnet.ps1            # production build, http://localhost:10012 and http://<tailscale-ip>:10012
./scripts/tailnet.ps1 -Dev       # hot reload instead of a production build
./scripts/tailnet.ps1 -SkipBuild # reuse the last build
./scripts/tailnet.ps1 -Stop      # stop frontend, backend and database
```

The script starts the embedded database (`backend/scripts/dev_db.py`, idempotent), runs the backend
on `127.0.0.1:8000` only, and serves Next on `0.0.0.0:10012`. The browser only talks to Next, which
proxies `/api/*` to the backend. Logs go to `.run/` (git-ignored).

A Windows Firewall rule "BPI Evidence Assistant (Tailscale) 10012" (Tailscale addresses only) must
exist for other tailnet devices to connect; `./scripts/tailnet.ps1 -OpenFirewall` adds it from an
elevated PowerShell.

## Manually (any OS)

```bash
cd backend
.venv/Scripts/python scripts/dev_db.py                                    # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000
cd ../frontend && npm run dev                                             # http://localhost:3000
```

First run only: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`
and `cd frontend && npm ci`. For semantic search also `pip install -r requirements-semantic.txt` and
set `EMBEDDING_PROVIDER=fastembed` in `backend/.env.local`, then `dev_db.py --reset` to re-embed.

## Check it works

`curl -s http://localhost:10012/api/health` → `{"ok":true,"llm":...,"embedder":...}`. Then sign in
as a demo persona in the browser (playwright-cli) and ask an example question.
