"""Study documents: report PDFs follow RLS, findings carry page numbers, PDF ingestion works end to
end, and the catalogue shows restricted studies as metadata only."""

from __future__ import annotations

import json

import psycopg
import pytest
from pypdf import PdfWriter

from app import documents
from app.config import REPO_DIR
from app.documents import extract_pdf, locate_page, normalise_report_text
from app.offline_extract import extract
from app.report_pdf import SYNTHETIC_NOTICE, render_study_report
from tests.conftest import SME_QUESTION, auth

CORPUS = json.loads((REPO_DIR / "data" / "synthetic" / "corpus.json").read_text(encoding="utf-8"))
STUDY = {s["code"]: s for s in CORPUS["studies"]}

NEW_REPORT = {
    "title": "Payroll Account Switching Survey 2026",
    "summary": "A survey of salaried employees in Metro Manila and Cebu about moving their payroll account.",
    "owner_team": "SME Banking",
    "access_level": "open",
    "method_type": "quant",
    "sample_size": 1500,
    "fieldwork_start": "2026-07-01",
    "fieldwork_end": "2026-07-29",
    "population": {"age_min": 22, "age_max": 55, "regions": ["NCR", "Cebu"], "segment": "Salaried employees"},
    "findings": [
        {"text": "34% of employees said they would move their payroll account for faster salary credit (base n=1,500).",
         "finding_type": "quant_stat", "metric_key": "payroll:switch_speed", "value": 34, "unit": "%", "base_n": 1500},
        {"text": "Being asked for documents again was cited by 41% of employees who tried to switch (base n=620).",
         "finding_type": "quant_stat", "metric_key": "barrier:documents", "value": 41, "unit": "%", "base_n": 620},
        {"text": "Among employees aged 22-29, 47% said they would switch for faster salary credit (base n=410).",
         "finding_type": "quant_stat", "metric_key": "payroll:switch_speed", "value": 47, "unit": "%", "base_n": 410,
         "subgroup": {"age_band": "22-29"}},
    ],
}


def _download(client, study_id: str, who: str):
    return client.get(f"/api/studies/{study_id}/document", headers=auth(client, who))


# --------------------------------------------------------------------------- generator and page mapping

def test_generated_report_is_multi_page_labelled_and_deterministic():
    study = STUDY["SI-2026-014"]
    first, second = render_study_report(study), render_study_report(study)
    assert first.pdf == second.pdf                       # same bytes, same sha256, on every seed
    extracted = extract_pdf(first.pdf)
    assert extracted.page_count == first.page_count >= 4
    assert all(SYNTHETIC_NOTICE in page for page in extracted.pages)
    for finding, page in zip(study["findings"], first.pages):
        assert locate_page(finding["text"], extracted.pages)[0] == page


def test_generated_reports_read_back_through_the_offline_extractor():
    for code in ("SI-2026-014", "SI-2025-031"):
        study = STUDY[code]
        extracted = extract_pdf(render_study_report(study).pdf)
        card = extract(normalise_report_text(extracted))
        assert (card.method_type, card.sample_size, card.fieldwork_end) == (
            study["method_type"], study["sample_size"], study["fieldwork_end"])
        assert [f.text for f in card.findings] == [f["text"] for f in study["findings"]]


def test_offline_extractor_falls_back_to_prose_for_study_details():
    """Real reports have no labelled details block; the card fields come from explicit sentences."""
    prose = ("# Household Finance Survey\n\nThis nationally representative survey of adults covers accounts and "
             "loans. The survey has a sample size of 1,200 adults aged 15 and above, selected by random sampling "
             "from respondents in all regions. The survey was conducted from 13 January to 9 February 2022, "
             "with 2021 as reference year. A questionnaire was administered face to face.\n")
    card = extract(prose)
    assert (card.method_type, card.sample_size, card.fieldwork_end) == ("quant", 1200, "2022-02-09")
    assert card.population.regions == ["Nationwide"]
    vague = extract("# Notes\n\nSome notes about loans without a method or dates.\n")
    assert (vague.method_type, vague.sample_size, vague.fieldwork_end) == (None, None, None)


def test_locate_page_handles_split_words_and_refuses_weak_matches():
    pages = ["Intro text about nothing in particular.",
             "Outside NCR, s ome women admitted keeping money aside at home for emergencies.",
             "Outside NCR, some women admitted keeping money aside at home for emergencies."]
    assert locate_page("Outside NCR, some women admitted keeping money aside at home", pages) == (2, 1.0)
    page, score = locate_page("Fees ranked first among reasons for closing a credit card account", pages)
    assert page is None and score < 0.6


def test_seeded_findings_carry_the_page_they_appear_on(db, study_ids):
    report = render_study_report(STUDY["SI-2026-014"])
    with db.as_service() as conn:
        rows = conn.execute("select ordinal, page from public.findings where study_id = %s order by ordinal",
                            [study_ids["SI-2026-014"]]).fetchall()
        doc = conn.execute("select page_count, sha256, source_kind from public.study_documents where study_id = %s",
                           [study_ids["SI-2026-014"]]).fetchone()
    assert [r["page"] for r in rows] == report.pages
    assert doc["page_count"] == report.page_count and doc["source_kind"] == "synthetic"
    assert doc["sha256"] == documents.sha256(report.pdf)


# --------------------------------------------------------------------------- RLS on documents

def test_restricted_report_is_downloadable_only_with_access(client, db, people, study_ids):
    study = study_ids["SI-2026-014"]   # SME Banking, restricted
    assert _download(client, study, "carla").status_code == 404
    for who in ("ana", "ben"):
        response = _download(client, study, who)
        assert response.status_code == 200, who
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
    with db.as_user(people["carla"].id) as conn:
        assert conn.execute("select count(*) as n from public.study_documents where study_id = %s",
                            [study]).fetchone()["n"] == 0
    with db.as_service() as conn:
        rows = conn.execute("select actor_id::text as actor, details from public.audit_log "
                            "where action = 'document.downloaded' and entity_id = %s", [study]).fetchall()
    assert {r["actor"] for r in rows} == {people["ana"].id, people["ben"].id}   # denied attempts download nothing


def test_open_reports_are_downloadable_by_any_team(client, study_ids):
    assert _download(client, study_ids["SI-2025-031"], "carla").status_code == 200


def test_documents_of_pending_studies_are_for_si_only(client, db, people):
    with db.as_service() as conn:
        pending = conn.execute(
            "select s.id::text as id from public.studies s join public.teams t on t.id = s.owner_team_id "
            "where s.review_status = 'pending_review' and t.name = 'SME Banking' "
            "and exists (select 1 from public.study_documents d where d.study_id = s.id)").fetchone()["id"]
    assert _download(client, pending, "ben").status_code == 404     # the owning team waits for S&I review
    assert _download(client, pending, "ana").status_code == 200


def test_documents_cannot_be_written_by_business_units(db, people, study_ids):
    pdf = render_study_report(STUDY["SI-2026-027"]).pdf
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.as_user(people["carla"].id) as conn:
        documents.store_document(conn, study_ids["SI-2026-027"], pdf + b"\n%extra", filename="x.pdf",
                                 source_kind="uploaded", page_count=1)


def test_signed_link_opens_the_report_at_a_page_without_a_header(client, study_ids):
    study = study_ids["SI-2026-014"]
    link = client.post(f"/api/studies/{study}/document/link?page=4", headers=auth(client, "ben"))
    assert link.status_code == 200
    url = link.json()["url"]
    assert url.endswith("#page=4")
    opened = client.get(url.split("#")[0])
    assert opened.status_code == 200 and opened.content.startswith(b"%PDF")
    # A link is bound to its study, and Carla cannot get one for a report she cannot read.
    token = url.split("link=")[1].split("#")[0]
    assert client.get(f"/api/studies/{study_ids['SI-2025-031']}/document?link={token}").status_code == 404
    assert client.post(f"/api/studies/{study}/document/link", headers=auth(client, "carla")).status_code == 404
    assert client.get(f"/api/studies/{study}/document?link=not-a-token").status_code == 401


# --------------------------------------------------------------------------- study detail and citations

def test_study_detail_includes_document_and_pages(client, study_ids):
    detail = client.get(f"/api/studies/{study_ids['SI-2026-014']}", headers=auth(client, "ben")).json()
    assert detail["provenance"] == "synthetic"
    assert detail["document"]["page_count"] >= 4 and detail["document"]["url"].endswith("/document")
    first = detail["findings"][0]
    assert first["page"] == 3 and first["cite_label"] == "SI-2026-014 · p.3"
    assert first["document_url"].endswith("/document#page=3")
    assert client.get(f"/api/studies/{study_ids['SI-2026-014']}", headers=auth(client, "carla")).status_code == 404


def test_brief_sources_cite_page_and_link_to_the_report(client):
    brief = client.post("/api/briefs", headers=auth(client, "ben"), json={"question": SME_QUESTION}).json()
    sources = list(brief["sources"].values())
    assert sources and all(s["page"] for s in sources)
    assert all(s["cite_label"] == f"{s['study_code']} · p.{s['page']}" for s in sources)
    assert all(s["document_url"].endswith(f"#page={s['page']}") for s in sources)
    stored = client.get(f"/api/briefs/{brief['id']}", headers=auth(client, "ben")).json()
    assert all(s["page"] for s in stored["sources"].values())


# --------------------------------------------------------------------------- PDF ingestion

def test_pdf_upload_goes_to_review_with_pages_and_document(client, db):
    headers = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=headers).json()}
    report = render_study_report(NEW_REPORT)
    response = client.post("/api/ingest/pdf", headers=headers,
                           data={"owner_team_id": teams["SME Banking"], "access_level": "open"},
                           files={"file": ("payroll-switching.pdf", report.pdf, "application/pdf")})
    assert response.status_code == 200, response.text
    study = response.json()
    assert study["review_status"] == "pending_review" and study["provenance"] == "internal"
    assert (study["method_type"], study["sample_size"], study["fieldwork_end"]) == ("quant", 1500, "2026-07-29")
    assert study["robustness_tier"] == "A"
    assert [f["page"] for f in study["findings"]] == report.pages
    assert all(f["source_excerpt"] for f in study["findings"])
    assert study["document"]["source_kind"] == "uploaded" and study["document"]["page_count"] == report.page_count
    assert study["findings"][2]["subgroup"] == {"age_band": "22-29"}

    # Not readable by the owning team until S&I approves it; then it is in the catalogue with its report.
    assert _download(client, study["id"], "ben").status_code == 404
    assert client.post(f"/api/review/studies/{study['id']}/decision", headers=headers,
                       json={"approve": True}).status_code == 200
    assert _download(client, study["id"], "ben").status_code == 200
    entry = next(s for s in client.get("/api/studies", headers=auth(client, "carla")).json() if s["id"] == study["id"])
    assert entry["can_read"] and entry["document"]["page_count"] == report.page_count
    with db.as_service() as conn:
        logged = conn.execute("select details from public.audit_log where action = 'study.ingested' "
                              "and entity_id = %s", [study["id"]]).fetchone()["details"]
    assert logged["findings_with_page"] == 3 and logged["sha256"] == documents.sha256(report.pdf)


def test_pdf_upload_rejects_non_pdfs_scans_and_non_analysts(client):
    headers = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=headers).json()}
    form = {"owner_team_id": teams["SME Banking"]}
    not_pdf = client.post("/api/ingest/pdf", headers=headers, data=form,
                          files={"file": ("notes.pdf", b"just some text, not a pdf", "application/pdf")})
    assert not_pdf.status_code == 422 and "not a PDF" in not_pdf.json()["detail"]

    blank = PdfWriter()
    blank.add_blank_page(width=595, height=842)
    import io
    buffer = io.BytesIO()
    blank.write(buffer)
    scanned = client.post("/api/ingest/pdf", headers=headers, data=form,
                          files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")})
    assert scanned.status_code == 422 and "OCR" in scanned.json()["detail"]

    report = render_study_report(NEW_REPORT).pdf
    forbidden = client.post("/api/ingest/pdf", headers=auth(client, "ben"), data=form,
                            files={"file": ("r.pdf", report, "application/pdf")})
    assert forbidden.status_code == 403


def test_paste_text_ingestion_still_works(client):
    headers = auth(client, "ana")
    teams = {t["name"]: t["id"] for t in client.get("/api/teams", headers=headers).json()}
    text = (REPO_DIR / "data" / "synthetic" / "reports" / "sme-loan-renewal-pulse-2026.md").read_text(encoding="utf-8")
    response = client.post("/api/ingest", headers=headers, json={
        "report_text": text.replace("Pulse 2026", "Pulse 2026 (copy)"), "owner_team_id": teams["SME Banking"]})
    assert response.status_code == 200 and response.json()["sample_size"] == 450


def test_seeded_review_queue_has_real_pdfs(client):
    queue = client.get("/api/review/queue", headers=auth(client, "ana")).json()
    pdfs = [q for q in queue if (q["source_name"] or "").endswith(".pdf")]
    assert {q["method_type"] for q in pdfs} == {"quant", "qual", "mixed"}
    assert {q["robustness_tier"] for q in pdfs} == {"A", "B", "C"}
    for q in pdfs:
        detail = client.get(f"/api/studies/{q['id']}", headers=auth(client, "ana")).json()
        assert detail["document"] and all(f["page"] for f in detail["findings"])


# --------------------------------------------------------------------------- catalogue

def test_catalogue_lists_restricted_studies_as_metadata_only(client, study_ids):
    carla = {s["code"]: s for s in client.get("/api/studies", headers=auth(client, "carla")).json()}
    restricted = carla["SI-2026-014"]
    assert restricted["can_read"] is False and restricted["request_status"] is None
    assert restricted["owner_team"] == "SME Banking" and restricted["has_document"] is True
    for hidden in ("summary", "population", "sample_size", "effective_tier", "document", "finding_count"):
        assert hidden not in restricted
    assert carla["SI-2026-027"]["can_read"] is True and carla["SI-2026-027"]["document"]["page_count"] >= 4
    assert not any(code.startswith("SI-2026-1") for code in carla)   # pending studies are not catalogued

    client.post("/api/access-requests", headers=auth(client, "carla"),
                json={"study_id": study_ids["SI-2026-014"], "purpose": "Benchmark onboarding drop-off for cards."})
    again = {s["code"]: s for s in client.get("/api/studies", headers=auth(client, "carla")).json()}
    assert again["SI-2026-014"]["request_status"] == "pending"

    ben = {s["code"]: s for s in client.get("/api/studies", headers=auth(client, "ben")).json()}
    assert ben["SI-2026-014"]["can_read"] and ben["SI-2026-014"]["summary"]


def test_catalogue_filters(client):
    headers = auth(client, "ana")
    qual = client.get("/api/studies?method=qual", headers=headers).json()
    assert qual and all(s["method_type"] == "qual" for s in qual)
    team = client.get("/api/studies?team=Cards%20%26%20Payments", headers=headers).json()
    # The filter, not a fixed list: the synthetic corpus grows (card studies were added later).
    assert team and all(s["owner_team"] == "Cards & Payments" for s in team)
    assert "SI-2026-027" in {s["code"] for s in team}
    year = client.get("/api/studies?year=2025", headers=headers).json()
    assert year and all(s["year"] == 2025 for s in year)
    assert {"SI-2025-009", "SI-2025-031"} <= {s["code"] for s in year}
    assert client.get("/api/studies?provenance=public", headers=headers).json() == []   # tests run without public PDFs
    assert client.get("/api/studies?method=survey", headers=headers).status_code == 422


# --------------------------------------------------------------------------- access requests need approved studies

def _pending_study(db) -> str:
    with db.as_service() as conn:
        return conn.execute("select id::text as id from public.studies where review_status = 'pending_review' "
                            "order by code limit 1").fetchone()["id"]


def test_access_cannot_be_requested_for_unapproved_studies(client, db):
    pending = _pending_study(db)
    response = client.post("/api/access-requests", headers=auth(client, "carla"),
                           json={"study_id": pending, "purpose": "Trying to see a study still under review."})
    assert response.status_code == 404
    mine = client.get("/api/access-requests", headers=auth(client, "carla")).json()
    assert all(r["study_id"] != pending for r in mine)


def test_unapproved_studies_are_not_decided_or_listed(client, db, people):
    pending = _pending_study(db)
    with db.as_service() as conn:   # a request that predates the rule, or a study rejected after the request
        conn.execute("alter table public.access_requests disable trigger access_requests_require_approved_study")
        request_id = conn.execute(
            "insert into public.access_requests (study_id, requester_id, requester_team_id, purpose) "
            "values (%s, %s, %s, 'Legacy request for a pending study') returning id::text as id",
            [pending, people["carla"].id, people["carla"].team_id]).fetchone()["id"]
        conn.execute("alter table public.access_requests enable trigger access_requests_require_approved_study")
    with db.as_user(people["carla"].id) as conn:
        listed = conn.execute("select study_id::text as id from public.requested_study_catalogue()").fetchall()
    assert pending not in {r["id"] for r in listed}
    decided = client.post(f"/api/access-requests/{request_id}/decision", headers=auth(client, "ana"),
                          json={"approve": True})
    assert decided.status_code == 409
    with db.as_service() as conn:
        assert conn.execute("select count(*) as n from public.study_grants where study_id = %s",
                            [pending]).fetchone()["n"] == 0
