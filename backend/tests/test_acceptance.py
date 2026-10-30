"""The acceptance tests from the client-consultation revision, one per numbered criterion.
Criterion 6 (permissions and red-team) is covered by test_permissions.py and test_redteam.py."""

import re
from decimal import Decimal

import psycopg
import pytest

from app.validators import NO_QUANT_MESSAGE, QUAL_DISCLAIMER, has_hedge
from tests.conftest import CARDS_QUESTION, QR_QUESTION, SME_QUESTION, auth, brief_text


def ask(client, who, question):
    response = client.post("/api/briefs", headers=auth(client, who), json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def cited_codes(brief, claim):
    return {brief["sources"][e["finding_id"]]["study_code"] for e in claim["evidence"]}


# 1 -----------------------------------------------------------------------------------------------
def test_1_sme_drop_off_brief_for_a_fully_entitled_user(client):
    brief = ask(client, "ben", SME_QUESTION)

    headline = [c for c in brief["claims"] if c["kind"] == "headline"]
    assert len(headline) == 1
    assert cited_codes(brief, headline[0]) & {"SI-2026-014", "SI-2025-009"}

    fees = [n for n in brief["context_notes"] if n["topic"] == "barrier:fees"]
    assert len(fees) == 1
    assert {"age", "region"} <= set(fees[0]["differs_by"])
    # Surveys and focus groups are never compared: the Cebu FGD's view on fees is colour, not a
    # side of the divergence, so "method" never separates the groups in a context note.
    assert "method" not in fees[0]["differs_by"]
    assert all(brief["sources"][i]["evidence_kind"] == "quant" for i in fees[0]["finding_ids"])
    assert [c for c in brief["qual_contrasts"] if brief["sources"][c["finding_id"]]["study_code"] == "SI-2025-031"]

    assert not re.search(r"conflict|disagree|contradict", brief_text(brief), re.IGNORECASE)
    assert brief["unresolved_conflicts"] == []
    assert brief["charts"] and all(len(chart["bars"]) >= 2 for chart in brief["charts"])

    cebu = [c for c in brief["claims"] if c["kind"] == "qualitative_insight"
            and "SI-2025-031" in cited_codes(brief, c) and c["verbatim_ids"]]
    assert cebu, "the Cebu FGD should appear under What people say with a verbatim"
    assert all(c["qual_only"] and has_hedge(c["text"]) for c in cebu)
    assert all(brief["sources"][v]["finding_type"] == "verbatim" for c in cebu for v in c["verbatim_ids"])
    assert brief["confidence"]["level"] == "high"


# 2 -----------------------------------------------------------------------------------------------
def test_2_qual_only_question_has_no_headline_and_a_disclaimer(client):
    brief = ask(client, "ben", QR_QUESTION)
    assert brief["claims"] and all(c["kind"] == "qualitative_insight" for c in brief["claims"])
    assert brief["no_headline_message"] == NO_QUANT_MESSAGE
    assert brief["disclaimer"] == QUAL_DISCLAIMER
    claims = " ".join(c["text"] for c in brief["claims"])
    assert not re.search(r"\d\s?%|\bpercent\b|\bmost\b", claims, re.IGNORECASE)
    assert brief["confidence"]["level"] == "low"
    assert brief["charts"] == []


# 3 -----------------------------------------------------------------------------------------------
def test_3_every_chart_value_equals_the_database_value(client, db):
    bars = [bar for q in (SME_QUESTION, CARDS_QUESTION) for chart in ask(client, "ana", q)["charts"]
            for bar in chart["bars"]]
    assert len(bars) >= 6
    with db.as_service() as conn:
        stored = {r["id"]: r for r in conn.execute(
            "select id::text as id, value, base_n, finding_type from public.findings where id = any(%s::uuid[])",
            [[b["finding_id"] for b in bars]])}
    for bar in bars:
        row = stored[bar["finding_id"]]
        assert row["finding_type"] == "quant_stat"
        assert Decimal(str(bar["value"])) == row["value"]
        assert bar["base_n"] == row["base_n"]


# 4 -----------------------------------------------------------------------------------------------
def test_4_fieldwork_change_recomputes_tier_and_overrides_are_audited(client, db, study_ids):
    study = study_ids["SI-2026-014"]
    headers = auth(client, "ana")
    assert client.get(f"/api/studies/{study}", headers=headers).json()["robustness_tier"] == "A"

    moved = client.patch(f"/api/review/studies/{study}", headers=headers, json={"fieldwork_end": "2023-01-31"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["robustness_tier"] == "B"            # 45 months old: recency -1
    assert moved.json()["tier_breakdown"]["recency_points"] == -1

    no_reason = client.patch(f"/api/review/studies/{study}", headers=headers, json={"tier_override": "A"})
    assert no_reason.status_code == 422
    blank = client.patch(f"/api/review/studies/{study}", headers=headers,
                         json={"tier_override": "A", "tier_override_reason": "   "})
    assert blank.status_code == 422

    overridden = client.patch(f"/api/review/studies/{study}", headers=headers, json={
        "tier_override": "A", "tier_override_reason": "Re-weighted panel; S&I methods lead confirmed robustness."})
    assert overridden.status_code == 200
    assert overridden.json()["effective_tier"] == "A" and overridden.json()["robustness_tier"] == "B"

    with db.as_service() as conn:
        rows = conn.execute("select action, actor_id::text as actor, details from public.audit_log "
                            "where entity_id = %s order by id", [study]).fetchall()
    actions = [r["action"] for r in rows]
    assert "study.tier_recomputed" in actions
    override = [r for r in rows if r["action"] == "study.tier_override_set"]
    assert len(override) == 1
    assert override[0]["details"]["to"] == "A" and override[0]["details"]["reason"].startswith("Re-weighted")
    assert override[0]["actor"] is not None

    # The database itself refuses an override without a reason, whatever the path.
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.as_service() as conn:
            conn.execute("update public.studies set tier_override = 'C', tier_override_reason = null where id = %s", [study])


# 5 -----------------------------------------------------------------------------------------------
def test_5_unresolved_conflict_pair_is_flagged_low_and_escalated(client):
    brief = ask(client, "carla", CARDS_QUESTION)
    pairs = {frozenset(brief["sources"][i]["study_code"] for i in n["finding_ids"]) for n in brief["unresolved_conflicts"]}
    assert frozenset({"SI-2026-021", "SI-2026-027"}) in pairs
    assert all(n["differs_by"] == [] for n in brief["unresolved_conflicts"])
    assert brief["confidence"]["level"] == "low"
    assert brief["escalation"] and brief["escalation"]["reason"] == "unresolved_conflict"

    desk = client.get("/api/escalations", headers=auth(client, "ana")).json()
    assert any(e["brief_id"] == brief["id"] and e["status"] == "open" for e in desk)
    stored = client.get(f"/api/briefs/{brief['id']}", headers=auth(client, "carla")).json()
    assert stored["escalation"]["status"] == "open"


def test_a_conflict_already_with_an_analyst_shows_on_later_briefs(client):
    """Asking again links to the open escalation instead of raising a new one; the later brief must
    still show it (the bug hunt saw escalation: null)."""
    carla = auth(client, "carla")
    first = client.post("/api/briefs", headers=carla, json={"question": CARDS_QUESTION}).json()
    second = client.post("/api/briefs", headers=carla, json={"question": CARDS_QUESTION}).json()
    assert first["escalation"] and second["escalation"]["id"] == first["escalation"]["id"]
    stored = client.get(f"/api/briefs/{second['id']}", headers=carla).json()
    assert stored["escalation"]["id"] == first["escalation"]["id"]
    assert stored["escalation"]["status"] == "open"


def test_gaps_name_only_cited_studies(client):
    brief = client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SME_QUESTION}).json()
    import re as _re
    for gap in brief["gap_items"]:
        for code in _re.findall(r"SI-\d{4}-\d{3}", gap["text"] + " " + (gap.get("ask") or "")):
            assert code in {s["study_code"] for s in brief["sources"].values()}, gap


def test_emotion_tags_match_the_feelings_a_claim_names(client):
    brief = client.post("/api/briefs", headers=auth(client, "ben"), json={"question": QR_QUESTION}).json()
    for claim in brief["claims"]:
        if "Feelings voiced include" in claim["text"]:
            named = claim["text"].split("Feelings voiced include", 1)[1].lower()
            assert claim["emotions"] and all(e["label"].lower() in named for e in claim["emotions"])
