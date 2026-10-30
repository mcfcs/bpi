"""Regression tests for the bug hunt against the live build (numbered as reported)."""

from datetime import date, timedelta

import httpx

from app.commissioning import WebhookAdapter
from app.divergence import analyze
from app.schemas import Claim, Evidence, EvidenceBrief
from app.validators import validate_brief
from tests.conftest import CARDS_QUESTION, SME_QUESTION, auth
from tests.fakes import ScriptedLLM
from tests.test_consultation_rules import ask, src


def coverage(client, who, objectives, title="Coverage check"):
    response = client.post("/api/commissioning/coverage", headers=auth(client, who),
                           json={"title": title, "objectives": objectives})
    assert response.status_code == 200, response.text
    return response.json()


# 1 --------------------------------------------------------------------------------------------
def test_1_topics_no_study_measures_are_not_covered(client):
    check = coverage(client, "ben", ["Measure how often SME owners renew loans digitally"])
    assert check["result"]["objectives"][0]["coverage"] == "gap"
    assert "reuse them" not in check["result"]["recommended_new_scope"]
    brief = ask(client, "ben", "What slowed down SME loan renewals?")
    assert brief["claims"] == [] and brief["confidence"]["level"] == "low"


# 2 --------------------------------------------------------------------------------------------
def test_2_coverage_flags_conflicts_and_restricted_studies(client):
    objective = ["Find out whether young professionals prefer cashback or travel rewards on credit cards"]
    carla = coverage(client, "carla", objective)["result"]
    (o,) = carla["objectives"]
    assert o["coverage"] == "covered" and [c["code"] for c in o["caveats"]] == ["conflict"]
    assert "reuse them" not in carla["recommended_new_scope"] and "analyst" in carla["recommended_new_scope"]
    ben = coverage(client, "ben", objective)["result"]
    (o,) = ben["objectives"]
    restricted = [c for c in o["caveats"] if c["code"] == "restricted_match"]
    assert restricted and restricted[0]["studies"][0]["code"] == "SI-2026-027"
    assert set(restricted[0]["studies"][0]) == {"study_id", "code", "title", "owner_team"}   # metadata only
    assert "request access" in ben["recommended_new_scope"]


# 3 --------------------------------------------------------------------------------------------
def test_3_confidence_reflects_only_readable_studies_when_a_restricted_one_matches(client):
    brief = ask(client, "ben", CARDS_QUESTION)
    assert [m["code"] for m in brief["restricted_matches"]] == ["SI-2026-027"]
    assert brief["confidence"]["level"] == "medium"
    assert any("only the studies you can read" in r for r in brief["confidence"]["reasons"])
    assert "21%" not in str(brief["confidence"]) and "Travel rewards were the first choice" not in str(brief)


# 4 --------------------------------------------------------------------------------------------
def test_4_headline_on_a_disputed_metric_says_what_each_study_found(client):
    brief = ask(client, "carla", CARDS_QUESTION)
    (headline,) = [c for c in brief["claims"] if c["kind"] == "headline"]
    codes = {brief["sources"][e["finding_id"]]["study_code"] for e in headline["evidence"]}
    assert codes == {"SI-2026-021", "SI-2026-027"}
    assert "54%" in headline["text"] and "21%" in headline["text"] and "aged 25–35 in Metro Manila" in headline["text"]


def test_4_validator_rejects_a_headline_that_hides_a_conflict():
    a = src("a", "A", metric="reward_pref:cashback", value=54, ages=(25, 35))
    b = src("b", "B", metric="reward_pref:cashback", value=21, direction="low", ages=(25, 35))
    groups = analyze([a.ctx(), b.ctx()])
    draft = EvidenceBrief(claims=[Claim(text="Cashback wins (54%).", kind="headline",
                                        evidence=[Evidence(finding_id="a", stance="supports")])],
                          context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])
    assert "headline_hides_conflict" in {i.code for i in validate_brief(draft, {"a": a, "b": b}, groups)}


# 5 --------------------------------------------------------------------------------------------
def test_5_headline_answers_the_question_asked(client):
    brief = ask(client, "ben", "Are fees a barrier for SME loans?")
    (headline,) = [c for c in brief["claims"] if c["kind"] == "headline"]
    assert {brief["sources"][e["finding_id"]]["metric_key"] for e in headline["evidence"]} == {"barrier:fees"}


# 6 --------------------------------------------------------------------------------------------
def test_6_junk_questions_return_no_evidence(client):
    for question in ("'; drop table findings; --", "select * from findings"):
        brief = ask(client, "ben", question)
        assert brief["claims"] == [] and brief["sources"] == {} and brief["confidence"]["level"] == "low"


# 7 --------------------------------------------------------------------------------------------
def test_7_charts_show_only_studies_the_brief_cites(make_client):
    def script(request, attempt):
        ref = next(r for r, s in request.findings if s.study_code == "SI-2026-014" and s.metric_key == "barrier:fees")
        return EvidenceBrief(claims=[Claim(text="Fees matter.", kind="breakdown", evidence=[Evidence(finding_id=ref, stance="supports")])],
                             context_notes=[], unresolved_conflicts=[], chart_requests=["barrier:fees"], gaps=[])

    client = make_client(llm=ScriptedLLM(script))
    brief = ask(client, "ben", SME_QUESTION)
    cited = {v["study_code"] for v in brief["sources"].values()}
    bars = {b["study_code"] for chart in brief["charts"] for b in chart["bars"]}
    assert bars and bars <= cited


# 8 --------------------------------------------------------------------------------------------
def test_8_automatic_escalations_are_not_duplicated(client):
    first = ask(client, "carla", CARDS_QUESTION)
    second = ask(client, "carla", CARDS_QUESTION)
    assert first["escalation"]["id"] == second["escalation"]["id"]
    desk = client.get("/api/escalations", headers=auth(client, "ana")).json()
    assert len([e for e in desk if e["reason"] == "unresolved_conflict" and e["status"] == "open"]) == 1
    assert ask(client, "ana", CARDS_QUESTION)["escalation"] is None      # S&I's own briefs stay with S&I


def test_8_a_second_reply_is_appended_and_audited(client, db):
    headers = auth(client, "carla")
    created = client.post("/api/escalations", headers=headers, json={"note": "Please check the cashback figures."}).json()
    ana = auth(client, "ana")
    client.post(f"/api/escalations/{created['id']}/respond", headers=ana, json={"response": "First answer."})
    client.post(f"/api/escalations/{created['id']}/respond", headers=ana, json={"response": "Second answer."})
    (row,) = [e for e in client.get("/api/escalations", headers=ana).json() if e["id"] == created["id"]]
    assert "First answer." in row["response"] and "Second answer." in row["response"]
    with db.as_service() as conn:
        details = [r["details"] for r in conn.execute(
            "select details from public.audit_log where entity_id = %s and action = 'escalation.answered' order by id",
            [created["id"]])]
    assert [d["follow_up"] for d in details] == [False, True] and details[1]["reply_excerpt"] == "Second answer."


def test_8_the_brief_carries_its_escalation_thread(client):
    brief = ask(client, "carla", SME_QUESTION)
    headers = auth(client, "carla")
    first = client.post("/api/escalations", headers=headers, json={"brief_id": brief["id"], "note": "First question."}).json()
    second = client.post("/api/escalations", headers=headers, json={"brief_id": brief["id"], "note": "Second question."}).json()
    client.post(f"/api/escalations/{first['id']}/respond", headers=auth(client, "ana"), json={"response": "Answered."})
    stored = client.get(f"/api/briefs/{brief['id']}", headers=headers).json()
    assert [e["id"] for e in stored["escalations"]] == [first["id"], second["id"]]          # oldest first
    assert stored["escalations"][0]["response"] == "Answered." and stored["escalations"][0]["responded_by"] == "Ana Reyes"
    assert stored["escalation"]["id"] == second["id"]                                       # latest, as before
    assert set(stored["escalations"][0]) == {"id", "status", "reason", "note", "response", "responded_by",
                                             "responded_at", "created_at"}


# 9 --------------------------------------------------------------------------------------------
def test_9_access_cannot_be_granted_with_a_past_expiry(client, study_ids):
    created = client.post("/api/access-requests", headers=auth(client, "carla"), json={
        "study_id": study_ids["SI-2026-014"], "purpose": "Benchmark card onboarding drop-off."}).json()
    past = client.post(f"/api/access-requests/{created['id']}/decision", headers=auth(client, "dino"),
                       json={"approve": True, "expires_at": "2020-01-01"})
    assert past.status_code == 422
    future = (date.today() + timedelta(days=30)).isoformat()
    ok = client.post(f"/api/access-requests/{created['id']}/decision", headers=auth(client, "dino"),
                     json={"approve": True, "expires_at": future})
    assert ok.status_code == 200, ok.text


# 10 -------------------------------------------------------------------------------------------
def test_10_generated_wording_is_clean(client):
    check = coverage(client, "ben", ["How do OFW families use remittance apps?",
                                     "Understand why SME owners abandon online loan applications"])
    scope = check["result"]["recommended_new_scope"]
    assert "?." not in scope and "“How do OFW families use remittance apps?”" in scope
    assert "cover Understand" not in scope
    brief = ask(client, "ben", SME_QUESTION)
    split = next(c["text"] for c in brief["claims"] if "by subgroup" in c["text"] and "Fees" in c["text"])
    assert split.index("Ages 20–29") < split.index("Ages 30–40")


# 11 -------------------------------------------------------------------------------------------
def test_11_blank_and_nul_inputs_are_rejected(client, study_ids):
    headers = auth(client, "ben")
    assert client.post("/api/briefs", headers=headers, json={"question": "     a     "}).status_code == 422
    assert client.post("/api/briefs", headers=headers, json={"question": "Why fees?\x00"}).status_code == 422
    assert client.post("/api/commissioning/coverage", headers=headers,
                       json={"title": "   ", "objectives": ["Understand fees"]}).status_code == 422
    assert client.post("/api/commissioning/coverage", headers=headers,
                       json={"title": "A title", "objectives": ["   ", ""]}).status_code == 422
    assert client.post("/api/commissioning/coverage", headers=headers,
                       json={"title": "A title", "objectives": ["x" * 501]}).status_code == 422
    assert client.post("/api/escalations", headers=headers, json={"note": "   "}).status_code == 422
    assert client.post("/api/access-requests", headers=auth(client, "carla"),
                       json={"study_id": study_ids["SI-2026-014"], "purpose": "          "}).status_code == 422


# 12 -------------------------------------------------------------------------------------------
def test_12_exports_label_restricted_findings_and_submit_is_once(client, make_client):
    check = coverage(client, "ben", ["Understand why SME owners abandon online loan applications"])
    headers = auth(client, "ben")
    exported = client.get(f"/api/commissioning/{check['id']}/export.json", headers=headers).json()
    restricted = [f for f in exported["findings"] if f["access_level"] == "restricted"]
    assert restricted and restricted[0]["access_note"].startswith("Restricted - SME Banking")
    assert exported["notice"].startswith("Contains restricted findings")
    pdf = client.get(f"/api/commissioning/{check['id']}/export.pdf", headers=headers)
    assert pdf.status_code == 200

    received = []
    adapter = WebhookAdapter("https://example.invalid/flow",
                             client=httpx.Client(transport=httpx.MockTransport(lambda r: received.append(r) or httpx.Response(202))))
    hooked = make_client(adapter=adapter)
    check = coverage(hooked, "ben", ["Understand why SME owners abandon online loan applications"])
    first = hooked.post(f"/api/commissioning/{check['id']}/submit", headers=auth(hooked, "ben")).json()
    second = hooked.post(f"/api/commissioning/{check['id']}/submit", headers=auth(hooked, "ben")).json()
    assert len(received) == 1 and first["status"] == "sent"
    assert second["already_submitted"] is True and second["status"] == "sent"
