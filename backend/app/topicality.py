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
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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
""".split())

_PRE = (
    (re.compile(r"\bdrop(?:s|ped|ping)?[- ]?offs?\b", re.I), " dropoff "),
    (re.compile(r"\bgiv(?:e|es|ing)[- ]up\b|\bgave[- ]up\b", re.I), " dropoff "),
    (re.compile(r"\bscan[- ]to[- ]pay\b", re.I), " qr "),
)
_EXTRA_SYNONYMS = {"online": "digital", "app": "digital", "apps": "digital", "mobile": "digital",
                   "e-wallet": "digital", "ewallet": "digital", "renewal": "renew", "renewals": "renew",
                   "slow": "delay", "slowed": "delay", "delays": "delay", "waiting": "wait"}

# Signs that the "question" is code or an injection attempt rather than a question.
JUNK = re.compile(r"(--\s*$|;\s*--|/\*|\*/|<\s*/?\s*script|\bdrop\s+table\b|\bunion\s+select\b|\bselect\s+\S+\s+from\b|\x00)",
                  re.IGNORECASE)


def _norm(word: str) -> str:
    word = _EXTRA_SYNONYMS.get(word, word)
    for suffix in ("ally", "al", "ly", "ion"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    # "stopped" -> "stopp" after stemming; fold the doubled consonant so it meets "stops" -> "stop".
    if len(word) > 4 and word[-1] == word[-2] and word[-1] not in "aeiouls":
        word = word[:-1]
    return word


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


def overlap(question: str, source) -> set[str]:
    """The question's specific terms, or two-word phrases, that the finding also contains."""
    return (specific_terms(question) & source_terms(source)) | (phrases(question) & source_phrases(source))


def is_junk(question: str) -> bool:
    return bool(JUNK.search(question)) or not specific_terms(question) and not terms(question)
