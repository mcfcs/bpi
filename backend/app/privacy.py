"""Personal-data check at study review (checkpoint 1).

Before a study becomes searchable, its findings are scanned for text that could identify a person:
phone numbers, email addresses, account or card numbers, tax IDs, street addresses and names
("my name is ...", "Mr. ..."). A report written for internal use can carry these in verbatim quotes;
once approved, a finding is shown to every team that may read the study.

The check is pattern rules, not a model: it is cheap, it sends nothing anywhere, and every flag says
which rule matched. A flag does not block forever. The analyst edits the finding, or confirms they
checked it (the confirmation is audited with the approval). The report's own text, which only S&I
sees, is counted but never blocks.
"""

from __future__ import annotations

import re
from functools import lru_cache

import psycopg

from .config import PRIVACY_PATTERNS


@lru_cache(maxsize=1)
def _patterns() -> dict[str, tuple[str, re.Pattern]]:
    return {kind: (label, re.compile(rx)) for kind, (label, rx) in PRIVACY_PATTERNS.items()}


def scan(text: str | None) -> list[dict]:
    """Each match: its kind, a plain label and the matched text."""
    hits = []
    for kind, (label, rx) in _patterns().items():
        for m in rx.finditer(text or ""):
            hits.append({"kind": kind, "label": label, "match": m.group(0), "start": m.start(), "end": m.end()})
    return sorted(hits, key=lambda h: h["start"])


def study_flags(conn: psycopg.Connection, study_id: str) -> dict:
    """Flags on a study's findings (what readers would see) and a count for its source text."""
    findings = conn.execute(
        "select id::text as id, ordinal, text from public.findings where study_id = %s order by ordinal", [study_id]
    ).fetchall()
    flagged = []
    for f in findings:
        hits = scan(f["text"])
        if hits:
            flagged.append({"finding_id": f["id"], "ordinal": f["ordinal"], "text": f["text"],
                            "matches": [{k: h[k] for k in ("kind", "label", "match", "start", "end")} for h in hits]})
    source = conn.execute("select source_text from public.studies where id = %s", [study_id]).fetchone()
    return {"findings": flagged, "source_matches": len(scan(source["source_text"])) if source else 0}
