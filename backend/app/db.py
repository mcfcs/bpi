"""Database access.

Every request that touches study content runs in `as_user()`: a transaction that switches to the
`authenticated` role and sets the caller's JWT claims, so Postgres row-level security applies
exactly as it does through Supabase's API. `as_service()` keeps the connection's own privileges
and is only for seeding and scheduled jobs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, dsn: str, max_size: int = 8):
        self.dsn = dsn
        self.pool = ConnectionPool(
            dsn, min_size=1, max_size=max_size, kwargs={"row_factory": dict_row}, open=True
        )

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def as_user(self, user_id: str, email: str | None = None) -> Iterator[psycopg.Connection]:
        claims = {"sub": user_id, "email": email, "role": "authenticated"}
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("select set_config('request.jwt.claims', %s, true)", [json.dumps(claims)])
            conn.execute("set local role authenticated")
            yield conn

    @contextmanager
    def as_service(self) -> Iterator[psycopg.Connection]:
        with self.pool.connection() as conn, conn.transaction():
            yield conn
