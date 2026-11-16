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
    # Cohere Multilingual v3 on Bedrock (cut to 512 dims, see BedrockEmbedder). Sweep on the tune half
    # of the 64 questions (14 Nov): best 0.48 / 0.8; 0.48 / 0.7 kept canonical recall at 1.00 on both
    # halves with held-out micro F1 0.83 (fastembed 0.67) and Taglish recall 0.88 (fastembed 0.67).
    # Off-topic questions still get hits (3 of 6, best match ~0.51). Coverage cases pass 13/13 for any
    # coverage floor from 0.50 to 0.62 and restricted floor 0.48 or 0.52, so those are mid-range picks
    # the cases don't discriminate. Proposed defaults, not validated by S&I.
    "bedrock:cohere.embed-multilingual-v3": {
        "retrieval": {"min_similarity": 0.48, "relative_floor": 0.7, "restricted_min_similarity": 0.52,
                      "restricted_bypass_similarity": 0.7},
        "coverage": {"min_similarity": 0.56, "relative_floor": 0.8},
    },
    # Cohere Embed v4 on Bedrock (512 dims natively; Singapore serves it only through the global
    # profile). Tune-half sweep (14 Nov): best 0.34 / 0.7, held-out micro F1 0.88 (v3 0.83), all 64:
    # 0.87 with paraphrase precision 0.91 and 1 of 6 off-topic questions with hits (v3: 3 of 6), but
    # Taglish recall 0.77 (v3 0.88). Coverage cases pass 13/13 for any coverage floor 0.38-0.54 and
    # restricted floor 0.34 or 0.38: mid-range picks. Proposed defaults, not validated by S&I.
    "bedrock:global.cohere.embed-v4:0": {
        "retrieval": {"min_similarity": 0.34, "relative_floor": 0.7, "restricted_min_similarity": 0.38,
                      "restricted_bypass_similarity": 0.7},
        "coverage": {"min_similarity": 0.46, "relative_floor": 0.8},
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

# "A new study answers your question" (alerts.py): when a study is approved, unanswered questions
# asked in the last lookback_days are searched again as their askers, at most max_questions of them
# (one embedding call each). Proposed defaults, not validated by S&I.
ALERT_CONFIG: dict = {"lookback_days": 180, "max_questions": 50}

# Value summary on the audit page (usage.py). Minutes an analyst would spend finding and explaining
# an answer that a brief gave without escalation: a proposed estimate for S&I to replace with its own
# figure. Shown as an estimate, never as a measurement.
VALUE_CONFIG: dict = {"analyst_minutes_per_question": 30}

# Research-gap map (gaps.py): rows are metric families (the part of a metric key before ":"; a
# "_trend" family joins its base). Labels are proposed wording for S&I to review.
FAMILY_LABELS: dict[str, str] = {
    "barrier": "SME loan application drop-off",
    "support": "SME support and contact person",
    "card_dropoff": "Credit card application drop-off",
    "reward_pref": "Credit card rewards",
    "qr": "QR payments",
    "app": "Mobile app experience",
    "atm": "ATM access",
    "fraud": "Scams and fraud",
    "service": "Complaints and service",
    "literacy": "Financial literacy",
    "budget": "Payday budgeting",
    "wellness": "Workplace money wellness",
    "gig": "Gig and delivery workers",
    "fisherfolk": "Fisherfolk household finances",
    "climate": "Typhoons and household finances",
    "green": "Green products",
    "privacy": "Data privacy and sharing",
    "inclusive": "Customers with disabilities",
    "treasury": "Corporate treasury",
}
# Gap-map columns, from geography.area_type of the finding's place. A study across Metro Manila and
# provincial areas ("mixed") counts in both.
GAP_AREAS: dict[str, tuple[str, ...]] = {
    "metro_manila": ("Metro Manila",), "provincial_city": ("Provincial",), "provincial": ("Provincial",),
    "rural": ("Rural",), "mixed": ("Metro Manila", "Provincial"), "nationwide": ("Nationwide",),
}
GAP_COLUMNS: tuple[str, ...] = ("Metro Manila", "Provincial", "Rural", "Nationwide")
# An unanswered question is placed on the topic most common among its nearest approved findings.
GAP_CONFIG: dict = {"nearest_findings": 5}

# Personal-data check at study review (privacy.py): patterns that suggest a finding identifies a
# person. A match blocks approval until the analyst edits the finding or confirms they checked it.
# Proposed patterns for Philippine formats, not validated by S&I or BPI's data privacy office;
# false positives are expected and cost one confirmation click.
PRIVACY_PATTERNS: dict[str, tuple[str, str]] = {
    "phone": ("Phone number", r"(?:\+63[\s-]?|\b0)9\d{2}[\s-]?\d{3}[\s-]?\d{4}\b"),
    "email": ("Email address", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "account": ("Account or card number", r"\b\d(?:[ -]?\d){11,18}\b"),
    "tin": ("Tax ID (TIN)", r"\b\d{3}-\d{3}-\d{3}(?:-\d{3,5})?\b"),
    "name": ("A person's name", r"\b(?:my name is|ako si|pangalan ko(?: ay)?|Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Gng\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"),
    "address": ("Street address", r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Street|Ave|Avenue|Road|Rd|Blvd)\b\.?"),
}

# Overlap check at study review (overlap.py): approved findings closest to each finding of the new
# study. A study counts as overlapping when it shares a metric family or a finding at least this
# similar (the embedder's retrieval floor plus overlap_margin). Proposed defaults.
OVERLAP_CONFIG: dict = {"neighbours_per_finding": 3, "overlap_margin": 0.1, "max_studies": 4}

METRIC_LABELS.update({
    "card_dropoff:id_verification": "ID verification",
    "card_dropoff:fees": "Fees",
    "card_dropoff:approval_wait": "Waiting for approval",
    "card_dropoff:otp_delay": "One-time PIN delays",
    "card_dropoff:app_errors": "App errors",
    "app_trend:satisfaction": "Satisfaction with the mobile app",
    "atm:long_queues": "Long ATM queues",
    "atm:distance": "Distance to the nearest ATM",
    # Metrics that get charts in the wider synthetic corpus (scams, service, literacy, climate, work).
    "fraud:fake_text_exposure": "Received a fake bank text",
    "fraud:clicked_fake_link": "Clicked a link in a fake bank text",
    "fraud:reporting_unclear": "Did not know how to report a fake bank text",
    "service:first_call_resolution": "Issue resolved in the first call",
    "literacy:compound_interest": "Answered the compound interest question correctly",
    "literacy_trend:workshop_gain": "Answered the compound interest question correctly after the workshop",
    "climate:income_loss": "Lost income to a typhoon or flood",
    "gig:income_volatility": "Weekly income swings of more than a quarter",
    "green:solar_interest": "Would install rooftop solar with instalments",
    "privacy_trend:offer_comfort": "Comfort with data use for offers",
    "privacy:prefers_tailored_offers": "Prefers offers based on how they bank",
    "wellness:short_before_payday": "Ran out of money before payday",
    "treasury:signoff_delay": "Multi-level sign-off slowed urgent releases",
})
METRIC_CHART_TITLES.update({
    "card_dropoff:": "Cited {label_lower} as a reason for not finishing a card application",
    "app_trend:": "{label} (latest wave)",
    "privacy_trend:": "{label} (latest wave)",
    "atm:": "Named {label_lower} as a problem",
})

# How a segment statement describes a metric when it is prominent (high) or not (low), by key
# prefix. Used for "Fees: a driver of drop-off among ..., but not among ...".
METRIC_STANCE_PHRASES: dict[str, tuple[str, str]] = {
    "barrier:": ("a reason for dropping off", "not a main reason for dropping off"),
    "card_dropoff:": ("a driver of drop-off", "not a driver of drop-off"),
    "reward_pref:": ("the preferred reward", "not the preferred reward"),
    "app_trend:": ("improving", "declining"),
    "privacy_trend:": ("rising", "falling"),
    "literacy_trend:": ("improving", "barely improving"),
    "privacy:prefers_tailored_offers": ("wanted", "not wanted"),
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
# brief_needs_concept: with a semantic embedder, a question none of whose retrieved findings shares
# its concept (topicality.answers_question) gets "no study covers this" instead of a brief. On the
# 64 eval questions with Bedrock search (14 Nov) it removed 3 of the 4 off-topic questions that still
# retrieved findings and blocked no answerable one. Proposed default, not validated by S&I.
TOPICALITY_CONFIG: dict[str, dict] = {
    "hashing": {"filter_off_topic": True, "coverage_bypass_similarity": 2.0,   # never bypassed
                "brief_needs_concept": False},   # already filtered finding by finding
    "default": {"filter_off_topic": False, "coverage_bypass_similarity": 0.7, "brief_needs_concept": True},
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
    llm_provider: str          # "anthropic", "bedrock", or "offline"
    llm_model: str
    llm_effort: str
    aws_region: str
    aws_bedrock_model: str
    commissioning_adapter: str  # "noop" or "webhook"
    commissioning_webhook_url: str | None
    commissioning_webhook_headers: dict[str, str]
    cors_origins: tuple[str, ...]
    embedding_provider: str = "hashing"   # "hashing" or "fastembed"
    embedding_model: str | None = None    # fastembed model name; None for the default
    # Hosted demos where the backend has its own public URL (see README.md): when set, every
    # /api request except /api/health must carry this value in X-Demo-Key, which frontend/proxy.ts adds.
    # Unset locally and in tests, so nothing changes there.
    backend_shared_secret: str | None = None


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
        aws_region=env.get("AWS_REGION", "ap-southeast-1"),
        aws_bedrock_model=env.get("AWS_BEDROCK_MODEL", "global.anthropic.claude-opus-5-5"),
        commissioning_adapter=env.get("COMMISSIONING_ADAPTER", "noop"),
        commissioning_webhook_url=env.get("COMMISSIONING_WEBHOOK_URL") or None,
        commissioning_webhook_headers=json.loads(env.get("COMMISSIONING_WEBHOOK_HEADERS", "{}")),
        cors_origins=tuple(
            o.strip() for o in env.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ),
        embedding_provider=env.get("EMBEDDING_PROVIDER", "hashing").lower(),
        embedding_model=env.get("EMBEDDING_MODEL") or None,
        backend_shared_secret=env.get("BACKEND_SHARED_SECRET") or None,
    )
