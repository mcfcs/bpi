"""Checkpoint 1 aids (personal-data check, overlap check), follow-up questions, unanswered demand on the
gap map."""

from __future__ import annotations

from pathlib import Path

from app import privacy
from tests.conftest import SME_QUESTION, auth

REPORTS = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "reports"
PHONE_QUOTE = '> "Just text me at 0917 555 0142 when it is approved." — Bakery owner, 39, Laguna\n'


def test_patterns_flag_personal_data_and_leave_survey_figures_alone():
    kinds = {h["kind"] for h in privacy.scan(
        "Call 0917 555 0142 or +63 917 555 0142, mail ana@example.com; my name is Rosa Cruz; TIN 123-456-789-000.")}
    assert {"phone", "email", "name", "tin"} <= kinds
    assert privacy.scan("61% of 1,200 SME owners (base n=450) in 2025-2026 cited fees; rank 1 of 5.") == []


def test_approval_waits_for_a_personal_data_check(client):
    ana = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=ana).json()}
    report = (REPORTS / "sme-loan-renewal-pulse-2026.md").read_text(encoding="utf-8").replace(
        "SME Loan Renewal Pulse 2026", "SME Loan Renewal Pulse 2026 (privacy test)") + "\n" + PHONE_QUOTE
    study = client.post("/api/ingest", headers=ana, json={
        "report_text": report, "owner_team_id": teams["SME Banking"], "access_level": "open"}).json()

    detail = client.get(f"/api/studies/{study['id']}", headers=ana).json()
    (flag,) = detail["privacy"]["findings"]
    assert flag["matches"][0]["kind"] == "phone" and "0917 555 0142" in flag["text"]

    refused = client.post(f"/api/review/studies/{study['id']}/decision", headers=ana, json={"approve": True})
    assert refused.status_code == 422 and "personal data" in refused.json()["detail"]
    approved = client.post(f"/api/review/studies/{study['id']}/decision", headers=ana,
                           json={"approve": True, "privacy_checked": True})
    assert approved.status_code == 200 and approved.json()["review_status"] == "approved"
    entry = next(r for r in client.get("/api/audit", headers=ana).json() if r["action"] == "study.approved")
    assert entry["details"]["privacy_checked"] is True and entry["details"]["privacy_flags"] == 1


def test_editing_the_flagged_finding_clears_the_check(client):
    ana = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=ana).json()}
    report = (REPORTS / "sme-loan-renewal-pulse-2026.md").read_text(encoding="utf-8").replace(
        "SME Loan Renewal Pulse 2026", "SME Loan Renewal Pulse 2026 (edit test)") + "\n" + PHONE_QUOTE
    study = client.post("/api/ingest", headers=ana, json={
        "report_text": report, "owner_team_id": teams["SME Banking"], "access_level": "open"}).json()
    (flag,) = client.get(f"/api/studies/{study['id']}", headers=ana).json()["privacy"]["findings"]
    client.patch(f"/api/review/findings/{flag['finding_id']}", headers=ana,
                 json={"text": "Just text me when it is approved."})
    assert client.get(f"/api/studies/{study['id']}", headers=ana).json()["privacy"]["findings"] == []
    ok = client.post(f"/api/review/studies/{study['id']}/decision", headers=ana, json={"approve": True})
    assert ok.status_code == 200


def test_review_shows_approved_studies_a_new_one_overlaps(client):
    ana = auth(client, "ana")
    (pending,) = [q for q in client.get("/api/review/queue", headers=ana).json()
                  if q["source_name"] == "cebu-sme-digital-onboarding-groups-2026.md"]
    overlaps = client.get(f"/api/studies/{pending['id']}", headers=ana).json()["overlaps"]
    assert overlaps, "a Cebu SME onboarding study should overlap the approved SME studies"
    assert all(o["verdict"] in ("repeat", "newer_wave", "same_topic") and o["verdict_text"] for o in overlaps)
    assert any("SME" in o["title"] for o in overlaps)
    # Approved studies and business-unit readers get no review aids.
    approved = client.get(f"/api/studies/{overlaps[0]['study_id']}", headers=ana).json()
    assert "overlaps" not in approved
    assert "overlaps" not in client.get(f"/api/studies/{pending['id']}", headers=auth(client, "ben")).json()


def test_follow_up_keeps_the_subject_and_links_back(client):
    ben = auth(client, "ben")
    parent = client.post("/api/briefs", headers=ben, json={"question": SME_QUESTION}).json()
    child = client.post(f"/api/briefs/{parent['id']}/follow-up", headers=ben, json={"question": "What about fees?"}).json()
    assert child["question"] == "What about fees?"
    assert child["follow_up_of"] == {"id": parent["id"], "question": SME_QUESTION}
    assert child["sources"], "the follow-up searches with the earlier question, so it finds the SME studies"
    listed = client.get("/api/briefs", headers=ben).json()
    assert listed[0]["question"] == "What about fees?"
    # Someone else's brief cannot be continued.
    other = client.post(f"/api/briefs/{parent['id']}/follow-up", headers=auth(client, "carla"),
                        json={"question": "What about fees?"})
    assert other.status_code == 404


def test_unanswered_questions_sit_next_to_their_closest_topic(client):
    ben = auth(client, "ben")
    client.post("/api/briefs", headers=ben, json={"question": "How do sari-sari store owners use supplier credit?"})
    data = client.get("/api/gaps", headers=auth(client, "ana")).json()
    (u,) = [x for x in data["unanswered"] if "sari-sari" in x["question"]]
    assert u["topic"]
    row = next(r for r in data["rows"] if r["label"] == u["topic"])
    assert row["unanswered"] >= 1 and "SME Banking" in row["teams"]
