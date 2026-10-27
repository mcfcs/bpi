"""Nightly tier recomputation. Recency decays, so a study's tier can drop without anyone editing it.

Run daily, for example from cron or Windows Task Scheduler:
    python -m app.jobs.recompute_tiers
or have a scheduler call POST /api/admin/recompute-tiers as an S&I analyst.
"""

from __future__ import annotations

import json
import sys
from datetime import date

from .. import audit
from ..config import get_settings
from ..db import Database
from ..tiers import compute_tier_or_none


def recompute_all(db: Database, today: date, actor_id: str | None = None) -> list[dict]:
    """Recompute every study's tier; returns the studies whose tier changed. Audit rows are
    attributed to actor_id when an analyst triggered the run, otherwise to the system (null)."""
    changed = []
    with db.as_service() as conn:
        if actor_id:
            conn.execute("select set_config('request.jwt.claims', %s, true)", [json.dumps({"sub": actor_id})])
        rows = conn.execute(
            "select id::text as id, code, method_type, sample_size, fieldwork_end, robustness_tier "
            "from public.studies for update"
        ).fetchall()
        for row in rows:
            tier = compute_tier_or_none(row["method_type"], row["sample_size"], row["fieldwork_end"], today)
            conn.execute("update public.studies set robustness_tier = %s, tier_computed_at = now() where id = %s",
                         [tier, row["id"]])
            if tier != row["robustness_tier"]:
                change = {"study_id": row["id"], "code": row["code"], "from": row["robustness_tier"], "to": tier}
                changed.append(change)
                audit.log(conn, "study.tier_recomputed", "study", row["id"],
                          {"from": row["robustness_tier"], "to": tier, "trigger": "scheduled"})
    return changed


def main() -> int:
    settings = get_settings()
    db = Database(settings.database_url, max_size=1)
    try:
        changes = recompute_all(db, date.today())
    finally:
        db.close()
    print(f"Recomputed tiers; {len(changes)} changed.")
    for change in changes:
        print(f"  {change['code']}: {change['from']} -> {change['to']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
