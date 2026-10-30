"""Rules from the second S&I consultation: segment statements instead of "studies disagree",
quantitative first and never compared with qualitative, recency tiers for qualitative studies,
geography, two trends in one study, emotion cues, audience modes, persona framing, coverage
states and the generated "ask an analyst" draft."""

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app import emotion, geography
from app.commissioning import coverage_state
from app.confidence import compute_confidence
from app.describe import build_summaries, explain_group, method_detail, synthesize_themes
from app.divergence import FindingCtx, analyze
from app.llm import OfflineLLM
from app.llm_types import BriefRequest, Reader
from app.retrieval import Source
from app.schemas import AudienceSummary, Claim, ContextNote, Evidence, EvidenceBrief
from app.tiers import compute_tier, tier_breakdown
from app.validators import DISAGREE_WORDS, QUAL_FORBIDDEN, finalize, has_hedge, validate_brief, validate_summary
from tests.conftest import QR_QUESTION, SME_QUESTION, TODAY, auth, brief_text
from tests.fakes import ScriptedLLM

GENZ_QUESTION = "What stops Gen Z customers from finishing digital card applications?"
APP_QUESTION = "How has satisfaction with the mobile app changed between survey waves?"
ATM_QUESTION = "Are long ATM queues a problem outside Metro Manila?"
BANNED = re.compile(r"\b(?:conflict\w*|disagree\w*|contradict\w*)\b", re.IGNORECASE)


def ask(client, who, question, **extra):
    response = client.post("/api/briefs", headers=auth(client, who), json={"question": question, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def codes_of(brief, ids):
    return {brief["sources"][i]["study_code"] for i in ids if i in brief["sources"]}


def src(fid, study="S1", method="quant", tier="A", finding_type="quant_stat", metric="card_dropoff:fees",
        value=37, direction="high", subgroup=None, end=date(2026, 7, 31), regions=("NCR",), ages=(20, 40),
        segment="Credit card applicants", sample=1200, code=None, title="Study", summary=None) -> Source:
    return Source(
        finding_id=fid, study_id=study, text=f"finding {fid}", theme=None, finding_type=finding_type,
        metric_key=metric, value=None if value is None else Decimal(str(value)), unit="%" if value is not None else None,
        base_n=sample, subgroup=subgroup, direction=direction, study_code=code or f"SI-{study}", study_title=title,
        method_type=method, sample_size=sample, fieldwork_end=end,
        population={"age_min": ages[0], "age_max": ages[1], "regions": list(regions), "segment": segment},
        effective_tier=tier, robustness_tier=tier, tier_override=None, owner_team="Cards & Payments",
        access_level="open", study_summary=summary,
    )


# 1. Segment statements, never "studies disagree" ------------------------------------------------
def test_context_difference_is_a_segment_statement_naming_who_where_and_when(client):
    brief = ask(client, "carla", GENZ_QUESTION)
    (fees,) = [n for n in brief["context_notes"] if n["topic"] == "card_dropoff:fees"]
    text = fees["explanation"]
    assert text.startswith("Fees: a driver of drop-off among credit card applicants aged 20–40 in Metro Manila")
    assert "not a driver of drop-off among credit card applicants aged 41–60 nationwide" in text
    assert "SI-2026-041, survey of 1,200, Jul 2026: 37%" in text and "SI-2025-018, survey of 900, Feb 2025: 11%" in text
    assert set(fees["differs_by"]) == {"age", "region"}
    assert not BANNED.search(brief_text(brief))
    headline = [c for c in brief["claims"] if c["kind"] == "headline"][0]
    lead = brief["sources"][headline["evidence"][0]["finding_id"]]
    assert lead["metric_key"] == "card_dropoff:id_verification" and lead["study_code"] == "SI-2026-041"
    assert "NCR, ages 20–40" in headline["text"]


def test_unresolved_conflict_says_what_each_found_and_that_an_analyst_is_checking():
    a = src("a", "F", metric="reward_pref:cashback", value=54, ages=(25, 35), end=date(2026, 2, 27), code="SI-2026-021")
    b = src("b", "G", metric="reward_pref:cashback", value=21, direction="low", ages=(25, 35), end=date(2026, 4, 30),
            code="SI-2026-027")
    (group,) = analyze([a.ctx(), b.ctx()])
    text = explain_group(group, {"a": a, "b": b})
    assert "SI-2026-021 found 54%" in text and "SI-2026-027 found 21%" in text
    assert "analyst is checking" in text and not DISAGREE_WORDS.search(text)


def test_disagreement_wording_is_rejected_and_rewritten():
    a = src("a", "A", ages=(20, 40))
    b = src("b", "B", value=11, direction="low", ages=(41, 60), regions=("Nationwide",))
    sources = {"a": a, "b": b}
    groups = analyze([a.ctx(), b.ctx()])
    note = ContextNote(topic="card_dropoff:fees", finding_ids=["a", "b"], differs_by=["age", "region"],
                       explanation="The two studies disagree on fees.")
    draft = EvidenceBrief(claims=[Claim(text="Fees vary.", kind="breakdown", evidence=[Evidence(finding_id="a", stance="supports")])],
                          context_notes=[note], unresolved_conflicts=[], chart_requests=[], gaps=[])
    issues = validate_brief(draft, sources, groups)
    assert "disagreement_wording" in {i.code for i in issues}
    final, _ = finalize(draft, issues, sources, groups, [])
    assert not DISAGREE_WORDS.search(final.context_notes[0].explanation)
    assert final.context_notes[0].explanation.startswith("Fees: a driver of drop-off among")


# 2. Quantitative first; quantitative and qualitative never compared ------------------------------
def test_quant_and_qual_findings_are_never_a_divergence():
    quant = FindingCtx("q", "Q", "card_dropoff:fees", "high", "quant", 20, 40, ("NCR",), "Applicants", date(2026, 7, 31))
    qual = FindingCtx("f", "F", "card_dropoff:fees", "low", "qual", 20, 29, ("Cebu City",), "Applicants", date(2026, 8, 31))
    assert analyze([quant, qual]) == []
    other_qual = FindingCtx("g", "G", "card_dropoff:fees", "high", "qual", 20, 29, ("Davao City",), "Applicants", date(2025, 5, 31))
    (group,) = analyze([quant, qual, other_qual])           # qual with qual can still be compared
    assert set(group.finding_ids) == {"f", "g"}


def test_qual_running_against_quant_is_colour_in_what_people_say(client):
    brief = ask(client, "carla", GENZ_QUESTION)
    contrast = [c for c in brief["qual_contrasts"] if codes_of(brief, [c["finding_id"]]) == {"SI-2026-044"}]
    assert contrast and contrast[0]["topic"] == "card_dropoff:fees"
    claim = [c for c in brief["claims"] if contrast[0]["finding_id"] in [e["finding_id"] for e in c["evidence"]]
             and c["kind"] == "qualitative_insight" and "runs against" in c["text"]]
    assert claim and claim[0]["qual_only"] and has_hedge(claim[0]["text"])
    assert "SI-2026-044, 6 FGDs, 48 participants, Aug 2026" in claim[0]["text"]
    kinds = [c["kind"] for c in brief["claims"]]
    assert kinds == sorted(kinds, key=["headline", "breakdown", "qualitative_insight"].index)   # quant first
    for note in brief["context_notes"] + brief["unresolved_conflicts"]:
        assert all(brief["sources"][i]["evidence_kind"] == "quant" for i in note["finding_ids"])


# 3. Tiers: survey > FGDs; qualitative weighted by recency; visible method labels -----------------
def test_qualitative_tiers_follow_recency_and_never_reach_a():
    assert compute_tier("qual", 48, date(2026, 8, 31), TODAY) == "B"
    assert compute_tier("qual", 48, date(2025, 5, 31), TODAY) == "C"
    assert compute_tier("qual", 4800, date(2025, 5, 31), TODAY) == "C"   # size never helps
    assert compute_tier("quant", 1200, date(2026, 7, 31), TODAY) == "A"   # n=1,200 survey > 6 FGDs
    breakdown = tier_breakdown("qual", 48, date(2026, 8, 31), TODAY)
    assert breakdown["basis"] == "recency" and breakdown["sample_points"] == 0


def test_a_recent_focus_group_never_raises_confidence():
    qual_b = src("f", "F", method="qual", tier="B", finding_type="qual_theme", value=None)
    quant_c = src("c", "C", tier="C")
    brief = EvidenceBrief(claims=[Claim(text="x", kind="breakdown", evidence=[
        Evidence(finding_id="c", stance="supports"), Evidence(finding_id="f", stance="supports")])],
        context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])
    assert compute_confidence(brief, {"f": qual_b, "c": quant_c})["level"] == "low"


def test_sources_show_method_detail_and_fieldwork_month(client):
    brief = ask(client, "carla", GENZ_QUESTION)
    views = {v["study_code"]: v for v in brief["sources"].values()}
    assert views["SI-2026-041"]["method_detail"] == "Survey · n=1,200"
    assert views["SI-2026-044"]["method_detail"] == "6 FGDs · 48 participants"
    assert views["SI-2025-036"]["method_detail"] == "20 in-depth interviews · 20 participants"
    assert views["SI-2026-044"]["fieldwork_label"] == "Aug 2026" and views["SI-2026-044"]["tier"] == "B"
    assert views["SI-2026-044"]["tier_basis"].startswith("Recency only")
    assert method_detail(src("x", method="qual", sample=12, title="Groups", summary="Two focus groups in Cebu")) == "2 FGDs · 12 participants"


# 4. All-qualitative evidence: themes across groups, emotions, no incidence -----------------------
def test_qual_themes_are_synthesised_across_groups_with_feelings(client):
    brief = ask(client, "carla", GENZ_QUESTION)
    synthesis = next(c for c in brief["claims"] if c["kind"] == "qualitative_insight")
    assert "ID verification in the Cebu City and Iloilo City groups (Aug 2026) and the Davao City interviews (May 2025)" in synthesis["text"]
    assert "Feelings voiced include" in synthesis["text"] and has_hedge(synthesis["text"])
    assert not QUAL_FORBIDDEN.search(synthesis["text"])
    assert any(e["key"] == "frustration" for c in brief["claims"] for e in c["emotions"])
    verbatims = [v for v in brief["sources"].values() if v["finding_type"] == "verbatim" and v["emotion"]]
    assert {v["emotion"]["key"] for v in verbatims} & {"frustration", "confusion", "distrust"}


def test_all_qual_brief_stays_hedged_in_every_register(client):
    brief = ask(client, "ben", QR_QUESTION)
    assert all(c["kind"] == "qualitative_insight" for c in brief["claims"])
    for summary in brief["summaries"].values():
        assert has_hedge(summary["text"]) and not QUAL_FORBIDDEN.search(summary["text"])
    assert brief["confidence"]["level"] == "low"


@pytest.mark.parametrize("text, key", [
    ("Tatlong beses na akong nag-selfie, ayaw pa rin tanggapin. Nakakainis.", "frustration"),
    ("I wasn't sure which ID they wanted. I got confused and stopped.", "confusion"),
    ("I didn't want to send my ID to an app I wasn't sure was really the bank's.", "distrust"),
    ("Mas mabilis, mas panatag ako.", "relief"),
    ("QR is convenient for small amounts.", "convenience"),
])
def test_emotion_lexicon(text, key):
    assert emotion.detect(text)["key"] == key


def test_theme_synthesis_needs_two_themes():
    one = src("t", "T", method="qual", finding_type="qual_theme", value=None, regions=("Cebu City",))
    assert synthesize_themes([one]) is None


# 5. Geography --------------------------------------------------------------------------------
def test_area_types_and_phrases():
    assert geography.area_type(["NCR"]) == "metro_manila"
    assert geography.area_type(["Cebu City", "Iloilo City"]) == "provincial_city"
    assert geography.area_type(["Luzon outside NCR"]) == "provincial"
    assert geography.area_type(["Rural Mindanao"]) == "rural"
    assert geography.area_type(["Nationwide"]) == "nationwide"
    assert geography.where_phrase(["NCR"]) == "in Metro Manila"
    assert geography.contrast_note(["NCR"], ["Visayas"]) == "Metro Manila compared with provincial areas"


# 6. Two trends in the same study ---------------------------------------------------------------
def test_opposite_directions_inside_one_study_are_two_trends():
    young = FindingCtx("y", "T", "app_trend:satisfaction", "high", "quant", 18, 34, ("Nationwide",), "Users",
                       date(2026, 6, 30), "quant", (("age_band", "18-34"),))
    old = FindingCtx("o", "T", "app_trend:satisfaction", "low", "quant", 50, 65, ("Nationwide",), "Users",
                     date(2026, 6, 30), "quant", (("age_band", "50-65"),))
    (group,) = analyze([young, old])
    assert group.kind == "within_study" and group.differs_by == ["age"]
    w1 = FindingCtx("w1", "T", "x:y", "high", "quant", None, None, (), None, None, "quant", (("segment", "Wave 1"),))
    w2 = FindingCtx("w2", "T", "x:y", "low", "quant", None, None, (), None, None, "quant", (("segment", "Wave 2"),))
    assert analyze([w1, w2])[0].differs_by == ["period"]


def test_tracker_brief_explains_two_trends_with_the_respondents(client):
    brief = ask(client, "carla", APP_QUESTION)
    (pattern,) = brief["study_patterns"]
    assert pattern["topic"] == "app_trend:satisfaction" and pattern["differs_by"] == ["age"]
    text = pattern["explanation"]
    assert "two trends in the same study, SI-2026-025" in text
    assert "mobile banking app users aged 18–65 nationwide" in text
    assert "improving among mobile banking app users aged 18–34 (72%)".lower() in text.lower()
    assert brief["unresolved_conflicts"] == [] and brief["escalation"] is None
    assert not BANNED.search(brief_text(brief) + text)


def test_regional_split_names_metro_manila_versus_provincial(client):
    brief = ask(client, "ana", ATM_QUESTION)
    (pattern,) = brief["study_patterns"]
    assert "pain point in Metro Manila (57%)" in pattern["explanation"]
    assert "Metro Manila compared with provincial areas" in pattern["explanation"]


# 8. Ask an analyst: a generated, specific escalation ---------------------------------------------
def test_escalation_draft_is_specific_and_post_accepts_chosen_gaps(client, db):
    brief = ask(client, "carla", "Do young professionals prefer cashback or travel rewards on credit cards?")
    headers = auth(client, "carla")
    draft = client.get(f"/api/briefs/{brief['id']}/escalation-draft", headers=headers).json()
    assert draft["question"] == brief["question"] and draft["study_codes"] == ["SI-2026-021", "SI-2026-027"]
    assert 1 <= len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", draft["found"])) <= 3
    assert draft["gaps"] and all({"id", "text", "ask", "checked"} <= set(g) for g in draft["gaps"])
    assert any(d["kind"] == "unresolved_conflict" for d in draft["differences"])
    assert "SI-2026-021 and SI-2026-027" in draft["suggested_question"]
    assert client.get(f"/api/briefs/{brief['id']}/escalation-draft", headers=auth(client, "ben")).status_code == 404

    chosen = [draft["gaps"][0]["text"]]
    body = {"brief_id": brief["id"], "note": draft["note"], "gaps": chosen, "suggested_question": draft["suggested_question"]}
    created = client.post("/api/escalations", headers=headers, json=body).json()
    again = client.post("/api/escalations", headers=headers, json=body).json()
    assert again["id"] == created["id"] and again["duplicate"] is True
    desk = client.get("/api/escalations", headers=auth(client, "ana")).json()
    mine = next(e for e in desk if e["id"] == created["id"])
    assert "Gaps to check:\n- " + chosen[0] in mine["note"] and "Question for the analyst:" in mine["note"]
    with db.as_service() as conn:
        details = conn.execute("select details from public.audit_log where entity_id = %s and action = 'escalation.created'",
                               [created["id"]]).fetchone()["details"]
    assert details["gaps"] == chosen


# 9. Persona ----------------------------------------------------------------------------------
def test_brief_is_prepared_for_the_reader_without_changing_what_they_see(client):
    carla = ask(client, "carla", GENZ_QUESTION, reader_role="Product manager")
    ben = ask(client, "ben", GENZ_QUESTION)
    assert carla["prepared_for"]["team"] == "Cards & Payments" and carla["prepared_for"]["role_label"] == "Product manager"
    assert "SI-2026-041" in carla["prepared_for"]["team_study_codes"]
    assert carla["prepared_for"]["note"].startswith("Prepared for Carla Mendoza, Cards & Payments (Product manager).")
    assert ben["prepared_for"]["team_study_codes"] == []
    assert set(carla["sources"]) == set(ben["sources"])          # framing only: same evidence


def test_team_owned_metrics_are_listed_first():
    other = replace(src("o", "O", metric="branch:long_queues", value=60, code="SI-O"), owner_team="Strategy & Insights")
    mine = src("m", "M", metric="card_dropoff:fees", value=30, code="SI-M")
    lead = src("l", "L", metric="card_dropoff:id_verification", value=70, code="SI-L")
    request = BriefRequest(question="What matters?", findings=[("F1", lead), ("F2", other), ("F3", mine)], groups=[],
                           chartable=[], computed_gaps=[],
                           reader=Reader("Carla", "Cards & Payments", "bu_user", "Business-unit user", ("card_dropoff:",)))
    breakdowns = [c for c in OfflineLLM().write_brief(request).claims if c.kind == "breakdown"]
    assert [c.evidence[0].finding_id for c in breakdowns] == ["F3", "F2"]


# 10. Audience modes -----------------------------------------------------------------------------
def test_every_brief_has_three_validated_audience_summaries(client, db):
    for who, question in (("ben", SME_QUESTION), ("carla", GENZ_QUESTION), ("ana", ATM_QUESTION)):
        brief = ask(client, who, question)
        assert set(brief["summaries"]) == {"executive", "analyst", "plain"}
        for summary in brief["summaries"].values():
            assert summary["finding_ids"] and set(summary["finding_ids"]) <= set(brief["sources"])
            assert not BANNED.search(summary["text"])
        assert brief["summaries"]["analyst"]["text"].startswith("Lead evidence:")


def test_summary_templates_pass_the_validators():
    a = src("a", "A", ages=(20, 40), code="SI-A")
    b = src("b", "B", value=11, direction="low", ages=(41, 60), regions=("Nationwide",), code="SI-B")
    sources = {"a": a, "b": b}
    groups = analyze([a.ctx(), b.ctx()])
    brief = EvidenceBrief(claims=[Claim(text="Fees drove 37% of drop-off (NCR, ages 20–40).", kind="headline",
                                        evidence=[Evidence(finding_id="a", stance="supports")])],
                          context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[])
    summaries = build_summaries(brief, sources, groups)
    assert [s.audience for s in summaries] == ["executive", "analyst", "plain"]
    for i, s in enumerate(summaries):
        assert validate_summary(i, s, sources) == []


def test_a_summary_with_a_made_up_number_is_replaced(make_client):
    def script(request, attempt):
        ref = next(r for r, s in request.findings if s.finding_type == "quant_stat")
        return EvidenceBrief(
            claims=[Claim(text="A figure.", kind="breakdown", evidence=[Evidence(finding_id=ref, stance="supports")])],
            context_notes=[], unresolved_conflicts=[], chart_requests=[], gaps=[],
            summaries=[AudienceSummary(audience="executive", text="Drop-off rose 73% since 1999.", finding_ids=[ref]),
                       AudienceSummary(audience="plain", text="Some people stop.", finding_ids=[ref])])

    client = make_client(llm=ScriptedLLM(script))
    brief = ask(client, "ben", SME_QUESTION)
    assert "73%" not in brief["summaries"]["executive"]["text"]
    assert brief["summaries"]["plain"]["text"] == "Some people stop."      # valid LLM summary kept


# 11. Coverage states --------------------------------------------------------------------------
def test_coverage_states():
    recent = src("r", "R", tier="A", end=date(2026, 3, 1))
    old = src("o", "O", tier="B", end=date(2022, 6, 30))
    qual = src("q", "Q", method="qual", tier="B", finding_type="qual_theme", value=None)
    assert coverage_state([recent], TODAY) == "covered"
    assert coverage_state([old], TODAY) == "covered_stale"
    assert coverage_state([qual], TODAY) == "partial"
    assert coverage_state([], TODAY) == "gap"


def test_coverage_check_names_genuinely_new_problems(client):
    objectives = ["Understand why SME owners abandon online loan applications",
                  "Measure how often SME owners renew loans digitally",
                  "Size the market for crop insurance among rice farmers"]
    check = client.post("/api/commissioning/coverage", headers=auth(client, "ben"),
                        json={"title": "SME lending", "objectives": objectives}).json()
    states = [o["coverage"] for o in check["result"]["objectives"]]
    assert states == ["covered", "gap", "gap"]          # drop-off studies do not cover renewals
    assert check["result"]["new_problems"] == objectives[1:]
    assert check["result"]["objectives"][1]["coverage_label"] == "New problem: not yet researched"
    scope = check["result"]["recommended_new_scope"]
    assert "New problems, not yet researched" in scope and "?." not in scope
