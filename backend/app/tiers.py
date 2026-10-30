"""Robustness tiers: how much weight a study's findings carry.

Computed in code; never by the LLM. Quantitative and mixed studies score method, sample size and
recency. Qualitative studies are tiered by recency alone (QUAL_TIER_CONFIG): S&I weigh group
discussions and interviews by how recent they are, and a larger group never makes them
representative. The qualitative scale tops out below a robust survey, so n=1,200 > 6 FGDs.

The effective tier is coalesce(tier_override, robustness_tier); analysts set overrides at review
with a stated reason.
"""

from __future__ import annotations

from datetime import date

from .config import QUAL_TIER_CONFIG, TIER_CONFIG

TIER_BASIS = {
    "quant": "Method, sample size and recency",
    "mixed": "Method, sample size and recency",
    "qual": "Recency only (qualitative: group size does not raise the tier)",
}


def qual_tier(age_months: int) -> str:
    cfg = QUAL_TIER_CONFIG
    return next((tier for months, tier in cfg["recency_tiers"] if age_months <= months), cfg["older"])


def months_between(start: date, end: date) -> int:
    """Whole calendar months from start to end; negative when end is before start."""
    if end < start:
        return -months_between(end, start)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def tier_breakdown(method_type: str, sample_size: int | None, fieldwork_end: date, today: date) -> dict:
    """The points behind a tier, for the review screen and citation tooltips."""
    cfg = TIER_CONFIG
    method_points = cfg["method_points"][method_type]
    sample_points = 0
    if method_type != "qual" and sample_size:
        sample_points = next((pts for n, pts in cfg["sample_bands"] if sample_size >= n), 0)
    age_months = months_between(fieldwork_end, today)
    recency_points = next((pts for m, pts in cfg["recency_months"] if age_months <= m), -1)
    score = method_points + sample_points + recency_points
    if method_type == "qual":
        tier = qual_tier(age_months)
    else:
        tier = "A" if score >= cfg["tiers"]["A"] else "B" if score >= cfg["tiers"]["B"] else "C"
    return {
        "method_points": method_points,
        "sample_points": sample_points,
        "recency_points": recency_points,
        "age_months": age_months,
        "score": score,
        "tier": tier,
        "basis": "recency" if method_type == "qual" else "method_sample_recency",
        "basis_label": TIER_BASIS[method_type],
    }


def compute_tier(method_type: str, sample_size: int | None, fieldwork_end: date, today: date) -> str:
    return tier_breakdown(method_type, sample_size, fieldwork_end, today)["tier"]


def compute_tier_or_none(
    method_type: str | None, sample_size: int | None, fieldwork_end: date | None, today: date
) -> str | None:
    """The tier, or None until the analyst has filled in method and fieldwork end."""
    if method_type not in TIER_CONFIG["method_points"] or fieldwork_end is None:
        return None
    return compute_tier(method_type, sample_size, fieldwork_end, today)


def effective_tier(robustness_tier: str | None, tier_override: str | None) -> str | None:
    return tier_override or robustness_tier
