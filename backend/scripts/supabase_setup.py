"""Set up a hosted database for hosting option D: apply the migrations and load the synthetic corpus.

Reads backend/.env.supabase (git-ignored; see README.md and backend/.env.supabase.example):

    python scripts/supabase_setup.py              check the connection, migrate, seed, embed
    python scripts/supabase_setup.py --check      only check the connection and the search model
    python scripts/supabase_setup.py --seed-only  seed and embed (after `supabase db reset --linked`)
    python scripts/supabase_setup.py --plain-postgres   for a non-Supabase Postgres (Neon, RDS): also
                                                  applies supabase/local/supabase_shim.sql first

On Supabase the migrations run as they are (the auth schema, roles and pgvector already exist), so the
local shim is left out. Re-running is safe: applied migrations are recorded in local_meta and seeding
skips studies that already exist. Only synthetic data is loaded.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

ENV_FILE = BACKEND / ".env.supabase"
PLACEHOLDERS = ("YOUR-PROJECT-REF", "YOUR-PASSWORD", "[YOUR-PASSWORD]")


def load_env(path: Path) -> None:
    """Our own loader: blank values are skipped, so an empty AWS key doesn't shadow the profile."""
    if not path.exists():
        sys.exit(f"Missing {path}. Copy the template from the hosting guide and fill it in.")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value:
            os.environ[key] = value
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        os.environ.pop("AWS_PROFILE", None)  # an explicit key wins over the laptop's sign-in


def database_url() -> str:
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url or any(p in url for p in PLACEHOLDERS):
        sys.exit("Fill in SUPABASE_DB_URL in backend/.env.supabase (Session pooler string, with your password).")
    parsed = urlparse(url)
    if parsed.port == 6543:
        sys.exit("That is the transaction pooler (port 6543). Use the Session pooler string (port 5432).")
    return url


def describe(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.username}@{parsed.hostname}:{parsed.port}{parsed.path}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only check the connection and search model")
    parser.add_argument("--seed-only", action="store_true", help="skip migrations")
    parser.add_argument("--plain-postgres", action="store_true", help="also apply the local Supabase shim")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    args = parser.parse_args()

    load_env(args.env_file)
    url = database_url()

    import psycopg

    from app.db import Database
    from app.embeddings import build_embedder
    from app.jobs.reembed import reembed_all
    from app.migrations import apply_migrations
    from app.seed import seed

    print(f"Database: {describe(url)}")
    with psycopg.connect(url, connect_timeout=15) as conn:
        version = conn.execute("show server_version").fetchone()[0]
        has_vector = conn.execute("select count(*) from pg_available_extensions where name = 'vector'").fetchone()[0]
    print(f"Connected: Postgres {version}; pgvector {'available' if has_vector else 'NOT available'}")
    if not has_vector:
        sys.exit("This database has no pgvector extension.")

    embedder = build_embedder()
    if embedder.name.startswith("bedrock"):
        embedder.embed_query("connection check")
    print(f"Search model: {embedder.name}")
    if args.check:
        print("Check passed. Run again without --check to migrate and seed.")
        return 0

    if not args.seed_only:
        applied = apply_migrations(url, include_local_shim=args.plain_postgres)
        print(f"Migrations applied: {', '.join(applied) if applied else 'none (already up to date)'}")

    db = Database(url, max_size=2)
    try:
        result = seed(db, date.today(), embedder=embedder)
        count = reembed_all(db, embedder)
    finally:
        db.close()
    print(f"Seeded {len(result['studies'])} approved studies; {len(result['pending'])} new report(s) added to the review queue.")
    print(f"Embedded {count} findings with {embedder.name}.")
    print("Done. On Render, set EMBEDDING_PROVIDER / EMBEDDING_MODEL to the same values as this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
