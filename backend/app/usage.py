"""Usage summary for S&I, read from the append-only audit log and the governance tables.

What business teams asked, how often the answer was limited by access (a restricted study also
matched), how often briefs went to an analyst, and which questions no readable study answered: the
last are demand S&I can weigh before commissioning. Counts only; nothing here is written.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import psycopg

from .config import VALUE_CONFIG


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
        "value": value(conn, since),
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


def value(conn: psycopg.Connection, since: datetime) -> dict:
    """What the briefs delivered, for the value counter on the audit page.

    - answered: briefs that cited at least one finding; answered_without_analyst: of those, briefs
      nobody sent to an analyst (an automatic conflict check does not count against it);
    - cross_team: answered briefs that cited a study owned by another team (research reused across
      the silos), and how many distinct studies that reused;
    - already_covered: commissioning objectives the check found covered, i.e. research not
      commissioned twice if the team acts on it;
    - alerts: earlier questions a newly approved or newly granted study answered;
    - hours_saved: answered_without_analyst times VALUE_CONFIG's minutes per question, an estimate.
    """
    rows = conn.execute(
        """
        select b.id, t.name as team, b.payload -> 'sources' as sources,
               coalesce(cardinality(b.retrieved_finding_ids), 0) as retrieved,
               exists (select 1 from public.escalations e
                       where e.brief_id = b.id and e.reason <> 'unresolved_conflict') as escalated
        from public.briefs b
        join public.profiles p on p.id = b.user_id
        join public.teams t on t.id = p.team_id
        where b.created_at >= %s
        """, [since]).fetchall()
    answered = [r for r in rows if r["sources"]]
    without_analyst = [r for r in answered if not r["escalated"]]
    reused_studies: set[str] = set()
    cross_team = 0
    for r in answered:
        other = {s.get("study_id") for s in r["sources"].values() if s.get("owner_team") and s["owner_team"] != r["team"]}
        if other:
            cross_team += 1
            reused_studies |= other
    covered = conn.execute(
        """
        select count(*)::int as n from public.commissioning_checks c,
               jsonb_array_elements(c.result -> 'objectives') o
        where c.created_at >= %s and o ->> 'coverage' = 'covered'
        """, [since]).fetchone()["n"]
    alerts = conn.execute(
        "select count(*)::int as sent, count(read_at)::int as opened from public.answer_alerts where created_at >= %s",
        [since]).fetchone()
    minutes = VALUE_CONFIG["analyst_minutes_per_question"]
    return {
        "briefs": len(rows),
        "answered": len(answered),
        "answered_without_analyst": len(without_analyst),
        "share_without_analyst": round(len(without_analyst) / len(rows), 2) if rows else None,
        "cross_team": cross_team,
        "studies_reused": len(reused_studies),
        "already_covered": covered,
        "alerts_sent": alerts["sent"],
        "alerts_opened": alerts["opened"],
        "hours_saved": round(len(without_analyst) * minutes / 60, 1),
        "minutes_per_question": minutes,
    }
