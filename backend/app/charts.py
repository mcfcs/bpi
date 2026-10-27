"""Chart specs built server-side from quant_stat findings.

Numbers come from the database, never from the LLM: the LLM only picks which metric_keys to chart
from the list it is given. Queries run as the caller, so RLS limits the bars to studies they may
read. Qualitative studies are never charted.
"""

from __future__ import annotations

from collections import Counter

import psycopg

from . import geography
from .config import CHART_CONFIG, chart_title
from .describe import age_phrase, subgroup_label

POINTS_SQL = """
    select f.id::text as finding_id, f.metric_key, f.value, f.unit, f.base_n, f.subgroup,
           s.id::text as study_id, s.code as study_code, s.title as study_title, s.effective_tier,
           s.fieldwork_end, s.population, s.sample_size, s.method_type
    from public.findings f
    join public.studies s on s.id = f.study_id
    where f.finding_type = 'quant_stat'
      and f.value is not null
      and f.metric_key = any(%s)
      and s.review_status = 'approved'
      and s.method_type in ('quant', 'mixed')
    order by f.metric_key, s.code, f.ordinal
"""


def load_points(conn: psycopg.Connection, metric_keys: set[str] | list[str]) -> dict[str, list[dict]]:
    """Readable quant_stat rows per metric. When a study reports a metric by subgroup, its subgroup
    rows are charted and its total is left out, so no study is counted twice."""
    if not metric_keys:
        return {}
    grouped: dict[str, list[dict]] = {}
    for row in conn.execute(POINTS_SQL, [sorted(metric_keys)]).fetchall():
        grouped.setdefault(row["metric_key"], []).append(row)
    points = {}
    for key, rows in grouped.items():
        with_breakdown = {r["study_id"] for r in rows if r["subgroup"]}
        points[key] = [r for r in rows if r["subgroup"] or r["study_id"] not in with_breakdown]
    return points


def _bar_label(row: dict) -> str:
    if row["subgroup"]:
        return subgroup_label(row["subgroup"])
    pop = row["population"] or {}
    age = age_phrase(pop.get("age_min"), pop.get("age_max")).replace("aged ", "Ages ")
    return ", ".join(p for p in (age, geography.describe(pop.get("regions"))) if p)


def build_chart(metric_key: str, rows: list[dict]) -> dict | None:
    """Horizontal bar chart spec, one bar per subgroup or study, sorted by value. None when fewer
    than CHART_CONFIG["min_points"] comparable points exist."""
    rows = [r for r in rows if r["unit"] in CHART_CONFIG["units"]]
    if not rows:
        return None
    unit = Counter(r["unit"] for r in rows).most_common(1)[0][0]
    rows = [r for r in rows if r["unit"] == unit]
    if len(rows) < CHART_CONFIG["min_points"]:
        return None
    bars = [
        {
            "finding_id": r["finding_id"],
            "study_id": r["study_id"],
            "study_code": r["study_code"],
            "label": _bar_label(r),
            "detail": f"{r['study_code']} · {r['fieldwork_end'].year}" if r["fieldwork_end"] else r["study_code"],
            "value": float(r["value"]),
            "unit": unit,
            "base_n": r["base_n"] or r["sample_size"],
            "tier": r["effective_tier"],
            "study_title": r["study_title"],
            "sample_size": r["sample_size"],
            "method_type": r["method_type"],
            "region_label": geography.describe((r["population"] or {}).get("regions")),
            "fieldwork_end": r["fieldwork_end"].isoformat() if r["fieldwork_end"] else None,
        }
        for r in rows
    ]
    bars.sort(key=lambda b: b["value"], reverse=True)
    return {"metric_key": metric_key, "title": chart_title(metric_key), "unit": unit, "bars": bars}
