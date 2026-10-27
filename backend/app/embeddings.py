"""Text embeddings for hybrid search.

HashingEmbedder is deterministic and needs no external service, which keeps the demo and the tests
self-contained. It is essentially lexical, helped by a small banking glossary. For production
retrieval, swap in a hosted embedding model behind the same `embed()` method; the column is
vector(512), so choose a model or output dimension that matches.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

EMBEDDING_DIM = 512


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


STOPWORDS = frozenset(
    """a about across after all also am among an and any are as at be because been before being
    between both but by can could did do does doing during each few for from further had has have
    having here how i if in into is it its just may might more most much my no nor not of off on
    once only or other our out over own same she should so some such than that the their them then
    there these they this those through to too under until up very was we were what when where
    which while who whom why will with would you your""".split()
)

# Multi-word phrases and synonyms that should match each other. A hosted embedding model makes
# most of this unnecessary; keep it short.
PHRASES = {
    "drop off": "dropoff",
    "drop-off": "dropoff",
    "dropped off": "dropoff",
    "gave up": "dropoff",
    "give up": "dropoff",
    "small business": "sme",
    "small and medium": "sme",
    "contact person": "contactperson",
    "relationship manager": "contactperson",
    "someone to call": "contactperson",
    "travel miles": "travel",
    "air miles": "travel",
    "cash back": "cashback",
    "qr code": "qr",
}
SYNONYMS = {
    "abandon": "dropoff",
    "abandoned": "dropoff",
    "abandoning": "dropoff",
    "abandonment": "dropoff",
    "quit": "dropoff",
    "msme": "sme",
    "msmes": "sme",
    "smes": "sme",
    "charges": "fee",
    "charge": "fee",
    "fees": "fee",
    "entrepreneurs": "owner",
    "entrepreneur": "owner",
    "proprietors": "owner",
    "vendors": "vendor",
    "sellers": "vendor",
    "miles": "travel",
    "points": "reward",
}


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix) and not word.endswith("ss"):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    text = text.lower()
    for phrase, replacement in PHRASES.items():
        text = text.replace(phrase, f" {replacement} ")
    words = re.findall(r"[a-z0-9]+", text)
    out = []
    for word in words:
        if word in STOPWORDS:
            continue
        word = SYNONYMS.get(word, word)
        out.append(_stem(word))
    return out


def _bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % EMBEDDING_DIM, (1.0 if (value >> 63) & 1 else -1.0)


class HashingEmbedder:
    """Signed feature hashing of unigrams and bigrams, sublinear term frequency, L2-normalised."""

    def embed(self, text: str) -> list[float]:
        toks = tokens(text)
        counts: dict[str, float] = {}
        for tok in toks:
            counts[tok] = counts.get(tok, 0.0) + 1.0
        for left, right in zip(toks, toks[1:]):
            key = f"{left}_{right}"
            counts[key] = counts.get(key, 0.0) + 0.5
        vec = [0.0] * EMBEDDING_DIM
        for feature, count in counts.items():
            index, sign = _bucket(feature)
            vec[index] += sign * (1.0 + math.log(count)) if count >= 1 else sign * count
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
