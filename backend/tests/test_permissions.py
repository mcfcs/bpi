"""Governance: row-level security, can_read(), grants and the access-request flow, the audit log.
These run against the real policies in supabase/migrations."""

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app import retrieval
from app.embeddings import HashingEmbedder
from tests.conftest import SME_QUESTION, auth


def readable_codes(db, user) -> set[str]:
    with db.as_user(user.id, user.email) as conn:
        return {r["code"] for r in conn.execute("select code from public.studies").fetchall()}


def test_bu_users_read_open_studies_and_their_own_teams(db, people):
    ben = readable_codes(db, people["ben"])
    carla = readable_codes(db, people["carla"])
    assert "SI-2026-014" in ben and "SI-2026-014" not in carla      # SME Banking's restricted study
    assert "SI-2026-027" in carla and "SI-2026-027" not in ben      # Cards & Payments' restricted study
    assert {"SI-2025-009", "SI-2025-031", "SI-2022-007", "SI-2026-021", "SI-2026-033"} <= ben & carla


def test_pending_studies_are_visible_only_to_si(db, people):
    with db.as_service() as conn:
        pending = {r["code"] for r in conn.execute("select code from public.studies where review_status = 'pending_review'")}
    assert pending
    assert pending <= readable_codes(db, people["ana"])
    assert not pending & readable_codes(db, people["ben"])


def test_findings_follow_their_study(db, people, study_ids):
    with db.as_user(people["carla"].id) as conn:
        rows = conn.execute("select count(*) as n from public.findings where study_id = %s", [study_ids["SI-2026-014"]]).fetchone()
        assert rows["n"] == 0
        assert conn.execute("select public.can_read(%s) as ok", [study_ids["SI-2026-014"]]).fetchone()["ok"] is False


def test_hybrid_search_never_returns_unreadable_findings(db, people, study_ids):
    with db.as_user(people["carla"].id) as conn:
        found = retrieval.search(conn, SME_QUESTION, HashingEmbedder())
    assert found and all(s.study_id != study_ids["SI-2026-014"] for s in found)


def test_access_request_approved_by_owning_team_grants_access(client, db, people, study_ids):
    study = study_ids["SI-2026-014"]
    created = client.post("/api/access-requests", headers=auth(client, "carla"),
                          json={"study_id": study, "purpose": "Benchmark card onboarding drop-off against SME lending."})
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]

    # Requesters see what they asked for, by title, without being able to read the study.
    mine = client.get("/api/access-requests", headers=auth(client, "carla")).json()
    assert mine[0]["study_code"] == "SI-2026-014" and mine[0]["can_decide"] is False

    # A BU user who is not an approver cannot decide; neither can the requester.
    assert client.post(f"/api/access-requests/{request_id}/decision", headers=auth(client, "ben"),
                       json={"approve": True}).status_code == 403
    assert client.post(f"/api/access-requests/{request_id}/decision", headers=auth(client, "carla"),
                       json={"approve": True}).status_code == 403

    decided = client.post(f"/api/access-requests/{request_id}/decision", headers=auth(client, "dino"),
                          json={"approve": True, "note": "Approved for benchmarking."})
    assert decided.status_code == 200, decided.text
    assert "SI-2026-014" in readable_codes(db, people["carla"])

    with db.as_service() as conn:
        actions = [r["action"] for r in conn.execute(
            "select action from public.audit_log where entity_id = %s order by id", [request_id])]
    assert actions == ["access.requested", "access.approved"]


def test_expired_grants_stop_working(db, people, study_ids):
    with db.as_service() as conn:
        conn.execute(
            "insert into public.study_grants (study_id, team_id, expires_at) values (%s, %s, %s)",
            [study_ids["SI-2026-014"], people["carla"].team_id, datetime.now(timezone.utc) - timedelta(days=1)],
        )
    assert "SI-2026-014" not in readable_codes(db, people["carla"])


def test_users_cannot_grant_themselves_access(db, people, study_ids):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.as_user(people["carla"].id) as conn:
            conn.execute("insert into public.study_grants (study_id, team_id) values (%s, %s)",
                         [study_ids["SI-2026-014"], people["carla"].team_id])


def test_bu_users_cannot_edit_studies_or_overrides(db, people, study_ids):
    with db.as_user(people["ben"].id) as conn:
        updated = conn.execute(
            "update public.studies set tier_override = 'A', tier_override_reason = 'x' where id = %s",
            [study_ids["SI-2025-009"]]).rowcount
    assert updated == 0


def test_review_endpoints_are_for_si_only(client, study_ids):
    assert client.get("/api/review/queue", headers=auth(client, "ben")).status_code == 403
    assert client.patch(f"/api/review/studies/{study_ids['SI-2025-009']}", headers=auth(client, "ben"),
                        json={"tier_override": "A", "tier_override_reason": "x"}).status_code == 403
    assert client.get("/api/audit", headers=auth(client, "ben")).status_code == 403
    assert client.get("/api/review/queue", headers=auth(client, "ana")).status_code == 200


def test_audit_log_is_append_only_and_si_only(db, people):
    with db.as_user(people["ben"].id) as conn:
        conn.execute("select public.log_audit('test.event', 'test', null, '{}'::jsonb)")
        assert conn.execute("select count(*) as n from public.audit_log").fetchone()["n"] == 0  # cannot read it
    with db.as_user(people["ana"].id) as conn:
        row = conn.execute("select actor_id::text as actor from public.audit_log where action = 'test.event'").fetchone()
        assert row["actor"] == people["ben"].id
    for statement in ("update public.audit_log set action = 'x'", "delete from public.audit_log", "truncate public.audit_log"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.as_service() as conn:   # even the table owner
                conn.execute(statement)


def test_briefs_are_private_to_their_author_and_si(client):
    brief = client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SME_QUESTION}).json()
    assert client.get(f"/api/briefs/{brief['id']}", headers=auth(client, "carla")).status_code == 404
    assert client.get(f"/api/briefs/{brief['id']}", headers=auth(client, "ana")).status_code == 200


def test_requests_without_a_valid_token_are_rejected(client):
    assert client.post("/api/briefs", json={"question": SME_QUESTION}).status_code == 401
    assert client.post("/api/briefs", headers={"Authorization": "Bearer nope"}, json={"question": SME_QUESTION}).status_code == 401
