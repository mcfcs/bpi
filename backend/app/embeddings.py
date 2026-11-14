"""Text embeddings for hybrid search.

HashingEmbedder is deterministic and needs no external service, which keeps the demo and the tests
self-contained. It is essentially lexical, helped by a small banking glossary, so it misses
paraphrases ("scan-to-pay" vs "QR payments"): the same failure S&I described in their keyword
search. FastEmbedEmbedder runs a small neural model locally (ONNX, no data leaves the machine)
and is selected with EMBEDDING_PROVIDER=fastembed.

The column is vector(512). Models with fewer dimensions are zero-padded, which leaves cosine
similarity unchanged. Stored and query vectors must come from the same embedder: after switching,
re-embed with `python -m app.jobs.reembed` (dev_db.py does this automatically).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Protocol

EMBEDDING_DIM = 512


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> list[float]:
        """Embed a stored finding (document side)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a user's question (query side; some models use a different prefix)."""
        ...


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

    name = "hashing"

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

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


def model_cache_dir() -> Path:
    """Downloaded models live outside the repository (it may sit in a synced folder)."""
    if os.environ.get("EMBEDDING_CACHE_DIR"):
        return Path(os.environ["EMBEDDING_CACHE_DIR"])
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
    return base / "si-evidence-assistant" / "models"


class FastEmbedEmbedder:
    """A local sentence-embedding model through fastembed (ONNX Runtime, CPU).

    Install with `pip install -r requirements-semantic.txt`. The model downloads once into
    model_cache_dir(). Questions go through `query_embed` and findings through `passage_embed`, so
    models trained with query/passage prefixes (BGE, Arctic) get them.
    """

    def __init__(self, model: str):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise RuntimeError(
                "EMBEDDING_PROVIDER=fastembed needs the optional extra: pip install -r requirements-semantic.txt"
            ) from exc
        cache = model_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model, cache_dir=str(cache))
        self.model = model
        self.name = f"fastembed:{model}"
        self._cache: dict[tuple[str, str], list[float]] = {}

    def _fit(self, vec) -> list[float]:
        values = [float(v) for v in vec]
        if len(values) > EMBEDDING_DIM:
            raise ValueError(f"{self.model} returns {len(values)} dimensions; the column holds {EMBEDDING_DIM}.")
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values] + [0.0] * (EMBEDDING_DIM - len(values))

    def _one(self, kind: str, text: str) -> list[float]:
        key = (kind, text)
        if key not in self._cache:
            embed = self._model.query_embed if kind == "query" else self._model.passage_embed
            self._cache[key] = self._fit(next(iter(embed([text]))))
            if len(self._cache) > 2048:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[key]

    def embed(self, text: str) -> list[float]:
        return self._one("passage", text)

    def embed_query(self, text: str) -> list[float]:
        return self._one("query", text)


DEFAULT_FASTEMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_BEDROCK_EMBED_MODEL = "cohere.embed-multilingual-v3"


class EmbeddingUnavailable(RuntimeError):
    """A hosted embedder could not be reached (expired AWS sign-in, network). Stored findings were
    embedded by that model, so no local model can stand in: the request fails with a plain message."""


def search_ready(embedder: Embedder) -> tuple[bool, str | None]:
    """Whether question search can run now, without a billed call. Local embedders always can; the
    Bedrock embedder needs a valid AWS sign-in (checked with STS, which is free)."""
    if not embedder.name.startswith("bedrock:"):
        return True, None
    try:
        import boto3

        boto3.client("sts").get_caller_identity()
        return True, None
    except Exception:   # noqa: BLE001 - any failure means search will fail
        return False, "The AWS sign-in has expired or the network is down (run aws sso login)."


class BedrockEmbedder:
    """Cohere Embed v3 (or any Bedrock embedding model) via the Bedrock Runtime InvokeModel API.

    Cohere Multilingual v3 returns 1024 dimensions; we keep the first EMBEDDING_DIM (512) and
    renormalise to fit the vector(512) column. v3 was not trained for truncation (Embed v4 can return
    512 natively), so this costs some accuracy: `python -m eval.retrieval_eval --provider bedrock`
    measures it. Document and query sides use Cohere's input_type to get the right representation.
    """

    def __init__(self, model: str, region: str, client=None):
        import boto3
        self.model = model
        self.name = f"bedrock:{model}"
        self._client = client or boto3.client("bedrock-runtime", region_name=region)

    def _embed(self, text: str, input_type: str) -> list[float]:
        import json as _json
        from botocore.exceptions import BotoCoreError, ClientError
        body = {"texts": [text], "input_type": input_type, "truncate": "END"}
        v4 = "embed-v4" in self.model
        if v4:
            # Embed v4 returns the column's 512 dimensions itself (trained for shorter outputs).
            body.update(embedding_types=["float"], output_dimension=EMBEDDING_DIM)
        try:
            response = self._client.invoke_model(
                modelId=self.model,
                body=_json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
        except ClientError as exc:
            raise EmbeddingUnavailable(f"Bedrock embed error: {exc.response['Error']['Message']}") from exc
        except BotoCoreError as exc:   # expired SSO token, no credentials, connection failures
            raise EmbeddingUnavailable(f"Bedrock embed error: {exc}") from exc
        embeddings = _json.loads(response["body"].read())["embeddings"]
        values: list[float] = embeddings["float"][0] if v4 else embeddings[0]
        # v3: keep the column dimension and renormalise.
        values = values[:EMBEDDING_DIM]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def embed(self, text: str) -> list[float]:
        return self._embed(text, "search_document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, "search_query")


def build_embedder(provider: str | None = None, model: str | None = None) -> Embedder:
    """The embedder named by EMBEDDING_PROVIDER / EMBEDDING_MODEL (default: hashing)."""
    provider = (provider or os.environ.get("EMBEDDING_PROVIDER") or "hashing").lower()
    if provider == "hashing":
        return HashingEmbedder()
    if provider == "fastembed":
        return FastEmbedEmbedder(model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_FASTEMBED_MODEL)
    if provider == "bedrock":
        m = model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_BEDROCK_EMBED_MODEL
        region = os.environ.get("AWS_REGION", "ap-southeast-1")
        return BedrockEmbedder(m, region)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {provider!r}; use 'hashing', 'fastembed', or 'bedrock'.")


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
