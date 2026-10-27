from datetime import date

from app.config import REPO_DIR
from app.jobs.recompute_tiers import recompute_all
from app.offline_extract import extract
from tests.conftest import auth

REPORTS = REPO_DIR / "data" / "synthetic" / "reports"


def test_offline_extraction_fills_the_study_card():
    card = extract((REPORTS / "sme-loan-renewal-pulse-2026.md").read_text(encoding="utf-8"))
    assert card.method_type == "quant"
    assert card.sample_size == 450
    assert card.fieldwork_end == "2026-06-05"
    assert (card.population.age_min, card.population.age_max) == (25, 55)
    assert set(card.population.regions) == {"Calabarzon", "Central Luzon"}
    stats = [f for f in card.findings if f.finding_type == "quant_stat"]
    assert [f.value for f in stats][:2] == [61.0, 72.0]
    assert stats[1].subgroup.age_band == "25-34" and stats[1].base_n == 140
    assert [f.finding_type for f in card.findings].count("verbatim") == 1

    qual = extract((REPORTS / "cebu-sme-digital-onboarding-groups-2026.md").read_text(encoding="utf-8"))
    assert qual.method_type == "qual" and qual.sample_size == 28
    assert all(f.value is None for f in qual.findings)


def test_ingested_reports_wait_for_review_and_then_become_searchable(client, db):
    headers = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=headers).json()}
    report = (REPORTS / "sme-loan-renewal-pulse-2026.md").read_text(encoding="utf-8").replace(
        "SME Loan Renewal Pulse 2026", "SME Loan Renewal Pulse 2026 (second wave)")
    study = client.post("/api/ingest", headers=headers, json={
        "report_text": report, "owner_team_id": teams["SME Banking"], "access_level": "open",
        "source_name": "second-wave.md"}).json()
    assert study["review_status"] == "pending_review"
    assert study["robustness_tier"] == "A"   # computed in code from the extracted fields
    assert any(q["id"] == study["id"] for q in client.get("/api/review/queue", headers=headers).json())

    question = {"question": "Would SME borrowers renew their loans online if documents were on file?"}
    before = client.post("/api/briefs", headers=auth(client, "ben"), json=question).json()
    assert all(s["study_id"] != study["id"] for s in before["sources"].values())

    approved = client.post(f"/api/review/studies/{study['id']}/decision", headers=headers, json={"approve": True})
    assert approved.status_code == 200 and approved.json()["review_status"] == "approved"
    after = client.post("/api/briefs", headers=auth(client, "ben"), json=question).json()
    assert any(s["study_id"] == study["id"] for s in after["sources"].values())


def test_review_screen_edits_population_and_findings(client, db):
    headers = auth(client, "ana")
    (pending,) = [q for q in client.get("/api/review/queue", headers=headers).json() if q["method_type"] == "qual"]
    detail = client.get(f"/api/studies/{pending['id']}", headers=headers).json()
    assert {"method_type", "sample_size", "fieldwork_end", "population", "robustness_tier", "tier_override",
            "tier_override_reason", "effective_tier", "tier_breakdown", "findings"} <= set(detail)

    patched = client.patch(f"/api/review/studies/{pending['id']}", headers=headers, json={
        "population": {"age_min": 25, "age_max": 50, "regions": ["Cebu", "Mandaue"], "segment": "Micro and small business owners"},
        "sample_size": 30})
    assert patched.json()["population"]["regions"] == ["Cebu", "Mandaue"]

    finding = detail["findings"][0]
    updated = client.patch(f"/api/review/findings/{finding['id']}", headers=headers, json={
        "metric_key": "barrier:documents", "direction": "high", "theme": "loan_application_dropoff"})
    assert updated.status_code == 200
    assert updated.json()["metric_key"] == "barrier:documents" and updated.json()["direction"] == "high"

    bad = client.patch(f"/api/review/findings/{finding['id']}", headers=headers, json={"value": 40})
    assert bad.status_code == 422   # a value on a qualitative finding


def test_approval_needs_method_and_fieldwork(client, db):
    headers = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=headers).json()}
    vague = "# Untitled notes\n\nSome notes about loans without method or dates.\n\n## Key findings\n\n- Owners want faster loans.\n"
    study = client.post("/api/ingest", headers=headers, json={
        "report_text": vague, "owner_team_id": teams["Strategy & Insights"]}).json()
    assert study["robustness_tier"] is None
    refused = client.post(f"/api/review/studies/{study['id']}/decision", headers=headers, json={"approve": True})
    assert refused.status_code == 422


def test_nightly_job_lowers_tiers_as_studies_age(db):
    changed = recompute_all(db, date(2027, 10, 27))
    by_code = {c["code"]: c for c in changed}
    assert by_code["SI-2026-021"]["from"] == "A" and by_code["SI-2026-021"]["to"] == "B"
    with db.as_service() as conn:
        row = conn.execute("select actor_id, details from public.audit_log where action = 'study.tier_recomputed' "
                           "and entity_id = %s", [by_code["SI-2026-021"]["study_id"]]).fetchone()
    assert row["actor_id"] is None and row["details"]["trigger"] == "scheduled"
