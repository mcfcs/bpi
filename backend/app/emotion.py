"""Emotion cues for qualitative findings and verbatims.

S&I use qualitative research to "humanise the learning", so the brief shows which feelings
participants voiced next to their words. This is a small English and Tagalog/Taglish lexicon, run
in code: deterministic, offline, and explainable (the matched cue words are returned). It labels
the wording of a quote, not how many people feel that way, and the UI should present it as an
indicative cue. Extend the lexicon here; a reviewed model can replace it behind detect().
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

# Order matters for ties: the first emotion listed wins.
LEXICON: dict[str, dict] = {
    "distrust": {
        "label": "Distrust", "tone": "negative",
        "cues": [r"\btrust", r"\bscam", r"really the bank", r"\blegit", r"suspicious", r"\bwary\b",
                 r"sineseryoso", r"taking me seriously", r"\btakot\b", r"\bafraid\b"],
    },
    "frustration": {
        "label": "Frustration", "tone": "negative",
        "cues": [r"annoy", r"frustrat", r"nakakainis", r"\binis\b", r"\bgave up\b", r"\bgive up\b",
                 r"\bstuck\b", r"three times", r"tatlong beses", r"paulit-?ulit", r"\bhassle\b(?!-free)",
                 r"\babala\b", r"slows? me down", r"\bayaw\b", r"nakakapagod", r"same form",
                 r"\bagain\b", r"wala pa ring", r"no update", r"kept failing", r"\bfailing\b"],
    },
    "confusion": {
        "label": "Confusion", "tone": "negative",
        "cues": [r"confus", r"not sure (?:which|what|how|where)", r"\bunclear\b", r"didn'?t know",
                 r"don'?t know", r"hindi ko alam", r"di ko alam", r"nalito", r"nalilito", r"\bgulo\b",
                 r"no idea", r"whom to call"],
    },
    "worry": {
        "label": "Worry", "tone": "negative",
        "cues": [r"\bworr", r"nervous", r"anxious", r"kinakabahan", r"\bkabado\b"],
    },
    "relief": {
        "label": "Relief", "tone": "positive",
        "cues": [r"\brelie", r"panatag", r"at ease", r"nakahinga", r"\bfinally\b", r"buti na lang",
                 r"\bglad\b", r"peace of mind"],
    },
    "convenience": {
        "label": "Convenience", "tone": "positive",
        "cues": [r"convenien", r"\beasy\b", r"\beasier\b", r"madali", r"mabilis", r"\bfaster\b",
                 r"\bquick", r"hassle-free"],
    },
}

_COMPILED = {key: [re.compile(c, re.IGNORECASE) for c in spec["cues"]] for key, spec in LEXICON.items()}


def _matches(text: str) -> Counter:
    counts: Counter = Counter()
    for key, patterns in _COMPILED.items():
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            counts[key] = hits
    return counts


def _cue(key: str, cues: list[str] | None = None) -> dict:
    spec = LEXICON[key]
    out = {"key": key, "label": spec["label"], "tone": spec["tone"], "basis": "lexicon"}
    if cues is not None:
        out["cues"] = cues
    return out


def detect(text: str | None) -> dict | None:
    """The strongest emotion cue in one text, e.g. {"key": "frustration", "label": "Frustration",
    "tone": "negative", "basis": "lexicon", "cues": ["nakakainis"]}; None when no cue matches."""
    if not text:
        return None
    counts = _matches(text)
    if not counts:
        return None
    order = list(LEXICON)
    key = max(counts, key=lambda k: (counts[k], -order.index(k)))
    cues = [m.group(0) for p in _COMPILED[key] if (m := p.search(text))]
    return _cue(key, cues)


def detect_many(texts: Iterable[str | None], limit: int = 2) -> list[dict]:
    """The emotions voiced across several texts (a theme and its verbatims), strongest first."""
    totals: Counter = Counter()
    for text in texts:
        if text:
            totals.update(_matches(text))
    order = list(LEXICON)
    ranked = sorted(totals, key=lambda k: (-totals[k], order.index(k)))
    return [_cue(k) for k in ranked[:limit]]


def all_cues() -> list[dict]:
    """Every emotion the lexicon knows, in lexicon order (for matching labels a sentence names)."""
    return [_cue(key) for key in LEXICON]
