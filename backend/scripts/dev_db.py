"""Local development database: an embedded Postgres with pgvector (pgserver), migrated and seeded
with the synthetic corpus. Writes DATABASE_URL and demo settings to backend/.env.local.

    python scripts/dev_db.py           start (or reuse) the server, migrate, seed
    python scripts/dev_db.py --stop    stop the server
    python scripts/dev_db.py --reset   delete the local data and start again
    python scripts/dev_db.py --fetch-public   first download the public research PDFs (data/public)
    python scripts/dev_db.py --no-public      leave out public research studies

Public research reports are seeded as "Public source" studies only when their PDFs are already in
data/public/pdfs/ (see scripts/fetch_public_reports.py); without them the synthetic demo is unchanged.

For a Supabase project, apply supabase/migrations with the Supabase CLI instead.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pgserver  # noqa: E402

from app.config import BACKEND_DIR, DEV_JWT_SECRET, _load_env_file  # noqa: E402
from app.db import Database  # noqa: E402
from app.embeddings import build_embedder  # noqa: E402
from app.jobs.reembed import reembed_all  # noqa: E402
from app.migrations import apply_migrations  # noqa: E402
from app.seed import seed  # noqa: E402


def data_dir() -> Path:
    if os.environ.get("EMBEDDED_PGDATA"):
        return Path(os.environ["EMBEDDED_PGDATA"])
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    # Kept outside the repository: Postgres tools are unreliable with spaces in the data path.
    return base / "si-evidence-assistant" / "pgdata"


def write_env(uri: str) -> Path:
    env_path = BACKEND_DIR / ".env.local"
    lines = [line for line in (env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else [])
             if not line.startswith(("DATABASE_URL=", "DEMO_MODE=", "SUPABASE_JWT_SECRET="))]
    lines += [f"DATABASE_URL={uri}", "DEMO_MODE=true", f"SUPABASE_JWT_SECRET={DEV_JWT_SECRET}"]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--fetch-public", action="store_true", help="download public report PDFs first")
    parser.add_argument("--no-public", action="store_true", help="do not seed public research studies")
    args = parser.parse_args()
    pgdata = data_dir()

    if args.stop or args.reset:
        if pgdata.exists():
            pgserver.get_server(str(pgdata), cleanup_mode="stop").cleanup()
            print("Stopped the local database.")
        if args.stop:
            return 0
        shutil.rmtree(pgdata, ignore_errors=True)
        print(f"Deleted {pgdata}.")

    if args.fetch_public and not args.no_public:
        from scripts.fetch_public_reports import fetch
        fetched = fetch()
        print(f"Public reports: {sum(1 for s in fetched.values() if s == 'ok')} of {len(fetched)} available.")

    pgdata.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(pgdata), cleanup_mode=None)  # keeps running after this script exits
    uri = server.get_uri()
    applied = apply_migrations(uri)
    print(f"Database: {uri}")
    print(f"Migrations applied: {', '.join(applied) if applied else 'none (already up to date)'}")

    _load_env_file(BACKEND_DIR / ".env.local")  # EMBEDDING_PROVIDER / EMBEDDING_MODEL
    embedder = build_embedder()
    db = Database(uri, max_size=2)
    try:
        result = seed(db, date.today(), embedder=embedder, include_public=not args.no_public)
        # Seeding skips studies that already exist, so re-embed everything: stored vectors must
        # come from the same model as query vectors.
        count = reembed_all(db, embedder)
    finally:
        db.close()
    print(f"Seeded {len(result['studies'])} approved studies; {len(result['pending'])} new report(s) in the review queue.")
    if not args.no_public:
        print(f"Public research studies: {len(result['public'])} "
              f"({', '.join(result['public']) or 'none; run with --fetch-public to download the PDFs'}).")
    print(f"Embedded {count} findings with {embedder.name}.")
    print(f"Wrote {write_env(uri)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
