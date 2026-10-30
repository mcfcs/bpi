from datetime import date

from app.divergence import (
    FindingCtx,
    analyze,
    classify_divergence,
    diverges,
    parse_age_band,
    ranges_overlap,
    regions_overlap,
)


def ctx(fid, study, direction, ages=(None, None), regions=("NCR",), segment="SME owners",
        end=date(2026, 3, 20), method="quant", topic="barrier:fees"):
    return FindingCtx(fid, study, topic, direction, method, ages[0], ages[1], tuple(regions), segment, end)


STUDY_A = ctx("a", "A", "high", (20, 40), ["NCR"])
STUDY_B = ctx("b", "B", "low", (30, 60), ["Nationwide"], end=date(2025, 2, 14))
STUDY_C = ctx("c", "C", "low", (28, 58), ["Cebu", "Iloilo"], end=date(2025, 9, 12), method="qual")
CARDS_F = ctx("f", "F", "high", (25, 35), ["NCR"], "Young professionals", date(2026, 2, 27), topic="reward_pref:cashback")
CARDS_G = ctx("g", "G", "low", (25, 35), ["NCR"], "Young professionals", date(2026, 4, 30), topic="reward_pref:cashback")


def test_partially_overlapping_age_bands_are_different_groups():
    # 20-40 and 30-60 share only 30-40; a bare overlap test would call them the same people.
    assert not ranges_overlap((20, 40), (30, 60))
    assert ranges_overlap((25, 35), (25, 35))
    assert ranges_overlap((25, 55), (30, 60))
    assert ranges_overlap((None, None), (30, 60))  # unknown never invents a difference


def test_regions_are_compared_after_expansion():
    assert not regions_overlap(["NCR"], ["Nationwide"])
    assert not regions_overlap(["Cebu", "Iloilo"], ["NCR"])
    assert regions_overlap(["Cebu"], ["Cebu City"])
    assert regions_overlap(["Nationwide"], ["Philippines"])


def test_fees_example_is_a_context_difference_by_age_and_region():
    kind, differs_by = classify_divergence(STUDY_A, STUDY_B)
    assert kind == "context_difference"
    assert differs_by == ["age", "region"]


def test_qual_versus_quant_differs_by_method_and_region():
    kind, differs_by = classify_divergence(STUDY_A, STUDY_C)
    assert kind == "context_difference"
    assert {"region", "method"} <= set(differs_by)


def test_same_population_and_period_is_an_unresolved_conflict():
    assert classify_divergence(CARDS_F, CARDS_G) == ("unresolved_conflict", [])


def test_period_counts_only_beyond_18_months():
    eighteen_months = ctx("x", "X", "low", (20, 40), ["NCR"], end=date(2027, 9, 20))
    nineteen_months = ctx("y", "Y", "low", (20, 40), ["NCR"], end=date(2027, 11, 1))
    assert classify_divergence(STUDY_A, eighteen_months) == ("unresolved_conflict", [])
    assert classify_divergence(STUDY_A, nineteen_months) == ("context_difference", ["period"])


def test_divergence_needs_opposite_directions_on_the_same_topic_from_different_studies():
    assert diverges(STUDY_A, STUDY_B)
    assert not diverges(STUDY_A, ctx("a2", "A", "low", (20, 29)))          # same study: a breakdown
    assert not diverges(STUDY_A, ctx("d", "D", "high", (25, 55), ["Nationwide"]))
    assert not diverges(STUDY_A, ctx("n", "N", "neutral"))
    assert not diverges(STUDY_A, ctx("o", "O", "low", topic="barrier:documents"))


def test_analyze_merges_context_pairs_per_topic_and_keeps_conflicts_separate():
    groups = analyze([STUDY_A, STUDY_B, STUDY_C, CARDS_F, CARDS_G])
    by_kind = {(g.kind, g.topic): g for g in groups}
    fees = by_kind[("context_difference", "barrier:fees")]
    # The qualitative finding (c) is never paired with a survey figure, so only a and b remain.
    assert set(fees.finding_ids) == {"a", "b"}
    assert fees.differs_by == ["age", "region"]
    conflict = by_kind[("unresolved_conflict", "reward_pref:cashback")]
    assert conflict.finding_ids == ["f", "g"] and conflict.differs_by == []


def test_parse_age_band():
    assert parse_age_band("20-29") == (20, 29)
    assert parse_age_band("20–40") == (20, 40)
    assert parse_age_band("60+") == (60, 99)
    assert parse_age_band("Bakery owner") == (None, None)
