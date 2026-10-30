"""Ingestion: report text -> study card + findings, pending S&I review.

Pasted text arrives through `ingest_report`; PDFs go through `documents.ingest_pdf`, which extracts
the page texts, calls the same extractor, stores the document and pins each finding to its page.
The LLM fills the study card (method, sample size, fieldwork end, population) and structured
findings (type, metric_key, value, unit, base n, subgroup, direction). The robustness tier is then
computed in code. Nothing is searchable until an analyst approves the card at checkpoint 1.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from . import audit
from .embeddings import Embedder, to_pgvector
from .llm_types import LLM
from .review import embedding_text
from .schemas import StudyCardExtraction
from .tiers import compute_tier_or_none


def known_metric_keys(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute("select distinct metric_key from public.findings where metric_key is not null").fetchall()
    return [r["metric_key"] for r in rows]


def store_study_card(conn: psycopg.Connection, card: StudyCardExtraction, *, owner_team_id: str,
                     access_level: str, embedder: Embedder, today: date, created_by: str | None,
                     source_name: str | None = None, source_text: str | None = None,
                     code: str | None = None, review_status: str = "pending_review",
                     reviewed_by: str | None = None, provenance: str = "internal",
                     publisher: str | None = None, finding_pages: list[int | None] | None = None,
                     finding_excerpts: list[str | None] | None = None) -> str:
    """Insert a study card and its findings. `provenance` labels the study as synthetic demo data,
    a public third-party source or internal research; `finding_pages` / `finding_excerpts` (one per
    finding, in order) record where in the study document each finding came from."""
    fieldwork_end = date.fromisoformat(card.fieldwork_end) if card.fieldwork_end else None
    tier = compute_tier_or_none(card.method_type, card.sample_size, fieldwork_end, today)
    columns = {
        "title": card.title,
        "summary": card.summary,
        "owner_team_id": owner_team_id,
        "access_level": access_level,
        "review_status": review_status,
        "source_name": source_name,
        "source_text": source_text,
        "created_by": created_by,
        "method_type": card.method_type,
        "sample_size": card.sample_size,
        "fieldwork_end": fieldwork_end,
        "population": Jsonb(card.population.model_dump()),
        "robustness_tier": tier,
        "tier_computed_at": today if tier else None,
        "provenance": provenance,
        "publisher": publisher,
    }
    if code:
        columns["code"] = code
    if review_status == "approved":
        columns["reviewed_by"] = reviewed_by
    names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    study_id = conn.execute(
        f"insert into public.studies ({names}{', reviewed_at' if review_status == 'approved' else ''}) "
        f"values ({placeholders}{', now()' if review_status == 'approved' else ''}) returning id::text as id",
        list(columns.values()),
    ).fetchone()["id"]

    for ordinal, f in enumerate(card.findings):
        subgroup = {k: v for k, v in (f.subgroup.model_dump() if f.subgroup else {}).items() if v}
        page = finding_pages[ordinal] if finding_pages and ordinal < len(finding_pages) else None
        excerpt = finding_excerpts[ordinal] if finding_excerpts and ordinal < len(finding_excerpts) else None
        conn.execute(
            "insert into public.findings (study_id, ordinal, text, theme, embedding, finding_type, metric_key, "
            "value, unit, base_n, subgroup, direction, page, source_excerpt) "
            "values (%s, %s, %s, %s, %s::extensions.vector, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [study_id, ordinal, f.text, f.theme, to_pgvector(embedder.embed(embedding_text(card.title, f.theme, f.text))),
             f.finding_type, f.metric_key, f.value if f.finding_type == "quant_stat" else None, f.unit,
             f.base_n, Jsonb(subgroup) if subgroup else None, f.direction, page, excerpt],
        )
    return study_id


def ingest_report(conn: psycopg.Connection, llm: LLM, embedder: Embedder, *, report_text: str,
                  owner_team_id: str, access_level: str, source_name: str | None, user_id: str,
                  today: date, provenance: str = "internal") -> str:
    card = llm.extract_study_card(report_text, known_metric_keys(conn))
    study_id = store_study_card(
        conn, card, owner_team_id=owner_team_id, access_level=access_level, embedder=embedder,
        today=today, created_by=user_id, source_name=source_name, source_text=report_text,
        provenance=provenance,
    )
    audit.log(conn, "study.ingested", "study", study_id, {
        "source_name": source_name, "extractor": getattr(llm, "name", "unknown"),
        "findings": len(card.findings), "method_type": card.method_type,
    })
    return study_id
