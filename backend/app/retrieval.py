"""Retrieval: hybrid search over approved findings the caller may read, reranked by robustness tier.

Every query here runs on a connection from Database.as_user(), so row-level security decides what
comes back. Restricted studies are surfaced only as catalogue metadata (for "Request access").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg

from .config import DIRECTION_FALLBACK, RETRIEVAL_CONFIG, retrieval_config
from .divergence import FindingCtx, parse_age_band
from .embeddings import Embedder, to_pgvector


@dataclass
class Source:
    """A finding the caller can read, with the study context needed to weigh and cite it."""

    finding_id: str
    study_id: str
    text: str
    theme: str | None
    finding_type: str | None
    metric_key: str | None
    value: Decimal | None
    unit: str | None
    base_n: int | None
    subgroup: dict | None
    direction: str | None
    study_code: str
    study_title: str
    method_type: str | None
    sample_size: int | None
    fieldwork_end: date | None
    population: dict | None
    effective_tier: str | None
    robustness_tier: str | None
    tier_override: str | None
    owner_team: str
    access_level: str
    similarity: float = 0.0
    score: float = 0.0
    attached: bool = False  # a verbatim added because its theme was retrieved
    study_summary: str | None = None  # read for the method label ("6 FGDs"), not sent as evidence

    @property
    def is_quant(self) -> bool:
        return self.method_type == "quant" or (self.method_type == "mixed" and self.finding_type == "quant_stat")

    @property
    def is_qual(self) -> bool:
        return self.method_type == "qual"

    @property
    def topic(self) -> str | None:
        if self.metric_key:
            return self.metric_key
        return f"theme:{self.theme}" if self.theme else None

    def resolved_direction(self) -> str | None:
        if self.direction:
            return self.direction
        if self.finding_type == "quant_stat" and self.value is not None and self.unit in DIRECTION_FALLBACK:
            high, low = DIRECTION_FALLBACK[self.unit]
            value = float(self.value)
            if self.unit == "rank":
                return "high" if value <= high else "low" if value >= low else "neutral"
            return "high" if value >= high else "low" if value <= low else "neutral"
        return None

    def population_view(self) -> tuple[int | None, int | None, tuple[str, ...], str | None]:
        """Age range, regions and segment this finding speaks for: the subgroup where it narrows the
        study population, otherwise the study population."""
        pop = self.population or {}
        age_min, age_max = pop.get("age_min"), pop.get("age_max")
        regions = tuple(pop.get("regions") or ())
        segment = pop.get("segment")
        sub = self.subgroup or {}
        if sub.get("age_band"):
            lo, hi = parse_age_band(sub["age_band"])
            if lo is not None:
                age_min, age_max = lo, hi
        if sub.get("region"):
            regions = (sub["region"],)
        if sub.get("segment"):
            segment = sub["segment"]
        return age_min, age_max, regions, segment

    def ctx(self) -> FindingCtx:
        age_min, age_max, regions, segment = self.population_view()
        return FindingCtx(
            finding_id=self.finding_id,
            study_id=self.study_id,
            topic=self.topic,
            direction=self.resolved_direction(),
            method_type=self.method_type,
            age_min=age_min,
            age_max=age_max,
            regions=regions,
            segment=segment,
            fieldwork_end=self.fieldwork_end,
            evidence="quant" if self.is_quant else "qual",
            subgroup=tuple(sorted((k, str(v)) for k, v in (self.subgroup or {}).items() if v)),
        )


SOURCE_COLUMNS = """
    f.id::text as finding_id, f.study_id::text as study_id, f.text, f.theme, f.finding_type,
    f.metric_key, f.value, f.unit, f.base_n, f.subgroup, f.direction,
    s.code as study_code, s.title as study_title, s.method_type, s.sample_size, s.fieldwork_end,
    s.population, s.effective_tier, s.robustness_tier, s.tier_override, s.access_level,
    t.name as owner_team, s.summary as study_summary
"""


def load_sources(conn: psycopg.Connection, where: str, params: list) -> list[Source]:
    rows = conn.execute(
        f"""
        select {SOURCE_COLUMNS}
        from public.findings f
        join public.studies s on s.id = f.study_id
        join public.teams t on t.id = s.owner_team_id
        where s.review_status = 'approved' and ({where})
        order by s.code, f.ordinal
        """,
        params,
    ).fetchall()
    return [Source(**row) for row in rows]


def search(conn: psycopg.Connection, question: str, embedder: Embedder, *,
           query_embedding: list[float] | None = None, config: dict | None = None) -> list[Source]:
    cfg = {**retrieval_config(embedder.name), **(config or {})}
    vector = query_embedding or embedder.embed_query(question)
    rows = conn.execute(
        "select finding_id::text as finding_id, similarity, score "
        "from public.match_findings(%s::extensions.vector, %s, %s, %s, %s)",
        [to_pgvector(vector), question, cfg["match_count"], cfg["min_similarity"], cfg["rrf_k"]],
    ).fetchall()
    if not rows:
        return []
    best = max(row["similarity"] for row in rows)
    hits = {row["finding_id"]: row for row in rows if row["similarity"] >= cfg["relative_floor"] * best}
    sources = load_sources(conn, "f.id = any(%s::uuid[])", [list(hits)])
    for source in sources:
        hit = hits[source.finding_id]
        source.similarity = hit["similarity"]
        source.score = hit["score"] * cfg["tier_boost"].get(source.effective_tier, 1.0)
    sources.sort(key=lambda s: s.score, reverse=True)
    return sources


def attach_verbatims(conn: psycopg.Connection, sources: list[Source], per_theme: int | None = None) -> list[Source]:
    """Add the verbatims that go with each retrieved qualitative theme (same study, same metric or
    theme), so "What people say" can quote participants even when the quotes don't match the
    question's wording."""
    per_theme = per_theme or RETRIEVAL_CONFIG["verbatims_per_theme"]
    themes = [s for s in sources if s.finding_type == "qual_theme"]
    if not themes:
        return sources
    have = {s.finding_id for s in sources}
    candidates = load_sources(
        conn, "f.finding_type = 'verbatim' and f.study_id = any(%s::uuid[])",
        [list({s.study_id for s in themes})],
    )
    added: list[Source] = []
    for theme in themes:
        matching = [
            v for v in candidates
            if v.study_id == theme.study_id
            and ((theme.metric_key and v.metric_key == theme.metric_key)
                 or (not theme.metric_key and theme.theme and v.theme == theme.theme))
        ]
        for verbatim in matching[:per_theme]:
            if verbatim.finding_id not in have:
                verbatim.attached = True
                verbatim.score = theme.score * 0.5
                have.add(verbatim.finding_id)
                added.append(verbatim)
    return sources + added


def restricted_matches(conn: psycopg.Connection, query_embedding: list[float], config: dict | None = None) -> list[dict]:
    """Studies that match but the caller cannot read: metadata only, plus the caller's request status."""
    cfg = {**RETRIEVAL_CONFIG, **(config or {})}
    rows = conn.execute(
        "select study_id::text as study_id, code, title, owner_team, similarity "
        "from public.restricted_study_matches(%s::extensions.vector, %s, %s)",
        [to_pgvector(query_embedding), cfg["restricted_limit"], cfg["restricted_min_similarity"]],
    ).fetchall()
    if not rows:
        return []
    requests = conn.execute(
        "select distinct on (study_id) study_id::text as study_id, status from public.access_requests "
        "where requester_id = auth.uid() and study_id = any(%s::uuid[]) order by study_id, created_at desc",
        [[r["study_id"] for r in rows]],
    ).fetchall()
    status = {r["study_id"]: r["status"] for r in requests}
    return [{**row, "request_status": status.get(row["study_id"])} for row in rows]
