import re
from datetime import date
from decimal import Decimal

import pytest

from app.confidence import compute_confidence
from app.divergence import DivergenceGroup
from app.retrieval import Source
from app.schemas import Claim, ContextNote, Evidence, EvidenceBrief
from app.validators import (
    QUAL_FORBIDDEN,
    finalize,
    has_hedge,
    validate_brief,
)


def source(fid, method="quant", tier="A", finding_type="quant_stat", **kw) -> Source:
    defaults = dict(
        finding_id=fid, study_id=f"study-{fid}", text=f"finding {fid}", theme="loan_application_dropoff",
        finding_type=finding_type, metric_key="barrier:fees", value=Decimal("38") if finding_type == "quant_stat" else None,
        unit="%" if finding_type == "quant_stat" else None, base_n=1200, subgroup=None, direction="high",
        study_code=f"SI-{fid}", study_title=f"Study {fid}", method_type=method, sample_size=1200,
        fieldwork_end=date(2026, 3, 20), population={"age_min": 20, "age_max": 40, "regions": ["NCR"], "segment": "SME owners"},
        effective_tier=tier, robustness_tier=tier, tier_override=None, owner_team="S&I", access_level="open",
    )
    defaults.update(kw)
    return Source(**defaults)


SOURCES = {
    "quantA": source("quantA"),
    "quantB": source("quantB", tier="B"),
    "quantC": source("quantC", tier="C"),
    "qual": source("qual", method="qual", tier="C", finding_type="qual_theme", direction="low"),
    "verb": source("verb", method="qual", tier="C", finding_type="verbatim", direction=None),
}


def brief(*claims, context_notes=(), unresolved=(), charts=(), gaps=()) -> EvidenceBrief:
    return EvidenceBrief(claims=list(claims), context_notes=list(context_notes), unresolved_conflicts=list(unresolved),
                         chart_requests=list(charts), gaps=list(gaps))


def claim(text, kind="breakdown", ids=("quantA",), verbatims=()) -> Claim:
    return Claim(text=text, kind=kind, evidence=[Evidence(finding_id=i, stance="supports") for i in ids],
                 verbatim_ids=list(verbatims))


def codes(issues):
    return {i.code for i in issues}


@pytest.mark.parametrize("text", [
    "Most participants disliked fees.", "The majority wanted help.", "All groups agreed.",
    "This proves fees matter.", "45% of participants", "4.5 % said so", "Forty percent agreed.",
])
def test_incidence_language_is_caught(text):
    assert QUAL_FORBIDDEN.search(text)


@pytest.mark.parametrize("text", ["Almost every group mentioned it.", "Small shops felt this.", "Fees were raised."])
def test_ordinary_words_are_not_caught(text):
    assert not QUAL_FORBIDDEN.search(text)


def test_proposed_pattern_missed_percentages():
    # The pattern as proposed: the trailing \b after "%" cannot match before a space or end of text.
    proposed = re.compile(r"\b(most|majority|all|proves?|\d+(\.\d+)?\s?%|percent)\b", re.IGNORECASE)
    assert not proposed.search("45% of participants")
    assert QUAL_FORBIDDEN.search("45% of participants")


def test_hedges():
    assert has_hedge("In the Cebu and Iloilo groups, participants raised fees.")
    assert has_hedge("Participants described wanting a contact person.")
    assert has_hedge("This suggests fees matter less.")
    assert has_hedge("Indicatively, fees matter less.")
    assert not has_hedge("Fees matter less to owners.")


def test_qual_only_claim_needs_hedge_and_no_incidence_language():
    issues = validate_brief(brief(claim("Most owners want a contact person.", "qualitative_insight", ["qual"])), SOURCES, [])
    assert {"qual_incidence_language", "qual_missing_hedge"} <= codes(issues)
    ok = validate_brief(brief(claim("Participants described wanting a contact person.", "qualitative_insight", ["qual"], ["verb"])), SOURCES, [])
    assert ok == []


def test_claims_citing_quant_are_not_held_to_qual_rules():
    assert validate_brief(brief(claim("Most owners cited fees (38%).", "breakdown", ["quantA", "qual"])), SOURCES, []) == []


def test_headline_needs_tier_a_or_b_quant():
    assert "headline_without_ab_quant" in codes(validate_brief(brief(claim("x", "headline", ["quantC"])), SOURCES, []))
    assert "headline_without_ab_quant" in codes(validate_brief(
        brief(claim("Participants described x.", "headline", ["qual"])), SOURCES, []))
    assert validate_brief(brief(claim("x", "headline", ["quantB"])), SOURCES, []) == []


def test_citation_ids_must_be_in_the_retrieved_set():
    assert "unknown_finding_id" in codes(validate_brief(brief(claim("x", ids=["not-retrieved"])), SOURCES, []))
    assert "unknown_finding_id" in codes(validate_brief(
        brief(claim("Participants described x.", "qualitative_insight", ["qual"], ["F99"])), SOURCES, []))


def test_verbatims_only_on_qualitative_insights_and_only_verbatims():
    issues = validate_brief(brief(claim("x", "breakdown", ["quantA"], ["verb"])), SOURCES, [])
    assert "verbatim_outside_qual" in codes(issues)
    issues = validate_brief(brief(claim("Participants described x.", "qualitative_insight", ["qual"], ["quantA"])), SOURCES, [])
    assert "not_a_verbatim" in codes(issues)


def test_conflict_wording_is_reserved_for_unresolved_conflicts():
    assert "conflict_wording" in codes(validate_brief(brief(claim("Studies conflict on fees.")), SOURCES, []))


GROUP = DivergenceGroup("context_difference", "barrier:fees", ["quantA", "qual"], ["region", "method"])


def test_divergence_notes_take_their_facts_from_the_classifier():
    llm_note = ContextNote(topic="barrier:fees", finding_ids=["quantA"], differs_by=["age"], explanation="Who was asked differs.")
    draft = brief(claim("x"), context_notes=[llm_note])
    final, _ = finalize(draft, validate_brief(draft, SOURCES, [GROUP]), SOURCES, [GROUP], [])
    (note,) = final.context_notes
    assert note.differs_by == ["region", "method"]
    assert note.finding_ids == ["quantA", "qual"]
    assert note.explanation == "Who was asked differs."


def test_a_note_calling_a_context_difference_a_conflict_is_rewritten():
    llm_note = ContextNote(topic="barrier:fees", finding_ids=["quantA", "qual"], differs_by=["region"], explanation="These studies conflict.")
    draft = brief(claim("x"), context_notes=[llm_note])
    issues = validate_brief(draft, SOURCES, [GROUP])
    assert "conflict_wording" in codes(issues)
    final, _ = finalize(draft, issues, SOURCES, [GROUP], [])
    assert "conflict" not in final.context_notes[0].explanation.lower()


def test_missing_and_invented_divergence_notes():
    assert "missing_divergence_note" in codes(validate_brief(brief(claim("x")), SOURCES, [GROUP]))
    invented = ContextNote(topic="barrier:documents", finding_ids=["quantA"], differs_by=["age"], explanation="x")
    assert "unknown_divergence" in codes(validate_brief(brief(claim("x"), context_notes=[invented]), SOURCES, [GROUP]))


def test_finalize_drops_failing_claims_and_keeps_one_headline():
    draft = brief(
        claim("Headline one.", "headline", ["quantA"]),
        claim("Headline two.", "headline", ["quantB"]),
        claim("Most participants agreed.", "qualitative_insight", ["qual"]),
        charts=["barrier:fees", "made:up"],
    )
    final, dropped = finalize(draft, validate_brief(draft, SOURCES, []), SOURCES, [], ["barrier:fees"])
    assert [c.kind for c in final.claims] == ["headline", "breakdown"]
    assert dropped[0]["text"] == "Most participants agreed."
    assert final.chart_requests == ["barrier:fees"]


@pytest.mark.parametrize("ids, notes, unresolved, expected", [
    (["quantA"], [], [], "high"),
    (["quantA"], ["ctx"], [], "high"),                  # explained context differences keep High
    (["quantB"], [], [], "medium"),
    (["quantC"], [], [], "low"),                        # Tier C at best: treated conservatively
    (["qual"], [], [], "low"),
    (["quantA"], [], ["conflict"], "low"),
])
def test_confidence_rules(ids, notes, unresolved, expected):
    note = ContextNote(topic="barrier:fees", finding_ids=ids, differs_by=["age"], explanation="x")
    b = brief(claim("x", "breakdown", ids), context_notes=[note] if notes else [], unresolved=[note] if unresolved else [])
    assert compute_confidence(b, SOURCES)["level"] == expected


def test_confidence_with_no_claims_is_low():
    assert compute_confidence(brief(), SOURCES)["level"] == "low"
