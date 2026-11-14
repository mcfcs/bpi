"""Study documents: report PDFs stored with their study, page-level citations, and PDF ingestion.

The client: "Is there citation in the report? Yes, but you can't access the report as a whole."
Each study can hold its source PDF (public.study_documents) and each finding records the page it
came from (findings.page), so a brief can cite "SI-2026-014 · p.12" and open the report there.

Reads follow RLS: a document row is visible exactly when its study is (can_read(), or S&I), so a
team without access to a restricted study can neither list nor download its report. Every function
here that reads for a user expects a connection from Database.as_user().
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

import psycopg

from . import audit
from .config import DOCUMENT_CONFIG
from .embeddings import Embedder
from .llm_types import LLM
from .schemas import StudyCardExtraction

PDF_MEDIA_TYPE = "application/pdf"
KNOWN_HEADINGS = ("study details", "summary", "executive summary", "method and sample", "methodology",
                  "key findings", "in their words", "about this report")


class DocumentError(ValueError):
    """The upload is not a usable PDF (not a PDF, too large, or no extractable text)."""


# ---------------------------------------------------------------------------
# Text extraction and normalisation
# ---------------------------------------------------------------------------


@dataclass
class ExtractedPdf:
    pages: list[str]           # text per page, 1-based page n is pages[n - 1]
    title: str | None          # document metadata title, when set

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(p.strip()) for p in self.pages)


def check_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise DocumentError("That file is not a PDF.")
    if len(data) > DOCUMENT_CONFIG["max_upload_bytes"]:
        raise DocumentError(f"PDFs over {DOCUMENT_CONFIG['max_upload_bytes'] // 1_000_000} MB are not accepted.")


def extract_pdf(data: bytes) -> ExtractedPdf:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    check_pdf(data)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("The PDF is password-protected.")
        pages = [(page.extract_text() or "") for page in reader.pages]
        title = (reader.metadata.title if reader.metadata else None) or None
    except PdfReadError as exc:
        raise DocumentError(f"The PDF could not be read: {exc}") from exc
    return ExtractedPdf(pages=pages, title=title.strip() if title else None)


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def strip_running_lines(pages: list[str]) -> list[list[str]]:
    """Lines per page without running headers and footers: lines (digits ignored) that recur on at
    least half the pages of a document of three or more pages."""
    split = [[ln.rstrip() for ln in p.splitlines()] for p in pages]
    if len(pages) < 3:
        return [[ln for ln in lines if ln.strip()] for lines in split]
    counts = Counter(shape for lines in split for shape in {_shape(ln) for ln in lines if ln.strip()})
    running = {shape for shape, n in counts.items() if n >= max(3, len(pages) / 2)}
    return [[ln for ln in lines if ln.strip() and _shape(ln) not in running] for lines in split]


_TERMINAL = re.compile(r"""[.!?)"'\]]\s*$""")
_VERBATIM_END = re.compile(r"""["”]\s*[-–—]\s*(.+)$""")
_BULLET = re.compile(r"^\s*(?:[-*•▪●]|\d{1,2}[.)])\s+")


def normalise_report_text(extracted: ExtractedPdf) -> str:
    """PDF text -> the semi-structured form offline_extract reads: '# Title', '## Heading',
    '- finding' bullets with wrapped lines joined, and '> "quote" — attribution' verbatims.
    Lines it does not recognise pass through unchanged, so the Claude extractor sees everything."""
    pages = strip_running_lines(extracted.pages)
    lines = [ln.strip() for page in pages for ln in page]
    title = extracted.title or next((ln for ln in lines if len(ln) > 8 and not ln.isupper()), "Untitled study")

    out: list[str] = [f"# {title}", ""]
    buffer: list[str] = []
    kind: str | None = None   # 'bullet' | 'quote' while a multi-line item is open

    def flush():
        nonlocal buffer, kind
        if buffer:
            joined = re.sub(r"\s+", " ", " ".join(buffer)).strip()
            if kind == "bullet":
                out.append("- " + joined)
            else:
                match = _VERBATIM_END.search(joined)
                quote, attribution = (joined[: match.start() + 1], match.group(1)) if match else (joined, "")
                out.append(f"> {quote.strip()}" + (f" — {attribution.strip()}" if attribution else ""))
        buffer, kind = [], None

    for line in lines:
        lowered = line.lower().rstrip(":")
        if lowered in KNOWN_HEADINGS:
            flush()
            out += ["", f"## {line.rstrip(':')}", ""]
            continue
        if line == title:
            continue
        starts_quote = line.startswith(('"', "“"))
        if _BULLET.match(line):
            flush()
            buffer, kind = [_BULLET.sub("", line)], "bullet"
        elif starts_quote:
            flush()
            buffer, kind = [line], "quote"
        elif kind == "bullet" and not _TERMINAL.search(buffer[-1]):
            buffer.append(line)                      # a wrapped finding
        elif kind == "quote" and not _VERBATIM_END.search(" ".join(buffer)):
            buffer.append(line)                      # a wrapped quotation
        elif kind == "quote" and len(line.split()) <= 3 and line[:1].isupper() and not _TERMINAL.search(line):
            buffer.append(line)                      # a wrapped attribution ("..., Cebu" / "City")
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------------------
# Locating findings in the page texts
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    text = text.lower().translate(str.maketrans({"–": "-", "—": "-", "‘": "'", "’": "'",
                                                  "“": '"', "”": '"'}))
    text = re.sub(r"-\s*\n\s*", "", text)          # hyphenation at line ends
    return re.sub(r"[^a-z0-9%.,']+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [t.strip(".,'") for t in _norm(text).split() if t.strip(".,'")]


def locate_page(text: str, pages: list[str]) -> tuple[int | None, float]:
    """The 1-based page a finding's text appears on, and how sure we are (0-1).

    Exact (normalised) substring first; otherwise the page with the best share of the finding's
    word trigrams. Below DOCUMENT_CONFIG['min_page_match'] it returns None: an analyst can set the
    page at review rather than the system citing a wrong one."""
    needle = _norm(text)
    if not needle:
        return None, 0.0
    # PDF text extraction often splits words ("s ome", "w e") or spaces punctuation ("( 4%)"), so a
    # match with all spaces removed also counts as exact. The first page wins, so a sentence repeated
    # later (an executive summary, then the chapter) is cited where it first appears.
    compact = needle.replace(" ", "")
    for i, page in enumerate((_norm(p) for p in pages), 1):
        if needle in page or compact in page.replace(" ", ""):
            return i, 1.0
    tokens = _tokens(text)
    if len(tokens) < 3:
        return None, 0.0
    grams = {tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)}
    best, best_score = None, 0.0
    for i, page in enumerate(pages, 1):
        page_tokens = _tokens(page)
        page_grams = {tuple(page_tokens[j:j + 3]) for j in range(len(page_tokens) - 2)}
        score = len(grams & page_grams) / len(grams)
        if score > best_score:
            best, best_score = i, score
    if best_score < DOCUMENT_CONFIG["min_page_match"]:
        return None, best_score
    return best, best_score


def excerpt_on_page(text: str, page_text: str, width: int = 280) -> str | None:
    """The passage on the page that best matches the finding, for the source view."""
    flat = re.sub(r"\s+", " ", page_text).strip()
    if not flat:
        return None
    probe = " ".join(text.split()[:6])
    idx = flat.lower().find(probe.lower())
    if idx < 0:
        return None
    return flat[idx: idx + width].strip()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_document(conn: psycopg.Connection, study_id: str, data: bytes, *, filename: str, source_kind: str,
                   page_count: int | None, source_url: str | None = None, license: str | None = None,
                   uploaded_by: str | None = None) -> str:
    """Store a report for a study. Documents are immutable (no update policy): storing the same bytes
    again is a no-op that returns the existing row."""
    check_pdf(data)
    digest = sha256(data)
    conn.execute(
        "insert into public.study_documents (study_id, filename, media_type, content, page_count, sha256, "
        "source_url, source_kind, license, uploaded_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "on conflict (study_id, sha256) do nothing",
        [study_id, filename, PDF_MEDIA_TYPE, data, page_count, digest, source_url, source_kind, license, uploaded_by],
    )
    return conn.execute("select id::text as id from public.study_documents where study_id = %s and sha256 = %s",
                        [study_id, digest]).fetchone()["id"]


def set_finding_pages(conn: psycopg.Connection, study_id: str, pages: dict[int, int | None],
                      excerpts: dict[int, str | None] | None = None) -> None:
    """Record the page (and optionally the source passage) of each finding, by ordinal."""
    excerpts = excerpts or {}
    for ordinal, page in pages.items():
        conn.execute(
            "update public.findings set page = %s, source_excerpt = coalesce(%s, source_excerpt) "
            "where study_id = %s and ordinal = %s",
            [page, excerpts.get(ordinal), study_id, ordinal],
        )


DOCUMENT_COLUMNS = """
    d.id::text as id, d.study_id::text as study_id, d.filename, d.media_type, d.byte_size, d.page_count,
    d.sha256, d.source_url, d.source_kind, d.license, d.created_at
"""


def document_url(study_id: str, page: int | None = None) -> str:
    return f"/api/studies/{study_id}/document" + (f"#page={page}" if page else "")


def document_info(conn: psycopg.Connection, study_id: str) -> dict | None:
    """Metadata of the study's latest document, if the caller can read it (RLS)."""
    row = conn.execute(
        f"select {DOCUMENT_COLUMNS} from public.study_documents d where d.study_id = %s "
        "order by d.created_at desc limit 1", [study_id],
    ).fetchone()
    if row is None:
        return None
    return {**row, "created_at": row["created_at"].isoformat(), "url": document_url(study_id)}


def load_document(conn: psycopg.Connection, study_id: str) -> dict | None:
    """The latest document with its bytes, if the caller can read it (RLS); None otherwise."""
    return conn.execute(
        f"select {DOCUMENT_COLUMNS}, d.content from public.study_documents d where d.study_id = %s "
        "order by d.created_at desc limit 1", [study_id],
    ).fetchone()


def augment_study_detail(conn: psycopg.Connection, detail: dict) -> dict:
    """Add provenance, the document and each finding's page and citation to a study detail."""
    study_id = detail["id"]
    meta = conn.execute("select provenance, publisher from public.studies where id = %s", [study_id]).fetchone()
    pages = {r["id"]: r for r in conn.execute(
        "select id::text as id, page, source_excerpt from public.findings where study_id = %s", [study_id])}
    doc = document_info(conn, study_id)
    detail.update(provenance=meta["provenance"] if meta else None, publisher=meta["publisher"] if meta else None,
                  document=doc)
    for f in detail.get("findings", []):
        extra = pages.get(f["id"], {})
        f["page"] = extra.get("page")
        f["source_excerpt"] = extra.get("source_excerpt")
        f["cite_label"] = cite_label(detail["code"], f["page"])
        f["document_url"] = document_url(study_id, f["page"]) if doc else None
    return detail


def cite_label(code: str, page: int | None) -> str:
    return f"{code} · p.{page}" if page else code


def attach_citations(conn: psycopg.Connection, sources: dict[str, dict]) -> dict[str, dict]:
    """Add page, citation label and a document link to brief/coverage source views. Runs as the
    caller, so a finding the caller can no longer read simply gets no page."""
    if not sources:
        return sources
    rows = conn.execute(
        "select f.id::text as id, f.page, f.source_excerpt, "
        "exists (select 1 from public.study_documents d where d.study_id = f.study_id) as has_document, "
        "s.provenance, s.publisher "
        "from public.findings f join public.studies s on s.id = f.study_id where f.id = any(%s::uuid[])",
        [list(sources)],
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    for fid, view in sources.items():
        row = by_id.get(fid)
        page = row["page"] if row else None
        view["page"] = page
        view["source_excerpt"] = row["source_excerpt"] if row else None
        view["provenance"] = row["provenance"] if row else None
        view["publisher"] = row["publisher"] if row else None
        view["cite_label"] = cite_label(view.get("study_code", ""), page)
        view["document_url"] = document_url(view["study_id"], page) if row and row["has_document"] else None
    return sources


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def catalogue(conn: psycopg.Connection, *, method: str | None = None, team: str | None = None,
              year: int | None = None, provenance: str | None = None) -> list[dict]:
    """Approved studies: full catalogue entries for those the caller can read, metadata only (code,
    title, owner team, method, year, provenance) with request-access status for the rest."""
    meta = conn.execute(
        "select study_id::text as study_id, code, title, owner_team, access_level, method_type, fieldwork_year, "
        "provenance, publisher, has_document, can_read from public.study_catalogue()"
    ).fetchall()
    readable_ids = [m["study_id"] for m in meta if m["can_read"]]
    details = {r["id"]: r for r in conn.execute(
        "select s.id::text as id, s.summary, s.sample_size, s.fieldwork_end, s.population, s.effective_tier, "
        "(select count(*) from public.findings f where f.study_id = s.id) as finding_count, "
        "(select json_build_object('id', d.id::text, 'filename', d.filename, 'page_count', d.page_count, "
        "  'byte_size', d.byte_size, 'source_kind', d.source_kind, 'license', d.license, 'source_url', d.source_url) "
        " from public.study_documents d where d.study_id = s.id order by d.created_at desc limit 1) as document "
        "from public.studies s where s.id = any(%s::uuid[])", [readable_ids])}
    requests = {r["study_id"]: r["status"] for r in conn.execute(
        "select distinct on (study_id) study_id::text as study_id, status from public.access_requests "
        "where requester_id = auth.uid() order by study_id, created_at desc")}

    out = []
    for m in meta:
        if method and m["method_type"] != method:
            continue
        if team and team not in (m["owner_team"],):
            continue
        if year and m["fieldwork_year"] != year:
            continue
        if provenance and m["provenance"] != provenance:
            continue
        entry = {
            "id": m["study_id"], "code": m["code"], "title": m["title"], "owner_team": m["owner_team"],
            "access_level": m["access_level"], "method_type": m["method_type"], "year": m["fieldwork_year"],
            "provenance": m["provenance"], "publisher": m["publisher"], "has_document": m["has_document"],
            "can_read": m["can_read"],
        }
        d = details.get(m["study_id"])
        if m["can_read"] and d:
            doc = d["document"]
            entry.update(
                summary=d["summary"], sample_size=d["sample_size"],
                fieldwork_end=d["fieldwork_end"].isoformat() if d["fieldwork_end"] else None,
                population=d["population"], effective_tier=d["effective_tier"], finding_count=d["finding_count"],
                document={**doc, "url": document_url(m["study_id"])} if doc else None,
                request_status=None,
            )
        else:
            entry.update(request_status=requests.get(m["study_id"]))
        out.append(entry)
    out.sort(key=lambda e: (not e["can_read"], -(e["year"] or 0), e["code"]))
    return out


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------


@dataclass
class PdfIngestResult:
    study_id: str
    document_id: str
    pages_found: int
    findings: int


def map_finding_pages(card: StudyCardExtraction, pages: list[str]) -> tuple[dict[int, int | None], dict[int, str | None]]:
    found: dict[int, int | None] = {}
    excerpts: dict[int, str | None] = {}
    for ordinal, f in enumerate(card.findings):
        # The report's own words first (a model's finding text is usually a paraphrase), then the text.
        page, located_by = None, f.text
        for candidate in (getattr(f, "source_text", None), f.text):
            if candidate:
                page, _ = locate_page(candidate, pages)
                if page:
                    located_by = candidate
                    break
        found[ordinal] = page
        excerpts[ordinal] = excerpt_on_page(located_by, pages[page - 1]) if page else None
    return found, excerpts


def ingest_pdf(conn: psycopg.Connection, llm: LLM, embedder: Embedder, *, data: bytes, filename: str,
               owner_team_id: str, access_level: str, user_id: str | None, today: date,
               source_kind: str = "uploaded", provenance: str = "internal", source_url: str | None = None,
               license: str | None = None) -> PdfIngestResult:
    """PDF -> page texts -> study card (Claude when configured, else the offline extractor) ->
    findings with page numbers -> stored document -> S&I review queue (checkpoint 1)."""
    from .ingestion import known_metric_keys, store_study_card

    extracted = extract_pdf(data)
    if extracted.char_count < DOCUMENT_CONFIG["min_text_chars"]:
        raise DocumentError("No text could be extracted from this PDF. Scanned reports need OCR before upload.")
    report_text = normalise_report_text(extracted)
    card = llm.extract_study_card(report_text, known_metric_keys(conn))
    study_id = store_study_card(
        conn, card, owner_team_id=owner_team_id, access_level=access_level, embedder=embedder, today=today,
        created_by=user_id, source_name=filename, source_text=report_text, provenance=provenance,
    )
    pages, excerpts = map_finding_pages(card, extracted.pages)
    set_finding_pages(conn, study_id, pages, excerpts)
    document_id = store_document(conn, study_id, data, filename=filename, source_kind=source_kind,
                                 page_count=extracted.page_count, source_url=source_url, license=license,
                                 uploaded_by=user_id)
    located = sum(1 for p in pages.values() if p)
    audit.log(conn, "study.ingested", "study", study_id, {
        "source_name": filename, "extractor": getattr(llm, "name", "unknown"), "findings": len(card.findings),
        "method_type": card.method_type, "document_id": document_id, "pages": extracted.page_count,
        "findings_with_page": located, "sha256": sha256(data),
    })
    return PdfIngestResult(study_id=study_id, document_id=document_id, pages_found=located, findings=len(card.findings))
