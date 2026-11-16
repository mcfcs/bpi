"""Research-gap map for S&I: what the approved research covers, where, and what people ask about.

Rows are topic families (the metric family of a finding: "barrier:documents" belongs to "barrier");
columns are the kind of place a finding speaks for (Metro Manila, provincial, rural, nationwide).
Each cell gets the same coverage state as a "Before you commission" check, decided in code by the
same rule (commissioning.coverage_state): covered, covered but old, partial, or gap.

Next to each row is demand: how many briefs in the window cited that family, and from how many
teams. A family that is asked about often and only partly covered is where new research would be
used. The map is built from what the signed-in S&I analyst can read (RLS); studies restricted from
S&I are counted, not opened.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import psycopg

from . import geography
from .commissioning import coverage_state
from .config import FAMILY_LABELS, GAP_AREAS, GAP_COLUMNS, GAP_CONFIG

STATE_RANK = {"covered": 3, "covered_stale": 2, "partial": 1, "gap": 0}


def family_of(metric_key: str | None, theme: str | None = None) -> str | None:
    """"barrier:documents" -> "barrier"; "literacy_trend:x" -> "literacy". Findings without a metric
    key fall back to their theme."""
    key = metric_key or (f"{theme}:" if theme else None)
    if not key:
        return None
    family = key.split(":", 1)[0]
    return family[: -len("_trend")] if family.endswith("_trend") else family


def family_label(family: str) -> str:
    return FAMILY_LABELS.get(family, family.replace("_", " ").capitalize())


def _areas(population: dict | None, subgroup: dict | None) -> tuple[str, ...]:
    regions = [subgroup["region"]] if subgroup and subgroup.get("region") else (population or {}).get("regions")
    kind = geography.area_type(regions)
    return GAP_AREAS.get(kind, ()) if kind else ()


def gap_map(conn: psycopg.Connection, today: date, days: int = 90) -> dict:
    rows = conn.execute(
        """
        select f.metric_key, f.theme, f.finding_type, f.subgroup, s.id::text as study_id, s.code, s.method_type,
               s.fieldwork_end, s.population, s.effective_tier
        from public.findings f
        join public.studies s on s.id = f.study_id
        where s.review_status = 'approved'
        """).fetchall()

    by_cell: dict[tuple[str, str], list] = defaultdict(list)
    studies: dict[str, set[str]] = defaultdict(set)
    newest: dict[str, date] = {}
    for r in rows:
        family = family_of(r["metric_key"], r["theme"])
        if not family:
            continue
        evidence = SimpleNamespace(
            is_quant=r["method_type"] == "quant" or (r["method_type"] == "mixed" and r["finding_type"] == "quant_stat"),
            effective_tier=r["effective_tier"], fieldwork_end=r["fieldwork_end"])
        studies[family].add(r["code"])
        if r["fieldwork_end"] and (family not in newest or r["fieldwork_end"] > newest[family]):
            newest[family] = r["fieldwork_end"]
        for area in _areas(r["population"], r["subgroup"]):
            by_cell[(family, area)].append(evidence)

    demand, teams = _demand(conn, days)
    unanswered = _unanswered(conn, days)
    unanswered_by_family = Counter(u["family"] for u in unanswered if u["family"])
    for u in unanswered:
        if u["family"]:
            teams[u["family"]].add(u["team"])
    families = sorted(set(studies) | set(demand) | set(unanswered_by_family),
                      key=lambda f: (-(demand.get(f, 0) + unanswered_by_family.get(f, 0)), family_label(f)))
    out_rows = []
    for family in families:
        cells = {area: coverage_state(by_cell.get((family, area), []), today) for area in GAP_COLUMNS}
        best = max(cells.values(), key=STATE_RANK.__getitem__)
        weak = [a for a, state in cells.items() if state in ("gap", "partial", "covered_stale")]
        out_rows.append({
            "family": family,
            "label": family_label(family),
            "cells": cells,
            "best": best,
            "studies": sorted(studies.get(family, ())),
            "newest_fieldwork": newest[family].isoformat() if family in newest else None,
            "asked": demand.get(family, 0),
            "unanswered": unanswered_by_family.get(family, 0),
            "teams": sorted(teams.get(family, ())),
            # Asked about (answered or not), and somewhere still weak: where new research would be used first.
            "attention": bool(demand.get(family) or unanswered_by_family.get(family))
                         and (best != "covered" or len(weak) >= 2 or bool(unanswered_by_family.get(family))),
        })

    readable = conn.execute("select count(*)::int as n from public.studies where review_status = 'approved'").fetchone()["n"]
    return {
        "columns": list(GAP_COLUMNS),
        "rows": out_rows,
        "days": days,
        "studies_read": readable,
        "unanswered": [{k: v for k, v in u.items() if k != "family"} | {"topic": family_label(u["family"]) if u["family"] else None}
                       for u in unanswered],
    }


def _demand(conn: psycopg.Connection, days: int) -> tuple[Counter, dict[str, set[str]]]:
    """Briefs in the window that cited each family, and which teams asked them."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    briefs = conn.execute(
        """
        select b.payload -> 'sources' as sources, t.name as team
        from public.briefs b
        join public.profiles p on p.id = b.user_id
        join public.teams t on t.id = p.team_id
        where b.created_at >= %s
        """, [since]).fetchall()
    counts: Counter = Counter()
    teams: dict[str, set[str]] = defaultdict(set)
    for b in briefs:
        families = {family_of(s.get("metric_key"), s.get("theme")) for s in (b["sources"] or {}).values()}
        for family in families - {None}:
            counts[family] += 1
            teams[family].add(b["team"])
    return counts, teams


def _unanswered(conn: psycopg.Connection, days: int) -> list[dict]:
    """Questions no readable study answered, each placed on the topic most common among its nearest
    approved findings (by the question's stored embedding). That is the topic the question is closest
    to, not one that answers it: it tells S&I where unanswered demand sits in the grid."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = conn.execute(
        """
        select q.question, q.team, q.last_asked, q.times,
               (select array_agg(n.family) from (
                  select split_part(coalesce(f.metric_key, 'theme:' || f.theme), ':', 1) as family
                  from public.findings f join public.studies s on s.id = f.study_id
                  where s.review_status = 'approved' and f.embedding is not null and q.embedding is not null
                  order by f.embedding operator(extensions.<=>) q.embedding limit %s) n) as near
        from (
          select b.question, t.name as team, max(b.created_at) as last_asked, count(*)::int as times,
                 (array_agg(b.question_embedding order by b.created_at desc))[1] as embedding
          from public.briefs b
          join public.profiles p on p.id = b.user_id
          join public.teams t on t.id = p.team_id
          where b.created_at >= %s and coalesce(cardinality(b.retrieved_finding_ids), 0) = 0
          group by b.question, t.name
        ) q
        order by q.last_asked desc
        limit 12
        """, [GAP_CONFIG["nearest_findings"], since]).fetchall()
    out = []
    for r in rows:
        near = [family_of(f + ":") for f in (r["near"] or []) if f]
        family = Counter(near).most_common(1)[0][0] if near else None
        out.append({"question": r["question"], "team": r["team"], "last_asked": r["last_asked"].isoformat(),
                    "times": r["times"], "family": family})
    return out
