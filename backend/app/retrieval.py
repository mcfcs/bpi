"""Retrieval: hybrid search over approved findings the caller may read, reranked by robustness tier.

Every query here runs on a connection from Database.as_user(), so row-level security decides what
comes back. Restricted studies are surfaced only as catalogue metadata (for "Request access").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg

from . import topicality
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
    facet_weight: float = 1.0  # topicality.facet_multiplier against the question (1.0: no facet match)
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


# Words that end a conjunct when reading outwards from "and": articles, prepositions, auxiliaries and
# question words. "Are fees and approval time a problem for SME owners?" -> "fees" | "approval time".
_BOUNDARY = frozenset("""
a an the of for in on to with about among by from at into over under than between within across
is are was were be been do does did can could would should will has have had
how what why which who whom whether when where while if that this these those their our your its
""".split())
_CONJUNCT_WORDS = 4
_CLAUSE_START = frozenset("how what why which who whom when where whether do does did is are was were can could should will".split())


def split_question(question: str) -> list[str]:
    """A question that asks about two things joined by "and", once per thing: "Are fees and approval
    time a problem for SME owners?" -> ["Are fees a problem for SME owners?", "Are approval time a
    problem for SME owners?"]. Searched as one, the stronger part's best match sets the relative
    floor and the weaker part's findings fall under it. Split only when each side has a concept of
    its own and the two differ ("ID and document checks", "..., and does it matter?" stay whole)."""
    words = question.split()
    for i, word in enumerate(words):
        if word.lower() != "and" or i == 0 or i == len(words) - 1:
            continue
        # Two questions in one: "How do typhoons affect income and how do workshops change literacy?"
        if words[i + 1].lower() in _CLAUSE_START:
            first, second = " ".join(words[:i]).rstrip(",;"), " ".join(words[i + 1:])
            c1, c2 = topicality.concept_terms(first), topicality.concept_terms(second)
            if c1 and c2 and c1 != c2:
                return [first + "?", second[0].upper() + second[1:]]
            continue
        if words[i - 1].endswith((",", ";")):
            continue
        left, right = [], []
        for w in reversed(words[:i]):
            core = w.strip("?.,;:!").lower()
            if core in _BOUNDARY or w.endswith((",", ";")) or len(left) == _CONJUNCT_WORDS:
                break
            left.insert(0, w)
        article = ""
        for w in words[i + 1:]:
            core = w.strip("?.,;:!").lower()
            if core in ("a", "an", "the") and not right and not article:
                article = w   # "the selfie check and the annual fee": the second part may start with one
                continue
            if core in _BOUNDARY or len(right) == _CONJUNCT_WORDS:
                break
            if core.endswith("ing") and len(right) >= 2:
                break   # "the annual fee putting ...": the verb after a two-word noun phrase
            right.append(w)
            if w.endswith(("?", ".", ",", ";", "!")):
                break
        if article and right:
            right.insert(0, article)
        a, b = " ".join(left), " ".join(right[1:] if article else right).rstrip("?.,;:!")
        ca, cb = topicality.concept_terms(a), topicality.concept_terms(b)
        if not a or not b or not ca or not cb or ca == cb:
            continue
        joined = " ".join(left + ["and"] + right)
        start = question.index(joined)
        tail = question[start + len(joined):]
        if right[-1] != b.split()[-1] or not right[-1].endswith(b.split()[-1]):
            tail = right[-1][len(b.split()[-1]):] + tail   # keep the "?" that ended the conjunct
        return [question[:start] + a + tail, question[:start] + b + tail]
    return []


def search(conn: psycopg.Connection, question: str, embedder: Embedder, *,
           query_embedding: list[float] | None = None, config: dict | None = None) -> list[Source]:
    cfg = {**retrieval_config(embedder.name), **(config or {})}
    vector = query_embedding or embedder.embed_query(question)
    whole = _search_once(conn, question, vector, cfg)
    parts = split_question(question)
    if not parts:
        return whole
    # Each part keeps its own best matches: merge the result lists in turn (whole, part 1, part 2),
    # dropping repeats, up to the usual number of findings.
    lists = [whole] + [_search_once(conn, part, embedder.embed_query(part), cfg) for part in parts]
    merged: dict[str, Source] = {}
    for rank in range(max(len(x) for x in lists)):
        for found in lists:
            if rank < len(found) and found[rank].finding_id not in merged:
                merged[found[rank].finding_id] = found[rank]
    return list(merged.values())[: cfg["match_count"]]


def _search_once(conn: psycopg.Connection, question: str, vector: list[float], cfg: dict) -> list[Source]:
    rows = conn.execute(
        "select finding_id::text as finding_id, similarity, score "
        "from public.match_findings(%s::extensions.vector, %s, %s, %s, %s)",
        [to_pgvector(vector), question, cfg["match_count"], cfg["min_similarity"], cfg["rrf_k"]],
    ).fetchall()
    if not rows:
        return []
    hits = {row["finding_id"]: row for row in rows}
    candidates = load_sources(conn, "f.id = any(%s::uuid[])", [list(hits)])
    # Facet rerank: loan and card applications share most of their words, so cosine alone puts card
    # findings next to loan ones (and card rewards next to card drop-off). Matching the question's
    # product and topic raises a finding's score and the similarity the relative floor compares.
    # The absolute floor (in match_findings) stays on raw cosine, so nothing below it ever gets in and
    # a question that matches nothing still gets nothing.
    wanted = topicality.facets(question)
    for source in candidates:
        hit = hits[source.finding_id]
        source.similarity = hit["similarity"]
        source.facet_weight = topicality.facet_multiplier(wanted, source, cfg["facet_boost"])
    if not candidates:
        return []
    best = max(s.similarity * s.facet_weight for s in candidates)
    sources = [s for s in candidates if s.similarity * s.facet_weight >= cfg["relative_floor"] * best]
    for source in sources:
        source.score = (hits[source.finding_id]["score"] * source.facet_weight
                        * cfg["tier_boost"].get(source.effective_tier, 1.0))
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


def restricted_matches(conn: psycopg.Connection, query_embedding: list[float], config: dict | None = None,
                       question: str | None = None) -> list[dict]:
    """Studies that match but the caller cannot read: metadata only, plus the caller's request status.

    With `question`, a study must also share the question's concept (topicality.concept_words,
    checked in the database against its findings' text) unless its similarity reaches
    restricted_bypass_similarity: similarity alone hinted card-rewards studies for any card question."""
    cfg = {**RETRIEVAL_CONFIG, **(config or {})}
    concept = " ".join(topicality.concept_words(question)) if question else ""
    rows = conn.execute(
        "select study_id::text as study_id, code, title, owner_team, similarity "
        "from public.restricted_study_matches(%s::extensions.vector, %s, %s, %s, %s)",
        [to_pgvector(query_embedding), cfg["restricted_limit"], cfg["restricted_min_similarity"],
         concept or None, cfg["restricted_bypass_similarity"]],
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
