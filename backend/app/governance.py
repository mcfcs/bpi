"""Access requests and grants (checkpoint 2) and "Ask an analyst" escalations (checkpoint 3).

All functions take a connection from Database.as_user(); RLS and the security-definer functions in
the baseline migration enforce who may do what.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import psycopg

from . import audit
from .review import _jsonable


class GovernanceError(ValueError):
    pass


def request_access(conn: psycopg.Connection, study_id: str, purpose: str, user_id: str) -> dict:
    readable = conn.execute("select public.can_read(%s) as ok", [study_id]).fetchone()["ok"]
    if readable:
        raise GovernanceError("You can already read this study.")
    row = conn.execute(
        "insert into public.access_requests (study_id, requester_id, requester_team_id, purpose) "
        "values (%s, %s, public.current_team_id(), %s) returning id::text as id, status, created_at",
        [study_id, user_id, purpose.strip()],
    ).fetchone()
    audit.log(conn, "access.requested", "access_request", row["id"], {"study_id": study_id, "purpose": purpose.strip()})
    return _jsonable(row)


def list_access_requests(conn: psycopg.Connection) -> list[dict]:
    """The caller's own requests, plus requests they may decide (RLS decides which rows appear)."""
    rows = conn.execute(
        """
        select r.id::text as id, r.study_id::text as study_id, c.code as study_code, c.title as study_title,
               c.owner_team, r.purpose, r.status, r.created_at, r.decided_at, r.decision_note,
               p.display_name as requester, rt.name as requester_team,
               r.requester_id = auth.uid() as mine,
               (public.can_decide_access(r.study_id) and r.requester_id <> auth.uid() and r.status = 'pending') as can_decide
        from public.access_requests r
        join public.profiles p on p.id = r.requester_id
        join public.teams rt on rt.id = r.requester_team_id
        left join public.requested_study_catalogue() c on c.study_id = r.study_id
        order by r.created_at desc
        """
    ).fetchall()
    return [_jsonable(r) for r in rows]


def decide_access(conn: psycopg.Connection, request_id: str, approve: bool, note: str | None,
                  expires_on: date | None) -> dict:
    expires_at = datetime.combine(expires_on, time.max, tzinfo=timezone.utc) if expires_on else None
    row = conn.execute(
        "select id::text as id, status, decided_at from public.decide_access_request(%s, %s, %s, %s)",
        [request_id, approve, note, expires_at],
    ).fetchone()
    return _jsonable(row)


def create_escalation(conn: psycopg.Connection, user_id: str, brief_id: str | None, note: str,
                      reason: str = "user_request") -> dict:
    row = conn.execute(
        "insert into public.escalations (brief_id, requested_by, reason, note) values (%s, %s, %s, %s) "
        "returning id::text as id, status, reason, created_at",
        [brief_id, user_id, reason, note.strip()],
    ).fetchone()
    audit.log(conn, "escalation.created", "escalation", row["id"], {"brief_id": brief_id, "reason": reason})
    return _jsonable(row)


def list_escalations(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        select e.id::text as id, e.brief_id::text as brief_id, b.question, b.confidence, e.reason, e.note,
               e.status, e.response, e.created_at, e.responded_at, p.display_name as requested_by,
               t.name as requester_team, rp.display_name as responded_by
        from public.escalations e
        join public.profiles p on p.id = e.requested_by
        join public.teams t on t.id = p.team_id
        left join public.briefs b on b.id = e.brief_id
        left join public.profiles rp on rp.id = e.responded_by
        order by (e.status = 'open') desc, e.created_at desc
        """
    ).fetchall()
    return [_jsonable(r) for r in rows]


def respond_escalation(conn: psycopg.Connection, escalation_id: str, response: str, user_id: str) -> dict:
    row = conn.execute(
        "update public.escalations set response = %s, status = 'answered', responded_by = %s, responded_at = now() "
        "where id = %s returning id::text as id, status",
        [response.strip(), user_id, escalation_id],
    ).fetchone()
    if row is None:
        raise LookupError("escalation not found")
    audit.log(conn, "escalation.answered", "escalation", escalation_id, {})
    return _jsonable(row)
