"""Access requests and grants (checkpoint 2) and "Ask an analyst" escalations (checkpoint 3).

All functions take a connection from Database.as_user(); RLS and the security-definer functions in
the baseline migration enforce who may do what. draft_escalation() turns a stored brief into a
specific question for an analyst; it only reads the brief's own payload (already filtered by RLS
when the brief was built) and never calls the LLM.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone

import psycopg

from . import audit
from .describe import lower_label
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
                  expires_on: date | None, today: date | None = None) -> dict:
    if approve and expires_on is not None and expires_on < (today or date.today()):
        raise GovernanceError("The expiry date is in the past; choose today or a later date.")
    expires_at = datetime.combine(expires_on, time.max, tzinfo=timezone.utc) if expires_on else None
    row = conn.execute(
        "select id::text as id, status, decided_at from public.decide_access_request(%s, %s, %s, %s)",
        [request_id, approve, note, expires_at],
    ).fetchone()
    return _jsonable(row)


def compose_escalation_note(note: str, gaps: list[str] | None = None, suggested_question: str | None = None) -> str:
    """The note an analyst reads: the user's words, the question they chose, and the gaps they ticked."""
    parts = [note.strip()]
    if suggested_question and suggested_question.strip():
        parts.append("Question for the analyst: " + suggested_question.strip())
    chosen = [g.strip() for g in gaps or [] if g and g.strip()]
    if chosen:
        parts.append("Gaps to check:\n" + "\n".join(f"- {g}" for g in chosen))
    return "\n\n".join(parts)


def create_escalation(conn: psycopg.Connection, user_id: str, brief_id: str | None, note: str,
                      reason: str = "user_request", gaps: list[str] | None = None,
                      suggested_question: str | None = None) -> dict:
    text = compose_escalation_note(note, gaps, suggested_question)
    # Sending the same request twice while it is open returns the open escalation.
    existing = conn.execute(
        "select id::text as id, status, reason, created_at from public.escalations "
        "where requested_by = %s and brief_id is not distinct from %s::uuid and note = %s and status = 'open' "
        "order by created_at desc limit 1",
        [user_id, brief_id, text],
    ).fetchone()
    if existing:
        return {**_jsonable(existing), "duplicate": True}
    row = conn.execute(
        "insert into public.escalations (brief_id, requested_by, reason, note) values (%s, %s, %s, %s) "
        "returning id::text as id, status, reason, created_at",
        [brief_id, user_id, reason, text],
    ).fetchone()
    audit.log(conn, "escalation.created", "escalation", row["id"], {
        "brief_id": brief_id, "reason": reason, "gaps": [g.strip() for g in gaps or [] if g.strip()],
        "suggested_question": bool(suggested_question and suggested_question.strip())})
    return _jsonable(row)


def brief_escalations(conn: psycopg.Connection, brief_id: str) -> list[dict]:
    """Every escalation raised from a brief, oldest first, with the analyst's (appended) replies.
    RLS limits rows to the caller's own escalations, or all of them for S&I."""
    rows = conn.execute(
        "select e.id::text as id, e.status, e.reason, e.note, e.response, rp.display_name as responded_by, "
        "e.responded_at, e.created_at from public.escalations e "
        "left join public.profiles rp on rp.id = e.responded_by where e.brief_id = %s order by e.created_at",
        [brief_id],
    ).fetchall()
    return [_jsonable(r) for r in rows]


def conflict_keys(unresolved_conflicts: list[dict] | None) -> set[tuple[str, tuple[str, ...]]]:
    """(topic, finding ids) per unresolved conflict: what makes two automatic escalations the same."""
    return {(n["topic"], tuple(sorted(n["finding_ids"]))) for n in unresolved_conflicts or []}


def open_conflict_escalation(conn: psycopg.Connection, keys: set) -> dict | None:
    """The caller's open automatic escalation for any of these conflicts, if there is one."""
    if not keys:
        return None
    rows = conn.execute(
        "select e.id::text as id, e.status, e.reason, b.payload -> 'unresolved_conflicts' as conflicts "
        "from public.escalations e join public.briefs b on b.id = e.brief_id "
        "where e.requested_by = auth.uid() and e.status = 'open' and e.reason = 'unresolved_conflict' "
        "order by e.created_at desc"
    ).fetchall()
    for row in rows:
        if conflict_keys(row["conflicts"]) & keys:
            return {"id": row["id"], "status": row["status"], "reason": row["reason"], "existing": True}
    return None


def list_escalations(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        select e.id::text as id, e.brief_id::text as brief_id, b.question, b.confidence, e.reason, e.note,
               e.status, e.response, e.created_at, e.responded_at, p.display_name as requested_by,
               t.name as requester_team, rp.display_name as responded_by, e.requested_by::text as requester_id
        from public.escalations e
        join public.profiles p on p.id = e.requested_by
        join public.teams t on t.id = p.team_id
        left join public.briefs b on b.id = e.brief_id
        left join public.profiles rp on rp.id = e.responded_by
        order by (e.status = 'open') desc, e.created_at desc
        """
    ).fetchall()
    # Thread follow-ups under the first request: the same person asking about the same question again
    # (from the same brief, or from a new brief after asking again) continues one conversation.
    first: dict[tuple, str] = {}
    for row in sorted(rows, key=lambda r: r["created_at"]):
        question = " ".join((row["question"] or "").lower().split())
        key = (row["requester_id"], question or row["brief_id"] or row["id"])
        row["thread_id"] = first.setdefault(key, row["id"])
    return [_jsonable({k: v for k, v in r.items() if k != "requester_id"}) for r in rows]


def respond_escalation(conn: psycopg.Connection, escalation_id: str, response: str, user_id: str) -> dict:
    """Answer an escalation. A later reply is appended under the earlier one, never replacing it."""
    current = conn.execute("select response from public.escalations where id = %s for update", [escalation_id]).fetchone()
    if current is None:
        raise LookupError("escalation not found")
    reply = response.strip()
    follow_up = bool(current["response"])
    text = f"{current['response']}\n\nFollow-up ({date.today():%d %b %Y}):\n{reply}" if follow_up else reply
    row = conn.execute(
        "update public.escalations set response = %s, status = 'answered', responded_by = %s, responded_at = now() "
        "where id = %s returning id::text as id, status, response",
        [text, user_id, escalation_id],
    ).fetchone()
    if row is None:
        raise LookupError("escalation not found")
    audit.log(conn, "escalation.answered", "escalation", escalation_id,
              {"follow_up": follow_up, "reply_chars": len(reply), "reply_excerpt": reply[:200]})
    return _jsonable(row)


# ---------------------------------------------------------------------------------------------
# "Ask an analyst" draft, generated from a stored brief
# ---------------------------------------------------------------------------------------------

def _sentences(text: str, limit: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return " ".join(parts[:limit])


def _lower(label: str) -> str:
    first = label.split()[0] if label.split() else ""
    return label if first[:2].isupper() else label[:1].lower() + label[1:]


def draft_escalation(brief: dict) -> dict:
    """A specific, checkable escalation from a brief payload: the question, what the assistant
    found (2-3 sentences), cited study codes, gaps as a checklist, segment differences and any
    unresolved conflict, and a suggested question for the analyst. Built in code from the stored,
    validated brief, so it adds no facts."""
    sources = brief.get("sources") or {}
    labels = brief.get("topic_labels") or {}
    summaries = brief.get("summaries") or {}
    claims = brief.get("claims") or []
    if summaries.get("executive"):
        found = _sentences(summaries["executive"]["text"], 3)
    elif claims:
        found = " ".join(_sentences(c["text"], 1) for c in claims[:3])
    else:
        found = brief.get("no_headline_message") or "The assistant found no approved study you can read on this."
    codes = sorted({v["study_code"] for v in sources.values()})
    asks = {g["text"]: g.get("ask") for g in brief.get("gap_items") or []}
    gaps = [{"id": f"gap-{i}", "text": g, "ask": asks.get(g), "checked": True} for i, g in enumerate(brief.get("gaps") or [], 1)]

    differences = []
    for kind, key in (("unresolved_conflict", "unresolved_conflicts"), ("context_difference", "context_notes"),
                      ("within_study", "study_patterns")):
        for note in brief.get(key) or []:
            differences.append({
                "kind": kind, "topic": note["topic"], "label": labels.get(note["topic"], note["topic"]),
                "differs_by": note.get("differs_by", []), "explanation": note["explanation"],
                "study_codes": sorted({sources[i]["study_code"] for i in note["finding_ids"] if i in sources}),
            })

    team = (brief.get("prepared_for") or {}).get("team") or "my team"
    conflict = next((d for d in differences if d["kind"] == "unresolved_conflict"), None)
    confounded = next((d for d in differences if d["kind"] == "context_difference" and len(d["differs_by"]) >= 2), None)
    gap_ask = next((g["ask"] for g in gaps if g["ask"]), None)
    if conflict:
        suggested = (f"{' and '.join(conflict['study_codes'])} report different results on {lower_label(conflict['label'])} "
                     f"for the same group and period. Which should {team} rely on, and is there a known reason for "
                     f"the difference (questionnaire, sample source, timing)?")
    elif confounded:
        dims = ", ".join(confounded["differs_by"][:-1]) + " and " + confounded["differs_by"][-1]
        suggested = (f"On {_lower(confounded['label'])}, {' and '.join(confounded['study_codes'])} asked groups that differ "
                     f"by {dims} at once. Is there a study that varies only one of these, so we know which one "
                     f"explains the difference?")
    elif gap_ask:
        suggested = gap_ask
    elif codes:
        suggested = (f"Are {', '.join(codes)} still the latest S&I evidence on \u201c{brief.get('question', '')}\u201d, "
                     f"and is anything in progress?")
    else:
        suggested = f"Has S&I researched \u201c{brief.get('question', '')}\u201d, or is this a new problem?"

    note = f"Question: {brief.get('question', '')}\n\nWhat the assistant found: {found}"
    if codes:
        note += f"\n\nStudies cited: {', '.join(codes)}"
    return {
        "brief_id": brief.get("id"),
        "question": brief.get("question"),
        "found": found,
        "study_codes": codes,
        "confidence": (brief.get("confidence") or {}).get("level"),
        "gaps": gaps,
        "differences": differences,
        "suggested_question": suggested,
        "note": note,
    }
