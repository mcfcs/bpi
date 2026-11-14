"""Does a finding speak to the question's own concept, or only share generic words with it?

Similarity search matches "What slowed down SME loan renewals?" to loan drop-off studies because
both talk about SME loans. A brief or coverage check built on that is a false answer. Here a
question's *specific* terms are the words left after removing stopwords, question frames
("understand", "measure", "how often") and generic banking nouns ("SME", "loan", "card",
"customer"); a finding is on topic when it shares at least one of them (after the same synonym and
stem normalisation the hashing embedder uses).

Lexical overlap misses true paraphrases ("scan-to-pay" for QR), so how it is used depends on the
embedder (TOPICALITY_CONFIG): with the lexical hashing embedder it filters evidence; with a
semantic embedder it only lowers confidence unless the similarity is very high.

Facets (facets, source_facets, facet_multiplier) are a coarser, embedder-independent signal used by
retrieval's rerank: which product (loan, card, payments, app, ATM) and which topic (drop-off,
rewards, ...) a question and a finding are about. See FACET_LEXICON in config.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from .embeddings import tokens

# Words that frame a question or name the bank's generic products and people. Matching on them
# alone is what produced the false hits.
GENERIC = frozenset("""
understand explore measure size sizing market whether why how what which who when where often
much many need needs know learn find check assess estimate study studies research finding findings
data evidence insight insights survey report question people person customer customers client
clients user users consumer consumers sme smes owner owners business businesses bank banks banking
bpi loan loans card cards credit account accounts product products service services filipino
filipinos philippine philippines young professional professionals among group groups segment
segments team teams feel feels think thinks say says said use uses using get gets make makes
do does did ang mga ng sa ba na ko mo nila sila kami tayo po lang may yung kung para
apply applying application applications applicant applicants affect affects impact matter matters
problem problems issue issues reason reasons
test tests testing pulse panel tracker benchmark interview interviews
appetite interest interested demand gauge willing willingness bangko
""".split())
# The last two lines: study-design words, which sit in study titles ("Value Proposition Test") and so
# matched every finding of a study, and demand frames ("test appetite for", "gauge demand for",
# "measure interest in") that wrap the concept rather than name it.

_PRE = (
    (re.compile(r"\bdrop(?:s|ped|ping)?[- ]?offs?\b", re.I), " dropoff "),
    (re.compile(r"\bgiv(?:e|es|ing)[- ]up\b|\bgave[- ]up\b", re.I), " dropoff "),
    (re.compile(r"\bscan[- ]to[- ]pay\b", re.I), " qr "),
)
_EXTRA_SYNONYMS = {"online": "digital", "app": "digital", "apps": "digital", "mobile": "digital",
                   "e-wallet": "digital", "ewallet": "digital", "renewal": "renew", "renewals": "renew",
                   "slow": "delay", "slowed": "delay", "delays": "delay", "waiting": "wait",
                   "happy": "satisfaction", "masaya": "satisfaction", "satisfi": "satisfaction",
                   # In the Philippines a text message is "a text"; phishing is a scam message;
                   # the studies call small merchants "vendors".
                   "sms": "text", "phish": "scam", "merchant": "vendor"}

# Signs that the "question" is code or an injection attempt rather than a question.
JUNK = re.compile(r"(--\s*$|;\s*--|/\*|\*/|<\s*/?\s*script|\bdrop\s+table\b|\bunion\s+select\b|\bselect\s+\S+\s+from\b|\x00)",
                  re.IGNORECASE)


def _norm(word: str) -> str:
    word = _EXTRA_SYNONYMS.get(word, word)
    for suffix in ("ally", "al", "ly", "ion"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    # "impersonate" meets "impersonation" (-> "impersonat"), "automate" meets "automation".
    if len(word) > 6 and word.endswith("ate"):
        word = word[:-1]
    # "stopped" -> "stopp" after stemming; fold the doubled consonant so it meets "stops" -> "stop".
    if len(word) > 4 and word[-1] == word[-2] and word[-1] not in "aeiouls":
        word = word[:-1]
    return word


# Channel words ("online", "app", "mobile" all normalise to this): how something is done, not what.
_CHANNEL_TERMS = frozenset({_norm("digital")})


def _sequence(text: str | None) -> list[str]:
    text = text or ""
    for pattern, repl in _PRE:
        text = pattern.sub(repl, text)
    return [_norm(t) for t in tokens(text) if not t.isdigit()]


def terms(text: str | None) -> set[str]:
    """Normalised content terms of a text."""
    return set(_sequence(text))


def phrases(text: str | None) -> set[str]:
    """Adjacent content-term pairs ("card application"): two generic words together can name a
    specific concept even when neither does alone."""
    seq = _sequence(text)
    return {f"{a} {b}" for a, b in zip(seq, seq[1:]) if a != b}


def specific_terms(question: str) -> set[str]:
    generic = {_norm(t) for g in GENERIC for t in tokens(g)} | {_norm(g) for g in GENERIC}
    return {t for t in terms(question) if t not in generic and len(t) > 2}


def _source_parts(source) -> list[str | None]:
    from .config import metric_label

    return [source.text, source.theme and source.theme.replace("_", " "),
            metric_label(source.metric_key) if source.metric_key else None, source.study_title]


def source_terms(source) -> set[str]:
    parts: Iterable[str | None] = _source_parts(source)
    return set().union(*(terms(p) for p in parts))


def source_phrases(source) -> set[str]:
    # The finding's own words only: a study title like "SME Loan Journey Benchmark" would otherwise
    # make every finding in it match "SME loan renewals".
    return set().union(*(phrases(p) for p in _source_parts(source)[:3]))


def finding_terms(source) -> set[str]:
    """Terms of the finding itself (text and metric label), without the study title: used to pick
    which finding answers the question, where the shared title would make every finding equal."""
    from .config import metric_label

    return terms(source.text) | (terms(metric_label(source.metric_key)) if source.metric_key else set())


def concept_terms(question: str) -> set[str]:
    """The question's specific terms minus the products and channels it names (FACET_LEXICON
    products, "online"/"app"): what it asks *about* those products. "Measure interest in crypto
    savings accounts among overseas Filipino workers" -> {crypto, oversea, worker}."""
    return specific_terms(_product_pattern().sub(" ", question)) - _CHANNEL_TERMS


def overlap(question: str, source) -> set[str]:
    """The question's specific terms, or two-word phrases, that the finding also contains.

    When the question names a concept beyond its product, a shared term counts only if it is part of
    that concept: sharing "savings account", "credit card" or "SME owner" with a finding about
    something else is the false hit this module exists to stop. A shared topic facet also counts
    ("topic:dropoff"), since "not finishing", "giving up" and "abandoned" name one concept in
    different words. A question that names only a product ("What do we know about QR payments?")
    keeps any overlap."""
    shared = (specific_terms(question) & source_terms(source)) | (phrases(question) & source_phrases(source))
    concept = concept_terms(question)
    if not concept:
        return shared
    topics = facets(question)["topic"] & source_facets(source)["topic"]
    return {t for t in shared if any(word in concept for word in t.split(" "))} | {f"topic:{t}" for t in topics}


def concept_words(question: str) -> list[str]:
    """The question's own words that carry its concept terms, for a full-text check where only the
    database can see the text (restricted studies)."""
    concept = concept_terms(question)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", _product_pattern().sub(" ", question))
    return list(dict.fromkeys(w for w in words if terms(w) & concept))


@lru_cache(maxsize=1)
def _product_pattern() -> re.Pattern:
    from .config import FACET_LEXICON

    patterns = [p for group in FACET_LEXICON["product"].values() for p in group]
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _facet_patterns() -> dict[str, dict[str, re.Pattern]]:
    from .config import FACET_LEXICON

    return {dim: {name: re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)
                  for name, patterns in lexicon.items()}
            for dim, lexicon in FACET_LEXICON.items()}


def facets(text: str | None) -> dict[str, frozenset[str]]:
    """The products and topics a text names, e.g. {"product": {"card"}, "topic": {"dropoff"}}."""
    text = text or ""
    return {dim: frozenset(name for name, rx in patterns.items() if rx.search(text))
            for dim, patterns in _facet_patterns().items()}


def source_facets(source) -> dict[str, frozenset[str]]:
    """A finding's products and topics: from its metric family when known (reviewed vocabulary),
    otherwise read from the study title, theme and text with the question lexicon."""
    from .config import METRIC_FACETS

    key = getattr(source, "metric_key", None)
    prefix = max((p for p in METRIC_FACETS if key and key.startswith(p)), key=len, default=None)
    if prefix:
        product, topic = METRIC_FACETS[prefix]
        return {"product": frozenset({product} if product else ()), "topic": frozenset({topic} if topic else ())}
    theme = (source.theme or "").replace("_", " ")
    return facets(" ".join(p for p in (source.study_title, theme, source.text) if p))


def facet_multiplier(question_facets: dict[str, frozenset[str]], source, weights: dict[str, float]) -> float:
    """1 plus the weight of each facet dimension on which the finding matches the question. A
    dimension the question doesn't name adds nothing, so it never penalises a generic question."""
    own = source_facets(source)
    return 1.0 + sum(w for dim, w in weights.items()
                     if question_facets.get(dim) and question_facets[dim] & own.get(dim, frozenset()))


def answers_question(question: str, sources, bypass_similarity: float) -> bool:
    """Whether any retrieved finding speaks to the question's concept. Semantic search ranks
    something for every question, so "What savings goals do retirees set?" still pulls household
    budgeting findings above the floor. A brief built on those is a false answer, so when no finding
    shares the question's specific terms (or a concept phrase, or a topic facet) and none is a
    near-exact match, nothing answers the question. A question with no specific terms ("What do we
    know about QR payments?") is answered by whatever was retrieved."""
    if not specific_terms(question):
        return True
    findings = [s for s in sources if getattr(s, "finding_type", None) != "verbatim"]
    return any(overlap(question, s) or s.similarity >= bypass_similarity for s in findings)


def is_junk(question: str) -> bool:
    return bool(JUNK.search(question)) or not specific_terms(question) and not terms(question)
