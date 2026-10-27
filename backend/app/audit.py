"""Audit log writes.

`log()` goes through public.log_audit(), which stamps the caller from the JWT claims, so an API user
cannot write a row on someone else's behalf. On a service connection (scheduled jobs) the actor is
recorded as null.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def log(conn: psycopg.Connection, action: str, entity_type: str, entity_id: Any,
        details: dict | None = None) -> None:
    conn.execute(
        "select public.log_audit(%s, %s, %s, %s)",
        [action, entity_type, None if entity_id is None else str(entity_id), Jsonb(details or {})],
    )
