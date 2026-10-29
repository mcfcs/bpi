"""Recompute every finding's embedding with the configured embedder.

Stored vectors and query vectors must come from the same model. Run this after changing
EMBEDDING_PROVIDER or EMBEDDING_MODEL:
    python -m app.jobs.reembed
`scripts/dev_db.py` runs it on every start, so the local database always matches the settings.
"""

from __future__ import annotations

import sys

from .. import audit
from ..config import get_settings
from ..db import Database
from ..embeddings import Embedder, build_embedder, to_pgvector
from ..review import embedding_text


def reembed_all(db: Database, embedder: Embedder) -> int:
    """Re-embed all findings (any review status); returns how many were updated."""
    with db.as_service() as conn:
        rows = conn.execute(
            "select f.id::text as id, f.text, f.theme, s.title from public.findings f "
            "join public.studies s on s.id = f.study_id order by f.id"
        ).fetchall()
        for row in rows:
            vector = embedder.embed(embedding_text(row["title"], row["theme"], row["text"]))
            conn.execute("update public.findings set embedding = %s::extensions.vector where id = %s",
                         [to_pgvector(vector), row["id"]])
        audit.log(conn, "findings.reembedded", "finding", None, {"embedder": embedder.name, "count": len(rows)})
    return len(rows)


def main() -> int:
    settings = get_settings()
    embedder = build_embedder(settings.embedding_provider, settings.embedding_model)
    db = Database(settings.database_url, max_size=1)
    try:
        count = reembed_all(db, embedder)
    finally:
        db.close()
    print(f"Re-embedded {count} findings with {embedder.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
