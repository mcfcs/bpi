"""How the tier rules weigh the whole evidence base: the synthetic corpus, the synthetic report PDFs
in the review queue and the public research studies.

These tests pin the current behaviour of app/tiers.py (owned elsewhere) on realistic inputs. The
ones marked "S&I to confirm" document outcomes that may not match how S&I weighs evidence; they are
reported for discussion, not changed here. `python -m eval.evidence_weighing` prints the full table.
"""

from __future__ import annotations

from datetime import date

from eval.evidence_weighing import evidence_table
from tests.conftest import TODAY


def _by_code() -> dict[str, dict]:
    return {row["code"]: row for row in evidence_table(TODAY)}


def test_large_recent_surveys_are_tier_a():
    rows = _by_code()
    assert rows["SI-2026-014"]["tier"] == "A"                                   # n=1,200, 2026
    assert rows["PUB-BSP-CES25Q4"]["tier"] == "A"                               # n=5,489 households, Oct 2025
    assert rows["Nationwide Digital Banking Adoption Survey 2026"]["tier"] == "A"  # n=2,400, 2026


def test_small_old_survey_is_tier_c():
    assert _by_code()["Branch SME Service Survey 2021"]["tier"] == "C"          # n=180, fieldwork 2021


def test_old_large_surveys_drop_to_tier_b():
    rows = _by_code()
    assert rows["PUB-BSP-FIS21"]["tier"] == "B"      # nationally representative, but fieldwork early 2022
    assert rows["PUB-ADB-SME20"]["tier"] == "B"      # n=2,487, fieldwork 2019
    assert rows["SI-2022-007"]["tier"] == "B"


def test_mixed_method_with_mid_sized_survey_is_tier_b():
    assert _by_code()["Credit Card Activation Mixed-Method Study 2026"]["tier"] == "B"


def test_qualitative_studies_are_tiered_by_recency():
    """Consultation 2: for qualitative work S&I look at recency, not sample size. Recent focus groups
    (within QUAL_TIER_CONFIG's 12 months) are B, older ones C, so this year's groups and a 2013 case
    study no longer carry the same label. Qualitative never reaches A. (Earlier this test pinned
    "qualitative is always C" as a question for S&I; the consultation answered it.)"""
    rows = _by_code()
    recent, old = rows["SI-2026-033"], rows["PUB-CGAP-G2P13"]   # fieldwork May 2026 vs 2013
    assert recent["tier"] == "B"
    assert old["tier"] == "C"
    assert all(r["tier"] in ("B", "C") for r in rows.values() if r["method_type"] == "qual")


def test_sample_size_bands_ignore_design_and_scale():
    """S&I to confirm: n=640 (an online pulse) and n=5,489 (a national probability sample) are both A
    when recent, because every n >= 1,000 earns the same points and n=300-999 is one point less."""
    rows = _by_code()
    assert rows["SI-2026-021"]["tier"] == rows["PUB-BSP-CES25Q4"]["tier"] == "A"


def test_mixed_studies_lose_a_method_point_on_their_survey_findings():
    """S&I to confirm: the tier is per study, so the BSP survey findings in a 'mixed' report get
    mixed (2) rather than quant (3) method points, while its qualitative findings get the same tier
    as the survey numbers."""
    row = _by_code()["PUB-BSP-FIS21"]
    assert row["method_type"] == "mixed" and row["breakdown"]["method_points"] == 2


def test_tiers_age_out_over_time():
    later = {row["code"]: row for row in evidence_table(date(2029, 6, 1))}   # 3+ years on: recency -1
    assert later["SI-2026-014"]["tier"] == "B" and later["PUB-BSP-CES25Q4"]["tier"] == "B"
