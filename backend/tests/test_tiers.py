from datetime import date

import pytest

from app import tiers
from app.tiers import compute_tier, compute_tier_or_none, months_between, tier_breakdown

TODAY = date(2026, 10, 27)


@pytest.mark.parametrize("start, end, expected", [
    (date(2026, 3, 20), date(2026, 10, 27), 7),
    (date(2026, 3, 28), date(2026, 10, 27), 6),     # not a full seventh month yet
    (date(2025, 2, 14), date(2026, 10, 27), 20),
    (date(2026, 10, 27), date(2026, 3, 20), -7),    # signed
    (date(2026, 1, 1), date(2026, 1, 31), 0),
])
def test_months_between(start, end, expected):
    assert months_between(start, end) == expected


def test_seeded_studies_get_the_expected_tiers():
    # Study A: quant, n=1,200, fieldwork 2026 -> 3 + 2 + 1
    assert compute_tier("quant", 1200, date(2026, 3, 20), TODAY) == "A"
    # Study B: quant, n=800, fieldwork ended Feb 2025 (20 months) -> 3 + 1 + 0
    assert compute_tier("quant", 800, date(2025, 2, 14), TODAY) == "B"
    # Study C: qual, 42 participants -> 1 + 0 + 1; qual never earns sample points
    assert compute_tier("qual", 42, date(2025, 9, 12), TODAY) == "C"
    assert compute_tier("qual", 5000, date(2026, 9, 1), TODAY) == "C"


def test_recency_lowers_an_old_studys_tier():
    recent = compute_tier("quant", 1050, date(2026, 6, 30), TODAY)
    old = compute_tier("quant", 1050, date(2022, 6, 30), TODAY)
    assert (recent, old) == ("A", "B")
    assert tier_breakdown("quant", 1050, date(2022, 6, 30), TODAY)["recency_points"] == -1


def test_thresholds_come_from_config(monkeypatch):
    monkeypatch.setitem(tiers.TIER_CONFIG, "tiers", {"A": 7, "B": 3})
    assert compute_tier("quant", 1200, date(2026, 3, 20), TODAY) == "B"


def test_tier_is_none_until_method_and_fieldwork_are_known():
    assert compute_tier_or_none(None, 500, date(2026, 1, 1), TODAY) is None
    assert compute_tier_or_none("quant", 500, None, TODAY) is None
    assert compute_tier_or_none("quant", 500, date(2026, 1, 1), TODAY) == "A"


def test_effective_tier_prefers_the_override():
    assert tiers.effective_tier("B", None) == "B"
    assert tiers.effective_tier("B", "A") == "A"
