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
    # Facet rerank (topicality.facet_multiplier): a finding whose product (loan, card, ...) or topic
    # (drop-off, rewards, ...) matches one the question names gets 1 + this per matching facet, on
    # its score and on the similarity the relative floor compares. A facet the question doesn't name
    # counts for nothing, so generic questions are unaffected. The absolute floor stays on raw cosine,
    # so a facet match never lets in a finding below it (off-topic questions stay empty). Chosen mid-plateau
    # (0.25-0.5) on the tune half of eval/questions.json; proposed default, not validated by S&I.
    "facet_boost": {"product": 0.4, "topic": 0.4},
    "verbatims_per_theme": 3,
    "restricted_min_similarity": 0.2,
    "restricted_limit": 5,
    # A restricted-study hint for a question with a concept beyond its product must share a concept
    # word with the study's findings (checked in the database) unless its similarity reaches this.
    # 2.0: never bypassed (lexical embedder). Proposed default, not validated by S&I.
    "restricted_bypass_similarity": 2.0,
}

# "Before you commission". Stricter than question answering: a finding counts toward an objective only
# if it is a strong match (absolute floor) and close to the best match (relative floor). Calibrated
# for the local hashing embedder; recalibrate when a hosted embedding model is used.
COVERAGE_CONFIG: dict = {"min_similarity": 0.45, "relative_floor": 0.8, "max_findings": 6}

# Similarity floors per embedder, layered over RETRIEVAL_CONFIG / COVERAGE_CONFIG (which were
# calibrated for the hashing embedder). Neural models score unrelated text far higher than a
# hashing embedder does, so they need their own floors. Calibrated with `python -m eval.retrieval_eval`
# on the synthetic corpus; recalibrate on real studies.
EMBEDDER_FLOORS: dict[str, dict[str, dict]] = {
    "hashing": {},
    # Sweep (eval/retrieval_eval.py --sweep): every floor from 0.36 to 0.40 kept off-topic questions
    # at zero hits (their best match peaked at 0.355) with micro F1 0.86-0.87; 0.38 is the middle.
    # Restricted-study hints and coverage are stricter; coverage is not separately evaluated yet.
    "fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {
        # restricted_bypass_similarity matches the coverage topicality bypass (TOPICALITY_CONFIG).
        "retrieval": {"min_similarity": 0.38, "relative_floor": 0.7, "restricted_min_similarity": 0.42,
                      "restricted_bypass_similarity": 0.7},
        "coverage": {"min_similarity": 0.5, "relative_floor": 0.8},
    },
}


def retrieval_config(embedder_name: str = "hashing") -> dict:
    return {**RETRIEVAL_CONFIG, **EMBEDDER_FLOORS.get(embedder_name, {}).get("retrieval", {})}


def coverage_config(embedder_name: str = "hashing") -> dict:
    return {**COVERAGE_CONFIG, **EMBEDDER_FLOORS.get(embedder_name, {}).get("coverage", {})}


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
            first = label.split()[0] if label.split() else ""
            lower = label if first[:2].isupper() else label[:1].lower() + label[1:]   # keep "ID ..."
            return template.format(label=label, label_lower=lower)
    return label


# ---------------------------------------------------------------------------
# Study documents (app/documents.py). Proposed defaults, not validated by S&I.
# ---------------------------------------------------------------------------
DOCUMENT_CONFIG: dict = {
    "max_upload_bytes": 25_000_000,  # PDF uploads larger than this are refused
    "min_text_chars": 200,           # less extractable text than this: treat as scanned (needs OCR first)
    # A finding is pinned to a page only when this share of its word trigrams appears on that page;
    # below it the page is left empty for the analyst to fill in at review rather than guessed.
    "min_page_match": 0.6,
    "download_link_seconds": 120,    # lifetime of a signed "open the report at page N" link
}

# Where public and synthetic report material lives. Public PDFs are downloaded by
# backend/scripts/fetch_public_reports.py and are git-ignored; never commit third-party PDFs.
PUBLIC_DATA_DIR = REPO_DIR / "data" / "public"
SYNTHETIC_DATA_DIR = REPO_DIR / "data" / "synthetic"


# ---------------------------------------------------------------------------
# Brief rules from the second S&I consultation (segment statements, quant first, qualitative
# recency, geography, audience modes, persona framing, coverage states). Proposed defaults that S&I
# has not validated yet.
# ---------------------------------------------------------------------------

# Qualitative studies are tiered by recency alone: S&I weigh qualitative evidence by how recent it
# is, not by how many people took part. The first band whose month limit the fieldwork age fits
# wins; older studies get "older". Capped at B so a group discussion never outranks a robust survey
# (n=1,200 survey > 6 FGDs). Qualitative tiers never raise confidence or allow a headline.
QUAL_TIER_CONFIG: dict = {"recency_tiers": [(12, "B")], "older": "C"}

# Coverage check states (commissioning.py): Tier A/B quant evidence whose newest fieldwork is older
# than this is "covered_stale" rather than "covered".
COVERAGE_STATE_CONFIG: dict = {"stale_months": 24}

METRIC_LABELS.update({
    "card_dropoff:id_verification": "ID verification",
    "card_dropoff:fees": "Fees",
    "card_dropoff:approval_wait": "Waiting for approval",
    "card_dropoff:otp_delay": "One-time PIN delays",
    "card_dropoff:app_errors": "App errors",
    "app_trend:satisfaction": "Satisfaction with the mobile app",
    "atm:long_queues": "Long ATM queues",
    "atm:distance": "Distance to the nearest ATM",
})
METRIC_CHART_TITLES.update({
    "card_dropoff:": "Cited {label_lower} as a reason for not finishing a card application",
    "app_trend:": "{label} (latest wave)",
    "atm:": "Named {label_lower} as a problem",
})

# How a segment statement describes a metric when it is prominent (high) or not (low), by key
# prefix. Used for "Fees: a driver of drop-off among ..., but not among ...".
METRIC_STANCE_PHRASES: dict[str, tuple[str, str]] = {
    "barrier:": ("a reason for dropping off", "not a main reason for dropping off"),
    "card_dropoff:": ("a driver of drop-off", "not a driver of drop-off"),
    "reward_pref:": ("the preferred reward", "not the preferred reward"),
    "app_trend:": ("improving", "declining"),
    "atm:": ("a pain point", "not a main pain point"),
}
DEFAULT_STANCE_PHRASES = ("prominent", "not prominent")


def stance_phrases(metric_key: str | None) -> tuple[str, str]:
    for prefix, phrases in METRIC_STANCE_PHRASES.items():
        if metric_key and metric_key.startswith(prefix):
            return phrases
    return DEFAULT_STANCE_PHRASES


# Persona framing: metric families each team owns. A brief lists these first for that team; it
# never changes what the reader may see (RLS decides that). Unknown teams get no reordering.
TEAM_METRIC_FOCUS: dict[str, tuple[str, ...]] = {
    "Cards & Payments": ("card_dropoff:", "reward_pref:", "qr:"),
    "SME Banking": ("barrier:", "support:", "channel_pref:"),
    "Digital Channels": ("app_trend:",),
}
# Topicality (app/topicality.py): whether retrieved findings share the question's own concept, not
# just generic words like "SME" or "loan". With the lexical hashing embedder, off-topic findings are
# dropped from briefs; with a semantic embedder lexical overlap misses true paraphrases, so it only
# caps confidence. Coverage checks drop off-topic findings unless their similarity reaches the bypass.
TOPICALITY_CONFIG: dict[str, dict] = {
    "hashing": {"filter_off_topic": True, "coverage_bypass_similarity": 2.0},   # never bypassed
    "default": {"filter_off_topic": False, "coverage_bypass_similarity": 0.7},
}


def topicality_config(embedder_name: str = "hashing") -> dict:
    return TOPICALITY_CONFIG.get(embedder_name, TOPICALITY_CONFIG["default"])


# Product and topic facets for the retrieval rerank (RETRIEVAL_CONFIG["facet_boost"]). SME loan and
# credit card applications share most of their vocabulary (application, drop off, fees, ID, approval),
# so a loan question pulled card studies and a card drop-off question pulled card-reward studies.
# Facets say which product and which topic a finding is about, so findings that match the question on
# both rank and survive the relative floor ahead of findings that only share words.
#
# A finding's facets come from its metric family (METRIC_FACETS); findings without a known family are
# read with the same lexicon as questions (study title, theme and text). Patterns are regular
# expressions matched case-insensitively on word boundaries. Proposed vocabulary, not validated by
# S&I; extend it when a new product or metric family is added.
FACET_LEXICON: dict[str, dict[str, tuple[str, ...]]] = {
    "product": {
        "loan": (r"loans?", r"lending", r"lend(?:er|ers)?", r"borrow(?:er|ers|ing)?", r"collateral",
                 r"pledged assets?", r"smes?", r"msmes?", r"small business(?:es)?",
                 r"business (?:owners?|clients?|borrowers?)", r"entrepreneurs?", r"negosyante",
                 r"micro-?enterprises?", r"credit(?! ?cards?)"),
        "card": (r"(?:credit )?cards?", r"cardholders?"),
        "payments": (r"qr", r"scan[- ]to[- ]pay", r"cashless", r"e-?wallets?", r"physical money",
                     r"cash payments?", r"market vendors?", r"vendors?", r"stall owners?", r"tindera", r"palengke"),
        "app": (r"mobile app", r"banking app", r"app ng bangko"),
        "atm": (r"atms?", r"cash machines?"),
        "deposits": (r"savings?(?: accounts?)?", r"checking accounts?", r"bank accounts?", r"deposits?"),
    },
    "topic": {
        # Not finishing an application, and the barriers named as reasons for it.
        "dropoff": (r"drop(?:s|ped|ping)?[- ]?offs?", r"abandon\w*", r"quit\w*", r"g[ai]ve up", r"giving up",
                    r"finish\w*", r"complet\w*", r"halfway", r"partway", r"put(?:ting)? off", r"discourag\w*",
                    r"deter\w*", r"tinatapos", r"natatapos", r"onboarding", r"sign[- ]?ups?", r"stops?",
                    r"paperwork", r"documents?", r"documentation", r"requirements?", r"ID", r"verification",
                    r"selfie", r"one-time pin", r"otp", r"approval", r"collateral", r"glitch\w*", r"errors?"),
        "rewards": (r"rewards?", r"perks?", r"benefits?", r"cash ?back", r"miles", r"travel", r"points", r"rebates?"),
        "support": (r"contact person", r"relationship manager", r"someone to call", r"makakausap", r"dedicated"),
        "satisfaction": (r"satisf\w*", r"happy", r"masaya", r"redesign"),
        "access": (r"queues?", r"lines?", r"pila", r"reach", r"distance", r"far", r"nearest"),
    },
}

# Metric key prefix -> (product, topic); the longest matching prefix wins. None: no facet on that
# dimension. Public studies reuse some families with other meanings ("support:in_person_help"), so
# those are listed by full key or left to the lexicon.
METRIC_FACETS: dict[str, tuple[str | None, str | None]] = {
    "barrier:": ("loan", "dropoff"),
    "barrier:access_to_finance": ("loan", None),
    "support:contact_person": ("loan", "support"),
    "channel_pref:": ("loan", None),
    "card_dropoff:": ("card", "dropoff"),
    "reward_pref:": ("card", "rewards"),
    "qr:": ("payments", None),
    "app_trend:": ("app", "satisfaction"),
    "atm:": ("atm", "access"),
}


ROLE_LABELS: dict[str, str] = {
    "si_analyst": "S&I analyst",
    "bu_user": "Business-unit user",
    "bu_approver": "Business-unit approver",
}


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
    embedding_provider: str = "hashing"   # "hashing" or "fastembed"
    embedding_model: str | None = None    # fastembed model name; None for the default


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
        embedding_provider=env.get("EMBEDDING_PROVIDER", "hashing").lower(),
        embedding_model=env.get("EMBEDDING_MODEL") or None,
    )
