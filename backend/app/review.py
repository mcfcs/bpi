"""S&I study-card review (checkpoint 1) and tier recomputation.

Analysts check and edit what extraction filled in, including method, sample size, fieldwork end and
population, and may override the computed robustness tier with a reason. The tier is recomputed in
code whenever method, sample size or fieldwork end changes. Override changes are audited by a
database trigger; other edits are audited here.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from . import audit, privacy
from .embeddings import Embedder, to_pgvector
from .schemas import FindingPatch, StudyPatch
from .tiers import compute_tier_or_none, tier_breakdown

STUDY_COLUMNS = """
    s.id::text as id, s.code, s.title, s.summary, s.owner_team_id::text as owner_team_id,
    t.name as owner_team, s.access_level, s.review_status, s.source_name, s.created_at,
    s.reviewed_at, s.review_note, s.method_type, s.sample_size, s.fieldwork_end, s.population,
    s.robustness_tier, s.tier_override, s.tier_override_reason, s.effective_tier, s.tier_computed_at
"""

FINDING_COLUMNS = """
    id::text as id, ordinal, text, theme, finding_type, metric_key, value, unit, base_n, subgroup, direction
"""


class ReviewError(ValueError):
    """A review edit that breaks a rule (for example an override without a reason)."""


def _jsonable(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value.__class__.__name__ == "Decimal":
            value = float(value)
        out[key] = value
    return out


def study_detail(conn: psycopg.Connection, study_id: str, today: date) -> dict | None:
    row = conn.execute(
        f"select {STUDY_COLUMNS}, s.source_text from public.studies s join public.teams t on t.id = s.owner_team_id "
        "where s.id = %s",
        [study_id],
    ).fetchone()
    if row is None:
        return None
    findings = conn.execute(
        f"select {FINDING_COLUMNS} from public.findings where study_id = %s order by ordinal", [study_id]
    ).fetchall()
    breakdown = None
    if row["method_type"] and row["fieldwork_end"]:
        breakdown = tier_breakdown(row["method_type"], row["sample_size"], row["fieldwork_end"], today)
    return {**_jsonable(row), "tier_breakdown": breakdown, "findings": [_jsonable(f) for f in findings]}


def review_queue(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        f"select {STUDY_COLUMNS}, (select count(*) from public.findings f where f.study_id = s.id) as finding_count "
        "from public.studies s join public.teams t on t.id = s.owner_team_id "
        "where s.review_status = 'pending_review' order by s.created_at"
    ).fetchall()
    return [_jsonable(r) for r in rows]


def update_study(conn: psycopg.Connection, study_id: str, patch: StudyPatch, today: date) -> dict:
    current = conn.execute(
        "select method_type, sample_size, fieldwork_end, robustness_tier, tier_override, tier_override_reason "
        "from public.studies where id = %s for update", [study_id],
    ).fetchone()
    if current is None:
        raise LookupError("study not found")

    changes: dict = {}
    for field in ("title", "summary", "access_level", "method_type", "sample_size", "fieldwork_end"):
        value = getattr(patch, field)
        if value is not None:
            changes[field] = value
    if patch.population is not None:
        changes["population"] = Jsonb(patch.population.model_dump())

    if patch.clear_tier_override:
        changes["tier_override"] = None
        changes["tier_override_reason"] = None
    elif patch.tier_override is not None:
        reason = (patch.tier_override_reason or "").strip()
        if not reason:
            raise ReviewError("A tier override needs a reason.")
        changes["tier_override"] = patch.tier_override
        changes["tier_override_reason"] = reason

    merged = {**current, **{k: v for k, v in changes.items() if k in current}}
    new_tier = compute_tier_or_none(merged["method_type"], merged["sample_size"], merged["fieldwork_end"], today)
    if new_tier != current["robustness_tier"] or any(k in changes for k in ("method_type", "sample_size", "fieldwork_end")):
        changes["robustness_tier"] = new_tier
        changes["tier_computed_at"] = today

    if changes:
        assignments = ", ".join(f"{column} = %s" for column in changes)
        conn.execute(f"update public.studies set {assignments} where id = %s", [*changes.values(), study_id])
        logged = {k: (v.obj if isinstance(v, Jsonb) else v) for k, v in changes.items()
                  if k not in ("tier_override", "tier_override_reason", "tier_computed_at")}
        audit.log(conn, "study.updated", "study", study_id, {k: str(v) if hasattr(v, "isoformat") else v for k, v in logged.items()})
        if "robustness_tier" in changes and changes["robustness_tier"] != current["robustness_tier"]:
            audit.log(conn, "study.tier_recomputed", "study", study_id,
                      {"from": current["robustness_tier"], "to": changes["robustness_tier"], "trigger": "review_edit"})
    return study_detail(conn, study_id, today)


def update_finding(conn: psycopg.Connection, finding_id: str, patch: FindingPatch, embedder: Embedder) -> dict:
    current = conn.execute(
        "select f.study_id::text as study_id, f.text, f.theme, s.title from public.findings f "
        "join public.studies s on s.id = f.study_id where f.id = %s for update of f", [finding_id],
    ).fetchone()
    if current is None:
        raise LookupError("finding not found")
    changes = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}
    if "subgroup" in changes:
        changes["subgroup"] = Jsonb(changes["subgroup"]) if changes["subgroup"] else None
    if changes.get("finding_type", "quant_stat") != "quant_stat" and changes.get("value") is not None:
        raise ReviewError("Only quant_stat findings can carry a value.")
    if "text" in changes or "theme" in changes:
        text = changes.get("text", current["text"])
        theme = changes.get("theme", current["theme"])
        changes["embedding"] = to_pgvector(embedder.embed(embedding_text(current["title"], theme, text)))
    if changes:
        assignments = ", ".join(
            f"{c} = %s::extensions.vector" if c == "embedding" else f"{c} = %s" for c in changes
        )
        conn.execute(f"update public.findings set {assignments} where id = %s", [*changes.values(), finding_id])
        audit.log(conn, "finding.updated", "finding", finding_id,
                  {"study_id": current["study_id"], "fields": sorted(k for k in changes if k != "embedding")})
    row = conn.execute(f"select {FINDING_COLUMNS} from public.findings where id = %s", [finding_id]).fetchone()
    return _jsonable(row)


def decide_study(conn: psycopg.Connection, study_id: str, approve: bool, note: str | None, user_id: str,
                 privacy_checked: bool = False) -> None:
    study = conn.execute(
        "select review_status, method_type, fieldwork_end, robustness_tier from public.studies where id = %s for update",
        [study_id],
    ).fetchone()
    if study is None:
        raise LookupError("study not found")
    if approve:
        missing = [f for f in ("method_type", "fieldwork_end") if study[f] is None]
        if missing:
            raise ReviewError(f"Fill in {', '.join(missing)} before approving.")
        untyped = conn.execute(
            "select count(*) as n from public.findings where study_id = %s and finding_type is null", [study_id]
        ).fetchone()["n"]
        if untyped:
            raise ReviewError(f"{untyped} finding(s) have no finding type.")
        flagged = privacy.study_flags(conn, study_id)["findings"]
        if flagged and not privacy_checked:
            kinds = sorted({m["label"].lower() for f in flagged for m in f["matches"]})
            raise ReviewError(f"{len(flagged)} finding(s) may contain personal data ({', '.join(kinds)}). "
                              "Edit them, or confirm you checked that they identify no one.")
    else:
        flagged = []
    conn.execute(
        "update public.studies set review_status = %s, reviewed_by = %s, reviewed_at = now(), review_note = %s where id = %s",
        ["approved" if approve else "rejected", user_id, note, study_id],
    )
    audit.log(conn, "study.approved" if approve else "study.rejected", "study", study_id,
              {"note": note, "tier": study["robustness_tier"],
               **({"privacy_flags": len(flagged), "privacy_checked": True} if flagged else {})})


def embedding_text(study_title: str | None, theme: str | None, text: str) -> str:
    """What gets embedded for a finding: its text with the study title and theme for context."""
    return ". ".join(p for p in (study_title, (theme or "").replace("_", " "), text) if p)
