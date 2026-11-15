"""New-study answer alerts, the research-gap map and the value summary."""

from __future__ import annotations

from tests.conftest import SME_QUESTION, auth

SARI_SARI = "How do sari-sari store owners use supplier credit?"


def _pending(client, headers, title_part: str) -> dict:
    (study,) = [q for q in client.get("/api/review/queue", headers=headers).json() if title_part in q["title"]]
    return study


def test_approving_a_study_alerts_whoever_asked_what_it_answers(client):
    ben, ana = auth(client, "ben"), auth(client, "ana")
    before = client.post("/api/briefs", headers=ben, json={"question": SARI_SARI}).json()
    assert before["sources"] == {}   # nothing approved answers it yet
    assert client.get("/api/alerts", headers=ben).json() == []

    study = _pending(client, ana, "Sari-sari")
    decided = client.post(f"/api/review/studies/{study['id']}/decision", headers=ana, json={"approve": True}).json()
    assert decided["review_status"] == "approved"
    assert decided["answer_alerts"] == 1

    (alert,) = client.get("/api/alerts", headers=ben).json()
    assert alert["question"] == SARI_SARI and alert["study_id"] == study["id"] and alert["read_at"] is None
    assert client.post(f"/api/alerts/{alert['id']}/read", headers=ben).status_code == 200
    assert client.get("/api/alerts", headers=ben).json()[0]["read_at"] is not None

    # Asking again now finds the study; nobody else sees Ben's alert, and a second approval raises none.
    after = client.post("/api/briefs", headers=ben, json={"question": SARI_SARI}).json()
    assert any(s["study_id"] == study["id"] for s in after["sources"].values())
    assert client.get("/api/alerts", headers=auth(client, "carla")).json() == []
    actions = [r["action"] for r in client.get("/api/audit", headers=ana).json()]
    assert "answer_alert.created" in actions


def test_no_alert_for_a_study_the_asker_cannot_read_until_access_is_granted(client):
    ben, ana = auth(client, "ben"), auth(client, "ana")
    client.post("/api/briefs", headers=ben, json={"question": SARI_SARI})
    study = _pending(client, ana, "Sari-sari")
    client.patch(f"/api/review/studies/{study['id']}", headers=ana, json={"access_level": "restricted"})

    decided = client.post(f"/api/review/studies/{study['id']}/decision", headers=ana, json={"approve": True}).json()
    assert decided["answer_alerts"] == 0   # searched as Ben, under RLS: the restricted study is invisible
    assert client.get("/api/alerts", headers=ben).json() == []

    request = client.post("/api/access-requests", headers=ben,
                          json={"study_id": study["id"], "purpose": "Sari-sari credit for SME lending"}).json()
    granted = client.post(f"/api/access-requests/{request['id']}/decision", headers=ana, json={"approve": True}).json()
    assert granted["status"] == "approved" and granted["answer_alerts"] == 1
    (alert,) = client.get("/api/alerts", headers=ben).json()
    assert alert["study_code"] == study["code"]


def test_gap_map_shows_coverage_by_place_and_demand(client):
    ana = auth(client, "ana")
    client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SME_QUESTION})
    client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SARI_SARI})

    data = client.get("/api/gaps", headers=ana).json()
    assert data["columns"] == ["Metro Manila", "Provincial", "Rural", "Nationwide"]
    rows = {r["family"]: r for r in data["rows"]}
    loans = rows["barrier"]
    assert loans["label"] == "SME loan application drop-off"
    assert loans["asked"] >= 1 and "SME Banking" in loans["teams"]
    assert set(loans["cells"].values()) <= {"covered", "covered_stale", "partial", "gap"}
    assert loans["cells"]["Metro Manila"] == "covered"   # SI-2026-014: Tier A survey, NCR, 2026
    assert data["rows"][0]["asked"] >= data["rows"][-1]["asked"]   # most asked first
    assert any(u["question"] == SARI_SARI for u in data["unanswered"])

    assert client.get("/api/gaps", headers=auth(client, "ben")).status_code == 403


def test_value_summary_counts_answers_reuse_and_alerts(client):
    ben, ana = auth(client, "ben"), auth(client, "ana")
    client.post("/api/briefs", headers=ben, json={"question": SME_QUESTION})
    client.post("/api/briefs", headers=ben, json={"question": SARI_SARI})
    study = _pending(client, ana, "Sari-sari")
    client.post(f"/api/review/studies/{study['id']}/decision", headers=ana, json={"approve": True})

    value = client.get("/api/audit/summary", headers=ana).json()["value"]
    assert value["briefs"] == 2 and value["answered"] == 1
    assert value["answered_without_analyst"] == 1
    assert value["cross_team"] == 1 and value["studies_reused"] >= 1   # Ben's brief cites S&I studies
    assert value["alerts_sent"] == 1 and value["alerts_opened"] == 0
    assert value["hours_saved"] == round(value["minutes_per_question"] / 60, 1)
