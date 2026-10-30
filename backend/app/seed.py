"""Load the synthetic corpus: teams, demo personas, approved studies and their findings, and raw
reports sent through the ingestion pipeline so they wait in the S&I review queue.

Every corpus study also gets a generated report PDF (app/report_pdf.py) stored with it, and each
finding records the page it is on. The report specs in data/synthetic/report_pdfs/ are rendered to
PDFs and go through PDF ingestion, so reviewers see real documents in the queue. With
`include_public=True`, public third-party reports whose PDFs have been downloaded are added as
approved, open studies labelled "Public source" (app/public_sources.py).

All BPI-style data here is synthetic. Do not load real BPI data with this module.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date

import psycopg

from . import documents, public_sources
from .config import REPO_DIR
from .db import Database
from .embeddings import Embedder, HashingEmbedder
from .ingestion import ingest_report, store_study_card
from .llm import OfflineLLM
from .llm_types import LLM
from .report_pdf import render_study_report
from .schemas import ExtractedFinding, ExtractedPopulation, ExtractedSubgroup, StudyCardExtraction

DATA_DIR = REPO_DIR / "data" / "synthetic"
PERSONA_NAMESPACE = uuid.UUID("6f2b8a40-58c1-4d4e-9a3e-5a1a3b7f0c11")
SYNTHETIC_LICENSE = "Synthetic demonstration data generated for the prototype; not real BPI data."


def persona_id(email: str) -> str:
    return str(uuid.uuid5(PERSONA_NAMESPACE, email))


def _card(study: dict) -> StudyCardExtraction:
    findings = []
    for f in study["findings"]:
        sub = f.get("subgroup")
        findings.append(ExtractedFinding(
            text=f["text"],
            finding_type=f["finding_type"],
            theme=f.get("theme", study.get("theme")),
            metric_key=f.get("metric_key"),
            value=f.get("value"),
            unit=f.get("unit"),
            base_n=f.get("base_n"),
            subgroup=ExtractedSubgroup(**{"age_band": None, "region": None, "segment": None, **sub}) if sub else None,
            direction=f.get("direction"),
        ))
    return StudyCardExtraction(
        title=study["title"],
        summary=study["summary"],
        method_type=study["method_type"],
        sample_size=study["sample_size"],
        fieldwork_end=study["fieldwork_end"],
        population=ExtractedPopulation(**study["population"]),
        findings=findings,
    )


def seed(db: Database, today: date, *, llm: LLM | None = None, embedder: Embedder | None = None,
         include_reports: bool = True, include_public: bool = False) -> dict:
    corpus = json.loads((DATA_DIR / "corpus.json").read_text(encoding="utf-8"))
    embedder = embedder or HashingEmbedder()
    teams: dict[str, str] = {}
    people: dict[str, str] = {}
    studies: dict[str, str] = {}

    with db.as_service() as conn:
        for team in corpus["teams"]:
            teams[team["name"]] = conn.execute(
                "insert into public.teams (name, kind) values (%s, %s) "
                "on conflict (name) do update set kind = excluded.kind returning id::text as id",
                [team["name"], team["kind"]],
            ).fetchone()["id"]
        for p in corpus["personas"]:
            uid = persona_id(p["email"])
            conn.execute("insert into auth.users (id, email) values (%s, %s) on conflict (id) do nothing", [uid, p["email"]])
            conn.execute(
                "insert into public.profiles (id, email, display_name, team_id, role) values (%s, %s, %s, %s, %s) "
                "on conflict (id) do update set display_name = excluded.display_name, team_id = excluded.team_id, "
                "role = excluded.role",
                [uid, p["email"], p["display_name"], teams[p["team"]], p["role"]],
            )
            people[p["email"]] = uid
        analyst = next(people[p["email"]] for p in corpus["personas"] if p["role"] == "si_analyst")

        for study in corpus["studies"]:
            report = render_study_report(study)
            existing = conn.execute("select id::text as id from public.studies where code = %s", [study["code"]]).fetchone()
            if existing:
                studies[study["code"]] = existing["id"]
                # Databases seeded before documents existed, or before the generator changed: label the
                # study and pin its findings to the pages of the report stored below.
                conn.execute("update public.studies set provenance = 'synthetic' where id = %s", [existing["id"]])
                documents.set_finding_pages(conn, existing["id"], dict(enumerate(report.pages)))
            else:
                studies[study["code"]] = store_study_card(
                    conn, _card(study), owner_team_id=teams[study["owner_team"]], access_level=study["access_level"],
                    embedder=embedder, today=today, created_by=analyst, code=study["code"],
                    source_name=report.filename, review_status="approved", reviewed_by=analyst,
                    provenance="synthetic", finding_pages=report.pages,
                )
            documents.store_document(conn, studies[study["code"]], report.pdf, filename=report.filename,
                                     source_kind="synthetic", page_count=report.page_count, license=SYNTHETIC_LICENSE)

        public = seed_public_reports(conn, teams["Strategy & Insights"], analyst, embedder, today) if include_public else []

    pending: list[str] = []
    if include_reports:
        llm = llm or OfflineLLM()
        for path in sorted((DATA_DIR / "reports").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            owner = re.search(r"^Commissioned by:\s*(.+)$", text, re.MULTILINE)
            access = re.search(r"^Access:\s*(open|restricted)\s*$", text, re.MULTILINE)
            with db.as_user(analyst) as conn:
                if conn.execute("select 1 from public.studies where source_name = %s", [path.name]).fetchone():
                    continue
                pending.append(ingest_report(
                    conn, llm, embedder, report_text=text,
                    owner_team_id=teams.get(owner.group(1).strip() if owner else "", teams["Strategy & Insights"]),
                    access_level=access.group(1) if access else "restricted",
                    source_name=path.name, user_id=analyst, today=today, provenance="synthetic",
                ))
        for path in sorted((DATA_DIR / "report_pdfs").glob("*.json")):
            spec = json.loads(path.read_text(encoding="utf-8"))
            report = render_study_report(spec)
            with db.as_user(analyst) as conn:
                if conn.execute("select 1 from public.studies where source_name = %s", [report.filename]).fetchone():
                    continue
                pending.append(documents.ingest_pdf(
                    conn, llm, embedder, data=report.pdf, filename=report.filename,
                    owner_team_id=teams.get(spec.get("owner_team", ""), teams["Strategy & Insights"]),
                    access_level=spec.get("access_level", "restricted"), user_id=analyst, today=today,
                    source_kind="synthetic", provenance="synthetic", license=SYNTHETIC_LICENSE,
                ).study_id)
    return {"teams": teams, "people": people, "studies": studies, "pending": pending, "public": public}


def seed_public_reports(conn: psycopg.Connection, owner_team_id: str, analyst: str, embedder: Embedder,
                        today: date) -> list[str]:
    """Approved, open "Public source" studies for each public report whose PDF has been downloaded
    and whose card has been written. Reports without a local PDF are skipped, never fetched here."""
    codes: list[str] = []
    for report in public_sources.load_reports():
        if not report.card or not report.available:
            continue
        card, entry = report.card, report.entry
        existing = conn.execute("select id::text as id from public.studies where code = %s", [card["code"]]).fetchone()
        if existing:
            study_id = existing["id"]
        else:
            pages, quotes = public_sources.card_pages(card)
            study_id = store_study_card(
                conn, public_sources.card_to_extraction(card), owner_team_id=owner_team_id, access_level="open",
                embedder=embedder, today=today, created_by=analyst, code=card["code"],
                source_name=f"{report.slug}.pdf", review_status="approved", reviewed_by=analyst,
                provenance="public", publisher=entry["publisher"], finding_pages=pages, finding_excerpts=quotes,
            )
        documents.store_document(conn, study_id, report.pdf_path.read_bytes(), filename=f"{report.slug}.pdf",
                                 source_kind="public", page_count=entry.get("pages"), source_url=entry["url"],
                                 license=entry["license"])
        codes.append(card["code"])
    return codes
