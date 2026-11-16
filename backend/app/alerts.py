""""A new study answers your question."

When S&I approves a study (checkpoint 1), or a study owner grants someone access to one
(checkpoint 2), questions that no readable study answered earlier are searched again, each one as
the person who asked it. If the brief that person would now get draws on the newly readable study,
they get an alert with a link to ask again.

This closes the loop between what business units ask and what S&I publishes: a question asked
before the research existed is answered when it arrives, without anyone remembering to ask again.

Rules:
- The search runs under the asker's own row-level security (invariant 1), with the same retrieval
  and off-topic gates as a brief (synthesis.answering_sources). An alert can never point at a study
  the asker cannot read.
- Nothing is written for the asker: no brief, no model call. The alert only says that asking again
  will now find something; the asker decides whether to.
- One alert per unanswered brief, and none if the asker already got an answer to the same question
  since. Each alert is audited under the person whose decision raised it.
"""

from __future__ import annotations

from . import audit, topicality
from .auth import CurrentUser
from .config import ALERT_CONFIG
from .db import Database
from .embeddings import Embedder
from .synthesis import answering_sources


def _normalise(question: str) -> str:
    return " ".join(question.lower().split())


def unanswered_questions(db: Database, only_user: str | None = None) -> list[dict]:
    """Recent briefs that retrieved nothing, newest per person and question, that have no alert yet
    and whose asker has not since had the same question answered. Read with the service role: these
    are governance rows (who asked what), not findings, and the match itself runs as the asker."""
    with db.as_service() as conn:
        rows = conn.execute(
            """
            select b.id::text as brief_id, b.user_id::text as user_id, p.email, b.question, b.created_at
            from public.briefs b
            join public.profiles p on p.id = b.user_id
            where coalesce(cardinality(b.retrieved_finding_ids), 0) = 0
              and b.created_at >= now() - make_interval(days => %s)
              and (%s::uuid is null or b.user_id = %s::uuid)
              and not exists (select 1 from public.answer_alerts a where a.brief_id = b.id)
              and not exists (
                select 1 from public.briefs later
                where later.user_id = b.user_id and later.created_at > b.created_at
                  and lower(later.question) = lower(b.question)
                  and coalesce(cardinality(later.retrieved_finding_ids), 0) > 0)
            order by b.created_at desc
            """,
            [ALERT_CONFIG["lookback_days"], only_user, only_user],
        ).fetchall()
    seen: set[tuple[str, str]] = set()
    picked = []
    for row in rows:
        key = (row["user_id"], _normalise(row["question"]))
        if key in seen or topicality.is_junk(row["question"]):
            continue
        seen.add(key)
        picked.append(row)
    return picked[: ALERT_CONFIG["max_questions"]]


def notify_new_answers(db: Database, embedder: Embedder, study_id: str, decided_by: CurrentUser,
                       only_user: str | None = None) -> list[dict]:
    """Alerts for earlier unanswered questions that the now-readable study answers. Call after the
    approval or grant has committed, so the askers' searches can see it."""
    hits = []
    for row in unanswered_questions(db, only_user):
        vector = embedder.embed_query(row["question"])
        with db.as_user(row["user_id"], row["email"]) as conn:
            sources = answering_sources(conn, row["question"], embedder, vector)
        if any(s.study_id == study_id for s in sources):
            hits.append(row)
    if not hits:
        return []

    created = []
    with db.as_service() as conn:
        for row in hits:
            alert = conn.execute(
                "insert into public.answer_alerts (user_id, brief_id, study_id, question) values (%s, %s, %s, %s) "
                "on conflict (brief_id) do nothing returning id::text as id",
                [row["user_id"], row["brief_id"], study_id, row["question"]],
            ).fetchone()
            if alert:
                created.append({**alert, "brief_id": row["brief_id"], "user_id": row["user_id"],
                                "question": row["question"]})
    with db.as_user(decided_by.id, decided_by.email) as conn:
        for alert in created:
            audit.log(conn, "answer_alert.created", "answer_alert", alert["id"],
                      {"study_id": study_id, "brief_id": alert["brief_id"], "user_id": alert["user_id"],
                       "question": alert["question"]})
    return created


def list_alerts(conn) -> list[dict]:
    """The caller's alerts, unread first. The study's code and title come through RLS, so an alert
    for a study the reader has since lost access to shows no title."""
    return conn.execute(
        """
        select a.id::text as id, a.brief_id::text as brief_id, a.study_id::text as study_id, a.question,
               a.created_at, a.read_at, s.code as study_code, s.title as study_title
        from public.answer_alerts a
        left join public.studies s on s.id = a.study_id
        where a.user_id = auth.uid()
        order by a.read_at is not null, a.created_at desc
        limit 20
        """).fetchall()


def mark_read(conn, alert_id: str) -> dict | None:
    return conn.execute(
        "update public.answer_alerts set read_at = coalesce(read_at, now()) where id = %s and user_id = auth.uid() "
        "returning id::text as id, read_at",
        [alert_id]).fetchone()
