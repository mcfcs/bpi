# ALAMKansya

*Ang alkansya ng kaalaman.* An evidence assistant for BPI Strategy & Insights: business units ask a question
in plain words and get an answer from approved research, with every statement linked to its study and page.
All data in this repository is synthetic.

This is the `deployment` branch of `mcfcs/bpi`. It holds only what is needed to deploy the prototype; the full
project (slides, tests, evaluation, notes) is on `main`. Render and Vercel deploy from this branch.

| Folder | What |
|---|---|
| `backend/` | FastAPI service (`app/`), the database loader (`scripts/supabase_setup.py`) and a local database helper (`scripts/dev_db.py`) |
| `frontend/` | Next.js 16 web app |
| `supabase/migrations/` | Database schema, row-level security and search functions |
| `data/` | The synthetic studies and reports the database is loaded with |
| `render.yaml` | Render Blueprint for the backend |
| `ALAMKansya-Deployment-Guide.pdf` | The steps below in full, with checks, troubleshooting and what to send the judges |

## How it is hosted

```
Browser ─▶ Vercel (Next.js frontend, open to anyone with the link)
              │  /api/*  + X-Demo-Key
              ▼
           Render (FastAPI backend, free web service)
              │
              ▼
           Supabase (Postgres + pgvector)
```

By default the backend writes briefs from built-in templates and searches by word matching, so it needs no
external AI service. Every brief is still cited, checked and filtered by the reader's permissions.

## 1. Database (Supabase)

1. Create a Supabase project. Under **Connect**, copy the **Session pooler** connection string (port 5432).
2. Copy `backend/.env.supabase.example` to `backend/.env.supabase` and paste the string, with your password.
3. With Python 3.12:
   ```bash
   cd backend
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
   cd ..
   backend/.venv/bin/python backend/scripts/supabase_setup.py --check
   backend/.venv/bin/python backend/scripts/supabase_setup.py
   ```
   It applies every migration and loads 33 approved studies, 6 reports waiting for review and the search data
   for all 160 findings. Running it again is safe.

## 2. Backend (Render)

**Blueprint:** Render → **New → Blueprint** → `mcfcs/bpi`, **Branch** `deployment`. Fill in when asked:

- `DATABASE_URL`: the same Session pooler string.
- `BACKEND_SHARED_SECRET`: a long random string (e.g. `openssl rand -hex 32`). Keep it for Vercel.

Or create a **Web Service** by hand from branch `deployment` with root directory `backend`, build `pip install -r requirements.txt`,
start `uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT`, health check `/api/health`, and the
variables in `backend/.env.example`.

Check: `https://<your-service>.onrender.com/api/health` answers, and
`POST /api/demo/login` without the key returns **401**.

**Keep it awake:** Render's free service sleeps after about 15 idle minutes. Point a free uptime monitor
(e.g. UptimeRobot) at `/api/health` every 5 minutes.

## 3. Frontend (Vercel)

Vercel → **Add New → Project** → `mcfcs/bpi`. Set **Root Directory** to `frontend` (Next.js is detected)
and these environment variables (see `frontend/.env.example`):

```
BACKEND_URL=https://<your-service>.onrender.com
BACKEND_SHARED_SECRET=<the same value as on Render>
```

Vercel builds `main` first. In the project settings, set the **production branch** to `deployment` (under Git, or
Environments → Production), and if your plan allows it **Functions → Region** to Singapore (`sin1`). Then redeploy.

Then open the Vercel URL and pick a persona at the top right. There is no password: anyone with the link can
use the demo. The **How it works** page (`/how`) explains the personas and features.

If long requests time out through Vercel, deploy the frontend as a second Render web service instead: root
`frontend`, build `npm ci && npm run build`, start `npx next start -H 0.0.0.0 -p $PORT`, same variables.

## Resetting the demo

Approving the Mindanao report in the review queue uses up the demo flow. To start again:

```bash
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase db reset --linked
backend/.venv/bin/python backend/scripts/supabase_setup.py --seed-only
```

## Using Claude and Cohere on Amazon Bedrock

With an AWS account that can call Claude Sonnet 5.5 and Cohere Embed v4 in `ap-southeast-1`:

1. On Render, replace `LLM_PROVIDER` / `EMBEDDING_PROVIDER` with the Bedrock block in `backend/.env.example`
   and add the AWS access key.
2. Reload the database with the same search model: in `backend/.env.supabase` set
   `EMBEDDING_PROVIDER=bedrock` and `EMBEDDING_MODEL=global.cohere.embed-v4:0`, then reset as above.

The stored search data and the questions must come from the same model, or search finds nothing.

## Running locally

```bash
# Backend: uses backend/.env (copy backend/.env.example). Or `python backend/scripts/dev_db.py` for a local
# embedded Postgres, which writes backend/.env.local for you.
cd backend && .venv/bin/python -m uvicorn app.main:create_app --factory --port 8000

# Frontend (Node 20.9+): proxies /api to BACKEND_URL (default http://127.0.0.1:8000)
cd frontend && npm ci && npm run dev
```

## Security notes

- Never commit `backend/.env`, `backend/.env.supabase` or `frontend/.env.local`; they are in `.gitignore`.
- Row-level security in the database decides what each persona can read; the backend never bypasses it for
  a user's request.
- The audit log is append-only.
