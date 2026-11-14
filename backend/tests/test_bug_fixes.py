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


# QA 30 Oct: a headline honours a place the question names -----------------------------------------
def test_headline_answers_for_the_place_the_question_names(client):
    brief = ask(client, "ana", "Are long ATM queues a problem outside Metro Manila?")
    headline = next(c for c in brief["claims"] if c["kind"] == "headline")
    assert "Metro Manila, 57%" not in headline["text"]
    assert "Luzon outside NCR, 24%" in headline["text"] and "Visayas, 19%" in headline["text"]


def test_a_headline_for_another_place_is_sent_back():
    sources = {"F1": src("F1", metric="atm:long_queues", value=57, subgroup={"region": "NCR"}),
               "F2": src("F2", metric="atm:long_queues", value=19, subgroup={"region": "Visayas"})}
    brief = EvidenceBrief(claims=[Claim(text="In Metro Manila, 57% said long lines were a problem.", kind="headline",
                                        evidence=[Evidence(finding_id="F1", stance="supports")])],
                          context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])
    issues = validate_brief(brief, sources, [], question="Are ATM queues a problem in the provinces?")
    assert [i.code for i in issues] == ["headline_ignores_place"] and issues[0].section == "brief"
    assert not validate_brief(brief, sources, [], question="Are ATM queues a problem in Metro Manila?")


# QA 30 Oct: disputed figures are marked wherever they appear ---------------------------------------
def test_disputed_figures_never_appear_as_plain_claims_or_unmarked_bars(client):
    brief = ask(client, "carla", CARDS_QUESTION)
    disputed = {fid for n in brief["unresolved_conflicts"] for fid in n["finding_ids"]}
    assert len(brief["unresolved_conflicts"]) == 2   # cashback and travel
    for claim in brief["claims"]:
        cited = {e["finding_id"] for e in claim["evidence"]}
        for note in brief["unresolved_conflicts"]:
            # A claim that uses one side of a dispute uses both, and says so.
            if cited & set(note["finding_ids"]):
                assert set(note["finding_ids"]) <= cited and "checking" in claim["text"]
        assert bool(claim["disputed"]) == bool(cited & disputed)
    bars = [b for chart in brief["charts"] for b in chart["bars"]]
    assert bars and all(b["disputed"] == (b["finding_id"] in disputed) for b in bars)


def test_a_breakdown_stating_one_side_of_a_dispute_is_sent_back():
    a = src("A", study="S1", metric="reward_pref:travel", value=47)
    b = src("B", study="S2", metric="reward_pref:travel", value=19, direction="low")
    groups = analyze([a.ctx(), b.ctx()])
    assert [g.kind for g in groups] == ["unresolved_conflict"]
    brief = EvidenceBrief(claims=[Claim(text="Travel rewards were the first choice for 47%.", kind="breakdown",
                                        evidence=[Evidence(finding_id="A", stance="supports")])],
                          context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])
    assert "breakdown_hides_conflict" in [i.code for i in validate_brief(brief, {"A": a, "B": b}, groups)]


# QA 30 Oct: a follow-up is threaded under the first request on the analyst desk ----------------------
def test_follow_ups_share_the_first_requests_thread(client):
    first = ask(client, "ben", SME_QUESTION)
    again = ask(client, "ben", SME_QUESTION.upper())   # asking again makes a new brief
    other = ask(client, "ben", "What do SME owners think about relationship managers?")
    headers = auth(client, "ben")
    for brief, note in ((first, "Does this hold for Visayas?"), (again, "And for owners over 50?"),
                        (other, "Is there newer data?")):
        assert client.post("/api/escalations", headers=headers,
                           json={"brief_id": brief["id"], "note": note}).status_code == 200
    rows = client.get("/api/escalations", headers=auth(client, "ana")).json()
    by_note = {r["note"]: r for r in rows}
    root = by_note["Does this hold for Visayas?"]
    assert root["thread_id"] == root["id"]
    assert by_note["And for owners over 50?"]["thread_id"] == root["id"]
    assert by_note["Is there newer data?"]["thread_id"] != root["id"]


# Demo robustness: real progress while a brief is prepared, and a warning when the writer is down ------
def test_a_brief_reports_each_step_and_the_page_can_poll_it(db, people, client):
    from app.embeddings import HashingEmbedder
    from app.llm import OfflineLLM
    from app.synthesis import BriefService

    steps: list[int] = []
    service = BriefService(db, OfflineLLM(), HashingEmbedder(), fallback_llm=OfflineLLM())
    service.ask(people["ben"], SME_QUESTION, report=lambda step, detail=None: steps.append(step))
    assert steps[:4] == [0, 1, 2, 3]
    # Nothing is running for this user, so the poll answers null rather than a stale step.
    assert client.get("/api/briefs/progress", headers=auth(client, "ben")).json() is None


def test_health_says_whether_the_brief_writer_can_be_reached(client):
    body = client.get("/api/health").json()
    assert body["llm_ready"] is True and body["llm_problem"] is None   # templates are always available


# C6: confidence counts only conflicts that bear on the question ---------------------------------------
def test_a_conflict_on_a_nearby_figure_caps_confidence_but_one_on_the_question_makes_it_low():
    from app.confidence import compute_confidence
    from app.schemas import ContextNote

    answer = src("A", study="S0", metric="card_dropoff:fees", value=37)
    t1 = src("T1", study="S1", metric="reward_pref:travel", value=47)
    t2 = src("T2", study="S2", metric="reward_pref:travel", value=19, direction="low")
    sources = {"A": answer, "T1": t1, "T2": t2}
    brief = EvidenceBrief(
        claims=[Claim(text="Fees were a reason 37% did not finish.", kind="headline",
                      evidence=[Evidence(finding_id="A", stance="supports")]),
                Claim(text="Travel rewards: S1 found 47%; S2 found 19%. An analyst is checking.", kind="breakdown",
                      evidence=[Evidence(finding_id="T1", stance="supports"), Evidence(finding_id="T2", stance="supports")])],
        context_notes=[], chart_requests=[], gaps=[],
        unresolved_conflicts=[ContextNote(topic="reward_pref:travel", finding_ids=["T1", "T2"], differs_by=[],
                                          explanation="S1 found 47%; S2 found 19%.")])
    nearby = compute_confidence(brief, sources, question="Are annual fees a reason applicants give up?")
    assert nearby["level"] == "medium" and any("related figure" in r for r in nearby["reasons"])
    assert compute_confidence(brief, sources, question="Do applicants prefer travel rewards?")["level"] == "low"
    assert compute_confidence(brief, sources)["level"] == "low"   # no question: every conflict counts


# S10: usage summary for S&I from the audit log -----------------------------------------------------------
def test_si_sees_what_teams_asked_and_what_no_study_answered(client):
    ask(client, "ben", SME_QUESTION)
    ask(client, "ben", SME_QUESTION)
    ask(client, "carla", "What is the average home mortgage rate customers expect?")
    assert client.get("/api/audit/summary", headers=auth(client, "ben")).status_code == 403
    body = client.get("/api/audit/summary", headers=auth(client, "ana")).json()
    assert body["briefs"]["total"] == 3
    assert body["most_asked"][0] == {"question": SME_QUESTION, "count": 2}
    assert [u["question"] for u in body["unanswered"]] == ["What is the average home mortgage rate customers expect?"]
    assert {t["team"] for t in body["briefs"]["by_team"]} == {"SME Banking", "Cards & Payments"}


def test_an_unreachable_hosted_search_model_gives_a_plain_503(make_client):
    from app.embeddings import EmbeddingUnavailable, HashingEmbedder

    class DownEmbedder(HashingEmbedder):
        def embed_query(self, text):
            raise EmbeddingUnavailable("Bedrock embed error: Token has expired and refresh failed")

    client = make_client(embedder=DownEmbedder())
    response = client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SME_QUESTION})
    assert response.status_code == 503 and "sign in to AWS" in response.json()["detail"]
    health = client.get("/api/health").json()
    assert health["search_ready"] is True   # a local embedder never needs AWS
