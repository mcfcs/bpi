"""Apply the SQL migrations to a local Postgres.

Supabase projects use the Supabase CLI (`supabase db push`) instead. Locally, the shim that stands
in for Supabase's auth schema and roles is applied first.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from .config import REPO_DIR

MIGRATIONS_DIR = REPO_DIR / "supabase" / "migrations"
LOCAL_SHIM = REPO_DIR / "supabase" / "local" / "supabase_shim.sql"


def migration_files(include_local_shim: bool = True) -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return ([LOCAL_SHIM] if include_local_shim else []) + files


def apply_migrations(dsn: str, include_local_shim: bool = True) -> list[str]:
    """Apply any migration not yet recorded in local_meta.applied_migrations. Returns the names applied."""
    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "create schema if not exists local_meta;"
            "create table if not exists local_meta.applied_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        done = {row[0] for row in conn.execute("select name from local_meta.applied_migrations")}
        for path in migration_files(include_local_shim):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into local_meta.applied_migrations (name) values (%s)", [path.name])
            applied.append(path.name)
    return applied
