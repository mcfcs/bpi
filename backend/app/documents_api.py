"""HTTP routes for the study catalogue, report documents and PDF ingestion.

Kept out of main.py so the document feature is one registration call there. Every read runs as the
caller (Database.as_user), so RLS decides which studies are listed in full and which reports can be
downloaded; restricted studies appear in the catalogue as metadata only.

    GET  /api/studies                         catalogue (filters: method, team, year, provenance)
    GET  /api/studies/{id}/document           the report PDF (Bearer token, or ?link=<signed link>)
    POST /api/studies/{id}/document/link      a short-lived signed link, for <a href> and #page=N
    POST /api/ingest/pdf                      S&I: upload a PDF report into the review queue
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from datetime import date
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from . import audit, documents, review
from .auth import CurrentUser, decode_token
from .config import DOCUMENT_CONFIG, Settings
from .db import Database
from .embeddings import Embedder
from .llm_types import LLM, LLMError

LINK_AUDIENCE = "study-document"


def issue_document_link(user_id: str, study_id: str, secret: str, ttl: int | None = None) -> str:
    now = int(time.time())
    ttl = ttl or DOCUMENT_CONFIG["download_link_seconds"]
    return jwt.encode({"sub": user_id, "sid": study_id, "aud": LINK_AUDIENCE, "iat": now, "exp": now + ttl},
                      secret, algorithm="HS256")


def _study_uuid(study_id: str) -> str:
    """A malformed id is simply not found (and never reaches SQL as a cast error)."""
    try:
        return str(uuid.UUID(study_id))
    except ValueError:
        raise HTTPException(404, "Document not found, or you do not have access to it.")


def register_document_routes(app: FastAPI, *, settings: Settings, db: Database, llm: LLM, offline: LLM,
                             embedder: Embedder, today: Callable[[], date],
                             current_user: Callable, require_si: Callable) -> None:

    @app.exception_handler(documents.DocumentError)
    async def _bad_document(_: Request, exc: Exception):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def as_user(user: CurrentUser):
        return db.as_user(user.id, user.email)

    @app.get("/api/studies")
    def study_catalogue(method: Literal["quant", "qual", "mixed"] | None = None, team: str | None = None,
                        year: int | None = None, provenance: Literal["synthetic", "public", "internal"] | None = None,
                        user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return documents.catalogue(conn, method=method, team=team, year=year, provenance=provenance)

    def _caller_for_download(study_id: str, authorization: str | None, link: str | None) -> tuple[str, str]:
        """(user id, how they authenticated). A signed link is bound to one user and one study."""
        if link:
            try:
                claims = jwt.decode(link, settings.jwt_secret, algorithms=["HS256"], audience=LINK_AUDIENCE)
            except jwt.PyJWTError:
                raise HTTPException(401, "This document link has expired. Open the report again from the brief.")
            if claims.get("sid") != study_id:
                raise HTTPException(404, "Document not found, or you do not have access to it.")
            return claims["sub"], "link"
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Sign in first.")
        try:
            claims = decode_token(authorization.split(" ", 1)[1], settings.jwt_secret)
        except jwt.PyJWTError:
            raise HTTPException(401, "Your session has expired. Sign in again.")
        return claims["sub"], "token"

    @app.get("/api/studies/{study_id}/document")
    def download_document(study_id: str, link: str | None = None, authorization: str | None = Header(default=None)):
        study_id = _study_uuid(study_id)
        user_id, via = _caller_for_download(study_id, authorization, link)
        with db.as_user(user_id) as conn:
            doc = documents.load_document(conn, study_id)   # RLS: None unless the caller can read the study
            if doc is None:
                raise HTTPException(404, "Document not found, or you do not have access to it.")
            audit.log(conn, "document.downloaded", "study", study_id,
                      {"document_id": doc["id"], "filename": doc["filename"], "via": via})
        return Response(bytes(doc["content"]), media_type=doc["media_type"], headers={
            # ASCII-only so any stored filename is a valid header value.
            "Content-Disposition": f'inline; filename="{re.sub(r"[^A-Za-z0-9._-]+", "-", doc["filename"])}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        })

    @app.post("/api/studies/{study_id}/document/link")
    def document_link(study_id: str, page: int | None = None, user: CurrentUser = Depends(current_user)):
        study_id = _study_uuid(study_id)
        with as_user(user) as conn:
            info = documents.document_info(conn, study_id)
        if info is None:
            raise HTTPException(404, "Document not found, or you do not have access to it.")
        token = issue_document_link(user.id, study_id, settings.jwt_secret)
        url = f"/api/studies/{study_id}/document?link={token}" + (f"#page={page}" if page else "")
        return {"url": url, "expires_in": DOCUMENT_CONFIG["download_link_seconds"], "page_count": info["page_count"]}

    @app.post("/api/ingest/pdf")
    def ingest_pdf(file: UploadFile = File(...), owner_team_id: str = Form(...),
                   access_level: Literal["open", "restricted"] = Form("restricted"),
                   source_url: str | None = Form(None), user: CurrentUser = Depends(require_si)):
        data = file.file.read(DOCUMENT_CONFIG["max_upload_bytes"] + 1)
        documents.check_pdf(data)
        filename = (file.filename or "report.pdf").replace('"', "").replace("\\", "/").rsplit("/", 1)[-1]
        kwargs = dict(data=data, filename=filename, owner_team_id=owner_team_id, access_level=access_level,
                      user_id=user.id, today=today(), source_kind="uploaded", provenance="internal",
                      source_url=source_url)
        with as_user(user) as conn:
            try:
                with conn.transaction():   # savepoint, so a failed Claude call leaves nothing behind
                    result = documents.ingest_pdf(conn, llm, embedder, **kwargs)
            except LLMError:
                result = documents.ingest_pdf(conn, offline, embedder, **kwargs)
            detail = review.study_detail(conn, result.study_id, today())
            return documents.augment_study_detail(conn, detail)
