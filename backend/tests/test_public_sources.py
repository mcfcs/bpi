"""Public research sources: the manifest and hand-labelled cards are well formed, and public studies
are seeded as approved, open, clearly labelled "Public source" studies only when their PDF is present.
No network and no real third-party PDFs are needed: a generated stand-in PDF is used."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from app import public_sources
from app.embeddings import HashingEmbedder
from app.report_pdf import render_study_report
from app.seed import seed_public_reports
from tests.conftest import TODAY, auth

OFFICIAL_HOSTS = {"www.bsp.gov.ph", "www.enterprisesurveys.org", "www.adb.org", "www.cgap.org"}


def test_manifest_and_cards_are_complete_and_consistent():
    reports = public_sources.load_reports()
    assert len(reports) >= 4
    methods = {r.card["method_type"] for r in reports}
    assert "qual" in methods and methods & {"quant", "mixed"}          # both kinds of evidence
    codes = [r.card["code"] for r in reports]
    assert len(set(codes)) == len(codes) and all(c.startswith("PUB-") for c in codes)
    for r in reports:
        entry, card = r.entry, r.card
        assert urlparse(entry["url"]).scheme == "https" and urlparse(entry["url"]).hostname in OFFICIAL_HOSTS
        assert entry["license"] and entry["publisher"] and len(entry["sha256"]) == 64
        public_sources.card_to_extraction(card)                       # validates against the extraction schema
        date.fromisoformat(card["fieldwork_end"])
        assert 4 <= len(card["findings"]) <= 8 or card["method_type"] == "qual"
        for f in card["findings"]:
            assert 1 <= f["page"] <= entry["pages"], (r.slug, f["text"])
            assert f["quote"].strip()
            if f["finding_type"] != "quant_stat":
                assert f.get("value") is None
        if card["method_type"] == "qual":
            assert any(f["finding_type"] == "verbatim" for f in card["findings"])
            assert any(f["finding_type"] == "qual_theme" for f in card["findings"])


def test_public_reports_are_seeded_only_when_the_pdf_is_present(db, people, tmp_path, monkeypatch):
    monkeypatch.setattr(public_sources, "PDF_DIR", tmp_path)
    reports = public_sources.load_reports()
    with db.as_service() as conn:
        team = conn.execute("select id::text as id from public.teams where name = 'Strategy & Insights'").fetchone()["id"]
        assert seed_public_reports(conn, team, people["ana"].id, HashingEmbedder(), TODAY) == []

    stand_in = reports[0]   # any PDF will do for the seeding path; the real file is git-ignored
    (tmp_path / f"{stand_in.slug}.pdf").write_bytes(render_study_report(
        {"title": "Stand-in", "summary": "", "method_type": "quant", "sample_size": 10, "fieldwork_end": "2025-01-31",
         "population": {}, "findings": []}, notice="Stand-in for a public report in tests").pdf)
    with db.as_service() as conn:
        assert seed_public_reports(conn, team, people["ana"].id, HashingEmbedder(), TODAY) == [stand_in.card["code"]]
        study = conn.execute(
            "select s.id::text as id, s.provenance, s.publisher, s.access_level, s.review_status, "
            "d.source_kind, d.source_url, d.license from public.studies s "
            "join public.study_documents d on d.study_id = s.id where s.code = %s", [stand_in.card["code"]]).fetchone()
        pages = [r["page"] for r in conn.execute(
            "select page from public.findings where study_id = %s order by ordinal", [study["id"]])]
        # Seeding again is a no-op.
        seed_public_reports(conn, team, people["ana"].id, HashingEmbedder(), TODAY)
        assert conn.execute("select count(*) as n from public.studies where code = %s",
                            [stand_in.card["code"]]).fetchone()["n"] == 1
    assert (study["provenance"], study["access_level"], study["review_status"]) == ("public", "open", "approved")
    assert study["publisher"] == stand_in.entry["publisher"] and study["source_kind"] == "public"
    assert study["source_url"] == stand_in.entry["url"] and study["license"] == stand_in.entry["license"]
    assert pages == [f["page"] for f in stand_in.card["findings"]]


def test_public_studies_are_labelled_in_the_catalogue(client, db, people, tmp_path, monkeypatch):
    monkeypatch.setattr(public_sources, "PDF_DIR", tmp_path)
    for r in public_sources.load_reports():
        (tmp_path / f"{r.slug}.pdf").write_bytes(render_study_report(
            {"title": r.card["title"], "summary": "", "method_type": "quant", "sample_size": 10,
             "fieldwork_end": "2025-01-31", "population": {}, "findings": []}, notice="Stand-in").pdf)
    with db.as_service() as conn:
        team = conn.execute("select id::text as id from public.teams where name = 'Strategy & Insights'").fetchone()["id"]
        seed_public_reports(conn, team, people["ana"].id, HashingEmbedder(), TODAY)
    public = client.get("/api/studies?provenance=public", headers=auth(client, "carla")).json()
    assert len(public) == len(public_sources.load_reports())
    assert all(s["can_read"] and s["publisher"] and s["document"]["source_kind"] == "public" for s in public)
    detail = client.get(f"/api/studies/{public[0]['id']}", headers=auth(client, "carla")).json()
    assert detail["provenance"] == "public" and all(f["source_excerpt"] for f in detail["findings"])
