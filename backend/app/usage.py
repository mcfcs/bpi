"""Usage summary for S&I, read from the append-only audit log and the governance tables.

What business teams asked, how often the answer was limited by access (a restricted study also
matched), how often briefs went to an analyst, and which questions no readable study answered: the
last are demand S&I can weigh before commissioning. Counts only; nothing here is written.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import psycopg


def summary(conn: psycopg.Connection, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    briefs = conn.execute(
        """
        select a.occurred_at, a.details, coalesce(t.name, 'Unknown team') as team
        from public.audit_log a
        left join public.profiles p on p.id = a.actor_id
        left join public.teams t on t.id = p.team_id
        where a.action = 'brief.generated' and a.occurred_at >= %s
        order by a.occurred_at desc
        """, [since]).fetchall()

    def detail(row, key, default=None):
        return (row["details"] or {}).get(key, default)

    confidence = Counter(detail(r, "confidence") or "none" for r in briefs)
    by_team = Counter(r["team"] for r in briefs)
    writers = Counter("templates" if str(detail(r, "model") or "").startswith("offline") else "model"
                      for r in briefs if detail(r, "cited", 0))
    unanswered = [r for r in briefs if not detail(r, "cited", 0)]
    asked = Counter(" ".join(str(detail(r, "question", "")).split()) for r in briefs)

    escalations = conn.execute(
        """
        select reason, status, count(*)::int as n from public.escalations
        where created_at >= %s group by reason, status
        """, [since]).fetchall()
    access = conn.execute(
        "select status, count(*)::int as n from public.access_requests where created_at >= %s group by status",
        [since]).fetchall()
    checks = conn.execute(
        "select count(*)::int as run, count(submitted_at)::int as submitted from public.commissioning_checks "
        "where created_at >= %s", [since]).fetchone()

    return {
        "days": days,
        "briefs": {
            "total": len(briefs),
            "confidence": {lvl: confidence.get(lvl, 0) for lvl in ("high", "medium", "low")},
            "by_team": [{"team": t, "count": n} for t, n in by_team.most_common()],
            "restricted_also_matched": sum(1 for r in briefs if detail(r, "restricted_matches")),
            "regenerated": sum(1 for r in briefs if detail(r, "regenerated")),
            "dropped_claims": sum(len(detail(r, "dropped_claims") or []) for r in briefs),
            "written_by_model": writers.get("model", 0),
            "written_from_templates": writers.get("templates", 0),
        },
        "most_asked": [{"question": q, "count": n} for q, n in asked.most_common(8) if q],
        "unanswered": [{"question": detail(r, "question"), "team": r["team"], "asked_at": r["occurred_at"].isoformat()}
                       for r in unanswered[:10]],
        "unanswered_total": len(unanswered),
        "escalations": {
            "automatic": sum(e["n"] for e in escalations if e["reason"] == "unresolved_conflict"),
            "from_users": sum(e["n"] for e in escalations if e["reason"] != "unresolved_conflict"),
            "open": sum(e["n"] for e in escalations if e["status"] == "open"),
            "answered": sum(e["n"] for e in escalations if e["status"] == "answered"),
        },
        "access_requests": {s: next((a["n"] for a in access if a["status"] == s), 0) for s in ("pending", "approved", "denied")},
        "coverage_checks": {"run": checks["run"], "sent_to_si": checks["submitted"]},
    }
