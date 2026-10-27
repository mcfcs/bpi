"""Runtime settings and the thresholds S&I can tune.

The tier, divergence, retrieval, coverage and chart thresholds below are proposed defaults that S&I
has not validated yet. They live here so they can change without touching the code that uses them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

# Robustness tiers. Computed in code (app/tiers.py), never by the LLM.
TIER_CONFIG: dict = {
    "method_points": {"quant": 3, "mixed": 2, "qual": 1},
    "sample_bands": [(1000, 2), (300, 1)],   # n >= 1000: +2, n >= 300: +1, else 0 (qual always 0)
    "recency_months": [(18, 1), (36, 0)],    # <=18 months: +1, <=36: 0, older: -1
    "tiers": {"A": 5, "B": 3},               # score >= 5 -> A, >= 3 -> B, else C
}

RETRIEVAL_CONFIG: dict = {
    "match_count": 24,
    "min_similarity": 0.12,     # absolute floor on cosine similarity to the question
    "relative_floor": 0.5,      # and at least this share of the best match's similarity
    "rrf_k": 50,
    # Rerank multiplier on the fused hybrid score. Lower tiers rank lower but are never excluded:
    # qualitative studies still supply the "why".
    "tier_boost": {"A": 1.3, "B": 1.15, "C": 1.0},
    "verbatims_per_theme": 3,
    "restricted_min_similarity": 0.2,
    "restricted_limit": 5,
}

# "Before you commission". Stricter than question answering: a finding counts toward an objective only
# if it is a strong match (absolute floor) and close to the best match (relative floor). Calibrated
# for the local hashing embedder; recalibrate when a hosted embedding model is used.
COVERAGE_CONFIG: dict = {"min_similarity": 0.45, "relative_floor": 0.8, "max_findings": 6}

# Divergence classification (app/divergence.py). The proposal compared ranges for any overlap at
# all, which would call 20-40 vs 30-60 the same population; these minimum-overlap ratios
# (intersection over union) are what make that example a context difference.
DIVERGENCE_CONFIG: dict = {
    "age_overlap_min": 0.5,
    "region_overlap_min": 0.5,
    "period_months": 18,
}

# Used only when a reviewed finding has no direction recorded: (high at or above, low at or below).
# For ranks a smaller number is more prominent.
DIRECTION_FALLBACK: dict = {"%": (30.0, 15.0), "rank": (3.0, 5.0)}

CHART_CONFIG: dict = {"min_points": 2, "max_charts": 3, "units": ("%", "score")}

# Display labels for metric keys. Whether S&I supplies a fixed metric vocabulary is open; unknown
# keys fall back to a readable form of the key.
METRIC_LABELS: dict[str, str] = {
    "barrier:documents": "Documentation requirements",
    "barrier:approval_time": "Unclear approval time",
    "barrier:fees": "Fees",
    "barrier:collateral": "Collateral requirements",
    "barrier:app_errors": "App errors",
    "support:contact_person": "Wants a named contact person",
    "channel_pref:online_renewal": "Prefers online renewal",
    "reward_pref:cashback": "Prefers cashback rewards",
    "reward_pref:travel": "Prefers travel rewards",
    "qr:payment_confirmation": "Confirming QR payments",
    "qr:cash_habit": "Cash habits",
}

METRIC_CHART_TITLES: dict[str, str] = {
    "barrier:": "Cited {label_lower} as a reason for dropping off",
    "reward_pref:": "{label}",
    "channel_pref:": "{label}",
}


def metric_label(metric_key: str | None) -> str:
    if not metric_key:
        return "Other"
    if metric_key in METRIC_LABELS:
        return METRIC_LABELS[metric_key]
    item = metric_key.split(":", 1)[-1]
    return item.replace("_", " ").capitalize()


def chart_title(metric_key: str) -> str:
    label = metric_label(metric_key)
    for prefix, template in METRIC_CHART_TITLES.items():
        if metric_key.startswith(prefix):
            return template.format(label=label, label_lower=label[:1].lower() + label[1:])
    return label


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into the environment without overriding values that are already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


DEV_JWT_SECRET = "local-development-secret-not-for-production-0000"


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    demo_mode: bool
    llm_provider: str          # "anthropic" or "offline"
    llm_model: str
    llm_effort: str
    commissioning_adapter: str  # "noop" or "webhook"
    commissioning_webhook_url: str | None
    commissioning_webhook_headers: dict[str, str]
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    _load_env_file(BACKEND_DIR / ".env.local")
    _load_env_file(BACKEND_DIR / ".env")
    env = os.environ
    demo_mode = env.get("DEMO_MODE", "false").lower() == "true"
    jwt_secret = env.get("SUPABASE_JWT_SECRET") or (DEV_JWT_SECRET if demo_mode else "")
    if not jwt_secret:
        raise RuntimeError("Set SUPABASE_JWT_SECRET (or DEMO_MODE=true for local development).")
    has_claude_credentials = bool(env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN"))
    return Settings(
        database_url=env.get("DATABASE_URL", ""),
        jwt_secret=jwt_secret,
        demo_mode=demo_mode,
        llm_provider=env.get("LLM_PROVIDER", "anthropic" if has_claude_credentials else "offline"),
        llm_model=env.get("LLM_MODEL", "claude-opus-5-5"),
        llm_effort=env.get("LLM_EFFORT", "high"),
        commissioning_adapter=env.get("COMMISSIONING_ADAPTER", "noop"),
        commissioning_webhook_url=env.get("COMMISSIONING_WEBHOOK_URL") or None,
        commissioning_webhook_headers=json.loads(env.get("COMMISSIONING_WEBHOOK_HEADERS", "{}")),
        cors_origins=tuple(
            o.strip() for o in env.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ),
    )
