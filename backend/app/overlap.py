"""Overlap check at study review (checkpoint 1): which approved studies a new study repeats.

For each finding of the study under review, the closest approved findings are looked up by meaning
(the stored embeddings, under the analyst's RLS) and by metric family. Studies that share a topic are
then compared in code, the same way briefs compare studies (divergence.py): who was asked (age,
segment), where, and when. Shared figures are put side by side from the database.

The result helps S&I spot research commissioned twice and findings that move over time. It decides
nothing: the analyst still approves or rejects, and an overlap is often welcome (a newer wave, a
different region). No model is called.
"""

from __future__ import annotations

from collections import defaultdict

import psycopg

from .config import DIVERGENCE_CONFIG, OVERLAP_CONFIG, metric_label, retrieval_config
from .describe import fmt_value
from .divergence import ranges_overlap, regions_overlap
from .gaps import family_label, family_of
from .geography import describe as describe_place
from .geography import is_nationwide
from .tiers import months_between

def _people(pop: dict | None) -> tuple[tuple[int | None, int | None], list[str], str | None]:
    pop = pop or {}
    return (pop.get("age_min"), pop.get("age_max")), list(pop.get("regions") or []), pop.get("segment")


def _compare(new: dict, old: dict) -> tuple[str, list[str]]:
    """How two studies' populations relate: a verdict and the ways they differ."""
    (age_a, regions_a, seg_a), (age_b, regions_b, seg_b) = _people(new["population"]), _people(old["population"])
    differs = []
    if not ranges_overlap(age_a, age_b):
        differs.append("age")
    if seg_a and seg_b and seg_a.strip().lower() != seg_b.strip().lower():
        differs.append("segment")
    nationwide = is_nationwide(regions_a) or is_nationwide(regions_b)
    if not nationwide and not regions_overlap(regions_a, regions_b):
        differs.append("place")
    if new["fieldwork_end"] and old["fieldwork_end"]:
        months = abs(months_between(new["fieldwork_end"], old["fieldwork_end"]))
        if months > DIVERGENCE_CONFIG["period_months"]:   # the line briefs use for "same period"
            differs.append("period")
    if not differs:
        return "repeat", differs
    if differs == ["period"]:
        return "newer_wave", differs
    return "same_topic", differs


VERDICT_TEXT = {
    "repeat": "Likely repeats this study: same topic, same kind of people, same place and period",
    "newer_wave": "Same topic and people, a different period: a newer or older wave",
    "same_topic": "Same topic, different people or place",
}
DIFFERS_TEXT = {"age": "age", "segment": "segment", "place": "place", "period": "period"}


def find_overlaps(conn: psycopg.Connection, study_id: str, embedder_name: str) -> list[dict]:
    study = conn.execute(
        "select id::text as id, population, fieldwork_end from public.studies where id = %s", [study_id]).fetchone()
    if study is None:
        return []
    floor = retrieval_config(embedder_name)["min_similarity"] + OVERLAP_CONFIG["overlap_margin"]
    pairs = conn.execute(
        """
        select p.id::text as new_id, p.metric_key as new_key, p.value as new_value, p.unit as new_unit,
               n.finding_id, n.study_id, n.metric_key, n.value, n.unit, n.similarity
        from public.findings p
        cross join lateral (
          select f.id::text as finding_id, f.study_id::text as study_id, f.metric_key, f.value, f.unit,
                 1 - (f.embedding operator(extensions.<=>) p.embedding) as similarity
          from public.findings f
          join public.studies s on s.id = f.study_id
          where s.review_status = 'approved' and f.study_id <> p.study_id and f.embedding is not null
          order by f.embedding operator(extensions.<=>) p.embedding
          limit %s
        ) n
        where p.study_id = %s and p.embedding is not null
        """, [OVERLAP_CONFIG["neighbours_per_finding"], study_id]).fetchall()

    by_study: dict[str, dict] = defaultdict(lambda: {"families": set(), "matches": 0, "best": 0.0, "figures": {}})
    for r in pairs:
        same_family = family_of(r["new_key"]) and family_of(r["new_key"]) == family_of(r["metric_key"])
        if not same_family and r["similarity"] < floor:
            continue
        entry = by_study[r["study_id"]]
        entry["matches"] += 1
        entry["best"] = max(entry["best"], float(r["similarity"]))
        if same_family:
            entry["families"].add(family_of(r["new_key"]))
        # The same measure in both studies: the two figures, read from the database.
        if (r["new_key"] and r["new_key"] == r["metric_key"] and r["new_value"] is not None
                and r["value"] is not None and r["new_key"] not in entry["figures"]):
            entry["figures"][r["new_key"]] = {
                "metric": metric_label(r["new_key"]),
                "new": fmt_value(r["new_value"], r["new_unit"]), "old": fmt_value(r["value"], r["unit"])}
    if not by_study:
        return []

    others = conn.execute(
        "select s.id::text as id, s.code, s.title, s.population, s.fieldwork_end, s.effective_tier, t.name as owner_team "
        "from public.studies s join public.teams t on t.id = s.owner_team_id where s.id = any(%s::uuid[])",
        [list(by_study)]).fetchall()
    out = []
    for other in others:
        entry = by_study[other["id"]]
        verdict, differs = _compare(study, other)
        out.append({
            "study_id": other["id"], "code": other["code"], "title": other["title"], "tier": other["effective_tier"],
            "owner_team": other["owner_team"],
            "place": describe_place((other["population"] or {}).get("regions")),
            "fieldwork_end": other["fieldwork_end"].isoformat() if other["fieldwork_end"] else None,
            "topics": sorted(family_label(f) for f in entry["families"]),
            "matches": entry["matches"],
            "verdict": verdict, "verdict_text": VERDICT_TEXT[verdict],
            "differs_by": [DIFFERS_TEXT[d] for d in differs],
            "figures": list(entry["figures"].values())[:3],
        })
    rank = {"repeat": 0, "newer_wave": 1, "same_topic": 2}
    out.sort(key=lambda o: (rank[o["verdict"]], -o["matches"], o["code"]))
    return out[: OVERLAP_CONFIG["max_studies"]]
