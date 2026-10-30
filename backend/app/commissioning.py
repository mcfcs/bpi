"""'Before you commission': how far approved research already covers a set of objectives, and the
hand-off to S&I's commissioning process.

The result is structured:
    {"objectives": [{"text", "coverage": "covered" | "covered_stale" | "partial" | "gap",
                     "coverage_label", "new_problem", "newest_fieldwork", "caveats", "finding_ids"}],
     "new_problems": [...], "recommended_new_scope": "..."}

A finding counts toward an objective only when it is a strong match and shares the objective's own
concept (topicality.py), so "renew loans digitally" is not "covered" by loan drop-off studies.
Caveats flag an unresolved conflict among the matching studies and restricted studies that may
also cover the objective (metadata only).

TODO(S&I): the target system for commissioning requests and the fields it needs are not confirmed.
Until they are, NoopAdapter (store, with JSON and PDF export) is the default, and WebhookAdapter posts
the structured result unchanged to a configurable URL, for example a Power Automate HTTP trigger.
Map the result to the confirmed fields in WebhookAdapter.payload() once S&I confirms them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import httpx
import psycopg
from fpdf import FPDF
from psycopg.types.json import Jsonb

from . import audit, divergence, retrieval, topicality
from .config import COVERAGE_STATE_CONFIG, Settings, coverage_config, retrieval_config, topicality_config
from .describe import join_words, lower_label, topic_label
from .embeddings import Embedder
from .llm_types import LLM, LLMError
from .tiers import months_between
from .validators import is_ab_quant


@dataclass
class SubmissionResult:
    status: str                 # "stored" or "sent"
    detail: dict = field(default_factory=dict)


class CommissioningAdapter(Protocol):
    name: str

    def submit(self, check: dict) -> SubmissionResult: ...


class NoopAdapter:
    """Default while S&I's process is unconfirmed: the check is already stored; offer the exports."""

    name = "noop"

    def submit(self, check: dict) -> SubmissionResult:
        base = f"/api/commissioning/{check['id']}"
        return SubmissionResult("stored", {"exports": {"json": f"{base}/export.json", "pdf": f"{base}/export.pdf"}})


class WebhookAdapter:
    """POSTs the coverage result to a configured URL. Nothing about the receiving system is assumed."""

    name = "webhook"

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 10.0,
                 client: httpx.Client | None = None):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.client = client

    def payload(self, check: dict) -> dict:
        # TODO(S&I): reshape to the commissioning system's confirmed fields.
        return {
            "source": "si-evidence-assistant",
            "check_id": check["id"],
            "title": check["title"],
            "requested_by": check.get("requested_by"),
            "created_at": check.get("created_at"),
            "result": check["result"],
        }

    def submit(self, check: dict) -> SubmissionResult:
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.url, json=self.payload(check), headers=self.headers)
        finally:
            if self.client is None:
                client.close()
        response.raise_for_status()
        return SubmissionResult("sent", {"status_code": response.status_code})


def build_adapter(settings: Settings) -> CommissioningAdapter:
    if settings.commissioning_adapter == "webhook":
        if not settings.commissioning_webhook_url:
            raise RuntimeError("COMMISSIONING_ADAPTER=webhook needs COMMISSIONING_WEBHOOK_URL.")
        return WebhookAdapter(settings.commissioning_webhook_url, settings.commissioning_webhook_headers)
    return NoopAdapter()


# What each coverage state means to the requester. "gap" keeps its original code (the webhook
# contract and the current UI use it) but now reads as a genuinely new, not-yet-researched problem.
COVERAGE_LABELS = {
    "covered": "Covered: recent Tier A/B survey evidence",
    "covered_stale": "Covered, but the evidence is old",
    "partial": "Partly covered: qualitative or Tier C evidence only",
    "gap": "New problem: not yet researched",
}


def _evidence_summary(findings: list[retrieval.Source], coverage: str | None = None) -> str:
    codes = join_words(sorted({s.study_code for s in findings}))
    if not findings:
        return "no approved study found; this looks like a new problem"
    if coverage == "covered_stale":
        newest = max(s.fieldwork_end for s in findings if is_ab_quant(s) and s.fieldwork_end)
        return f"Tier A/B quantitative evidence in {codes}, but the newest fieldwork ended in {newest:%B %Y}"
    if any(is_ab_quant(s) for s in findings):
        return f"Tier A/B quantitative evidence in {codes}"
    if all(s.is_qual for s in findings):
        return f"qualitative evidence only, in {codes}; no survey measures how widespread this is"
    return f"only Tier C or partial evidence, in {codes}"


def coverage_state(findings: list[retrieval.Source], today: date) -> str:
    """covered: a relevant Tier A/B quant finding with fieldwork inside the stale window;
    covered_stale: Tier A/B quant, but all of it older than that; partial: only qualitative or
    Tier C evidence; gap: nothing relevant (a new problem)."""
    ab = [s for s in findings if is_ab_quant(s)]
    if ab:
        dated = [s.fieldwork_end for s in ab if s.fieldwork_end]
        if dated and months_between(max(dated), today) > COVERAGE_STATE_CONFIG["stale_months"]:
            return "covered_stale"
        return "covered"
    return "partial" if findings else "gap"


def assess_objectives(conn: psycopg.Connection, objectives: list[str], embedder: Embedder,
                      today: date | None = None) -> list[dict]:
    """Coverage per objective, decided in code (see coverage_state)."""
    cfg = coverage_config(embedder.name)
    bypass = topicality_config(embedder.name)["coverage_bypass_similarity"]
    today = today or date.today()
    assessed = []
    for text in objectives:
        focus = topicality.specific_terms(text)
        sources = retrieval.search(conn, text, embedder, config={
            "min_similarity": cfg["min_similarity"], "relative_floor": cfg["relative_floor"]})
        sources = [s for s in sources if not focus or topicality.overlap(text, s) or s.similarity >= bypass]
        findings = sources[: cfg["max_findings"]]
        coverage = coverage_state(findings, today)
        dated = [s.fieldwork_end for s in findings if s.fieldwork_end]
        caveats = []
        conflicts = [g for g in divergence.analyze([s.ctx() for s in findings if s.finding_type != "verbatim"])
                     if g.kind == "unresolved_conflict"]
        if conflicts:
            labels = join_words(sorted({lower_label(topic_label(g.topic)) for g in conflicts}))
            caveats.append({"code": "conflict",
                            "text": f"Studies of the same group report different results on {labels}; an S&I analyst "
                                    f"should check them before they are reused."})
        # Only catalogue metadata is visible for these, so they are a hint ("may also cover"), not evidence.
        restricted = retrieval.restricted_matches(conn, embedder.embed_query(text), retrieval_config(embedder.name),
                                                  question=text)
        if restricted:
            caveats.append({"code": "restricted_match",
                            "text": "A restricted study may also cover this ("
                                    + join_words(f"{r['code']}, {r['owner_team']}" for r in restricted)
                                    + "); request access to check it.",
                            "studies": [{k: r[k] for k in ("study_id", "code", "title", "owner_team")} for r in restricted]})
        assessed.append({
            "text": text.strip(),
            "coverage": coverage,
            "coverage_label": COVERAGE_LABELS[coverage],
            "new_problem": coverage == "gap",
            "newest_fieldwork": max(dated).isoformat() if dated else None,
            "caveats": caveats,
            "finding_ids": [s.finding_id for s in findings],
            "evidence_summary": _evidence_summary(findings, coverage),
        })
    return assessed


def run_coverage_check(conn: psycopg.Connection, user_id: str, title: str, objectives: list[str],
                       embedder: Embedder, llm: LLM, fallback_llm: LLM, today: date | None = None) -> dict:
    assessed = assess_objectives(conn, [o for o in objectives if o.strip()], embedder, today)
    try:
        scope = llm.write_scope(title, assessed)
    except LLMError:
        scope = fallback_llm.write_scope(title, assessed)
    result = {
        "objectives": [{k: o[k] for k in ("text", "coverage", "coverage_label", "new_problem", "newest_fieldwork",
                                          "caveats", "finding_ids")} for o in assessed],
        "new_problems": [o["text"] for o in assessed if o["new_problem"]],
        "recommended_new_scope": scope,
    }
    row = conn.execute(
        "insert into public.commissioning_checks (created_by, title, objectives, result) values (%s, %s, %s, %s) "
        "returning id::text as id, created_at",
        [user_id, title.strip(), [o["text"] for o in assessed], Jsonb(result)],
    ).fetchone()
    audit.log(conn, "commissioning.checked", "commissioning_check", row["id"], {
        "coverage": [o["coverage"] for o in assessed]})
    return {"id": row["id"], "title": title.strip(), "created_at": row["created_at"].isoformat(), "result": result,
            "evidence_summaries": [o["evidence_summary"] for o in assessed]}


def load_check(conn: psycopg.Connection, check_id: str) -> dict | None:
    row = conn.execute(
        "select c.id::text as id, c.title, c.result, c.adapter, c.submission, c.submitted_at, c.created_at, "
        "p.display_name as requested_by from public.commissioning_checks c "
        "join public.profiles p on p.id = c.created_by where c.id = %s", [check_id],
    ).fetchone()
    if row is None:
        return None
    return {**row, "created_at": row["created_at"].isoformat(),
            "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None}


def existing_submission(check: dict) -> dict | None:
    """A check is handed over once. Submitting again returns the first hand-off unchanged."""
    if not check.get("submitted_at"):
        return None
    return {"adapter": check.get("adapter"), **(check.get("submission") or {}),
            "submitted_at": check["submitted_at"], "already_submitted": True}


RESTRICTED_NOTICE = "Restricted - {owner}; share only within approved teams."


def access_note(finding: dict) -> str | None:
    if finding.get("access_level") == "restricted":
        return RESTRICTED_NOTICE.format(owner=finding.get("owner_team") or "owning team")
    return None


def export_json(check: dict, findings: dict[str, dict]) -> dict:
    """The JSON export: the result plus each cited finding the reader can see, labelled with its
    access level and owner, so restricted content is marked wherever the file goes."""
    cited = sorted({fid for o in check["result"]["objectives"] for fid in o["finding_ids"]})
    rows = [{"finding_id": fid, "study_code": findings[fid]["study_code"], "owner_team": findings[fid]["owner_team"],
             "access_level": findings[fid].get("access_level"), "access_note": access_note(findings[fid]),
             "text": findings[fid]["text"]} for fid in cited if fid in findings]
    out = {"id": check["id"], "title": check["title"], "created_at": check["created_at"], **check["result"],
           "findings": rows}
    if any(r["access_note"] for r in rows):
        out["notice"] = "Contains restricted findings. Share only within the teams approved to read them."
    return out


def record_submission(conn: psycopg.Connection, check: dict, adapter: CommissioningAdapter,
                      outcome: SubmissionResult) -> dict:
    """Store how the check was handed over. The adapter call itself happens outside any database
    transaction, so a slow or failing receiver never holds a connection."""
    conn.execute(
        "update public.commissioning_checks set adapter = %s, submission = %s, submitted_at = now() where id = %s",
        [adapter.name, Jsonb({"status": outcome.status, **outcome.detail}), check["id"]],
    )
    audit.log(conn, "commissioning.submitted", "commissioning_check", check["id"],
              {"adapter": adapter.name, "status": outcome.status})
    return {"adapter": adapter.name, "status": outcome.status, **outcome.detail}


def _latin1(text: str) -> str:
    replacements = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def export_pdf(check: dict, findings: dict[str, dict]) -> bytes:
    """A plain, memo-style PDF of the coverage check. Findings the reader cannot see are omitted."""
    pdf = FPDF(format="A4")
    pdf.set_margins(22, 20, 22)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def para(text: str, size: float = 10.5, style: str = "", height: float = 5.4, family: str = "Times") -> None:
        pdf.set_font(family, style, size)
        pdf.multi_cell(width, height, _latin1(text), new_x="LMARGIN", new_y="NEXT")

    para("Before you commission: coverage check", 9, family="Helvetica")
    para(check["title"], 17, "B", 8)
    para(f"Requested by {check.get('requested_by', '')} on {check['created_at'][:10]}. Check {check['id']}.", 9.5)
    pdf.ln(4)
    for objective in check["result"]["objectives"]:
        para(f"{objective['coverage'].upper()}  {objective['text']}", 11.5, "B", 6)
        for fid in objective["finding_ids"]:
            f = findings.get(fid)
            if f:
                para(f"{f['study_code']}  Tier {f['tier'] or '-'}  {f.get('method_detail') or f['method_type'] or ''}  ",
                     8.5, family="Courier", height=4.6)
                if access_note(f):
                    para(access_note(f), 8.5, "B", family="Helvetica", height=4.6)
                para(f["text"], 10, height=5)
        for caveat in objective.get("caveats") or []:
            para(caveat["text"], 9.5, "I", height=5)
        if not objective["finding_ids"]:
            para("No approved study covers this objective.", 10, "I")
        pdf.ln(3)
    para("Recommended new scope", 12.5, "B", 7)
    para(check["result"]["recommended_new_scope"])
    pdf.ln(4)
    if any(access_note(f) for f in findings.values()):
        para("Contains restricted findings. Share only within the teams approved to read them.", 8.5, "B")
    para("Synthetic demonstration data. Generated by the S&I evidence assistant.", 8, "I")
    return bytes(pdf.output())
