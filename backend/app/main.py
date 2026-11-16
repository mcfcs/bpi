"""HTTP API for the S&I evidence assistant."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import hmac
import time
import httpx
import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import alerts, audit, commissioning, gaps, governance, ingestion, overlap, privacy, progress, review, usage
from .auth import CurrentUser, decode_token, issue_token
from .commissioning import CommissioningAdapter, build_adapter
from .config import Settings, get_settings
from .db import Database
from .describe import source_view
from .embeddings import Embedder, EmbeddingUnavailable, build_embedder, search_ready, to_pgvector
from .jobs.recompute_tiers import recompute_all
from .llm import OfflineLLM, build_llm, writer_ready
from .llm_types import LLM, LLMError
from .retrieval import load_sources
from .schemas import (
    AccessDecisionBody,
    AccessRequestBody,
    AskBody,
    CoverageBody,
    EscalationBody,
    EscalationResponseBody,
    FindingPatch,
    IngestBody,
    LoginBody,
    ReviewDecision,
    StudyPatch,
)
from .synthesis import BriefService

# Study documents: catalogue, report PDFs, page citations and PDF ingestion (app/documents*.py).
from . import documents  # noqa: E402
from .documents_api import register_document_routes  # noqa: E402

PROFILE_SQL = """
    select p.id::text as id, p.email, p.display_name, p.role, p.team_id::text as team_id, t.name as team_name
    from public.profiles p join public.teams t on t.id = p.team_id
"""


def create_app(settings: Settings | None = None, *, db: Database | None = None, llm: LLM | None = None,
               embedder: Embedder | None = None, today: Callable[[], date] = date.today,
               adapter: CommissioningAdapter | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = db or Database(settings.database_url)
    llm = llm or build_llm(settings)
    embedder = embedder or build_embedder(settings.embedding_provider, settings.embedding_model)
    adapter = adapter or build_adapter(settings)
    offline = OfflineLLM()
    briefs = BriefService(db, llm, embedder, fallback_llm=offline, today=today)

    app = FastAPI(title="S&I evidence assistant", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    app.state.db = db

    if settings.backend_shared_secret:
        expected_key = settings.backend_shared_secret

        @app.middleware("http")
        async def require_frontend_key(request: Request, call_next):
            """When the backend has its own public URL, refuse calls that didn't come through the
            password-protected frontend. /api/health stays open so an uptime checker can keep it awake."""
            if request.url.path != "/api/health" and request.method != "OPTIONS" and not hmac.compare_digest(
                    request.headers.get("x-demo-key", ""), expected_key):
                return JSONResponse(status_code=401, content={"detail": "Open the app through its own link."})
            return await call_next(request)

    # ------------------------------------------------------------------ errors
    def _error(status: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": message})

    @app.exception_handler(EmbeddingUnavailable)
    async def embedding_unavailable(request: Request, exc: EmbeddingUnavailable):
        return JSONResponse(status_code=503, content={
            "detail": "Search can't run right now: the hosted search model can't be reached. Try again in a few "
                      "minutes, or ask whoever runs the app to sign in to AWS again."})

    @app.exception_handler(psycopg.errors.InsufficientPrivilege)
    async def _forbidden(_: Request, exc: Exception):
        return _error(403, "You do not have permission to do that.")

    @app.exception_handler(psycopg.errors.NoDataFound)
    async def _not_found(_: Request, exc: Exception):
        return _error(404, "Not found.")

    @app.exception_handler(psycopg.errors.ObjectNotInPrerequisiteState)
    async def _conflict_state(_: Request, exc: Exception):
        return _error(409, str(exc).splitlines()[0])

    @app.exception_handler(psycopg.errors.UniqueViolation)
    async def _duplicate(_: Request, exc: Exception):
        return _error(409, "That already exists (for example, a pending request for the same study).")

    @app.exception_handler(psycopg.errors.ForeignKeyViolation)
    async def _missing_reference(_: Request, exc: Exception):
        return _error(422, "That refers to a record that does not exist. Check the id and try again.")

    @app.exception_handler(psycopg.errors.IntegrityError)
    async def _integrity(_: Request, exc: Exception):
        return _error(422, str(exc).splitlines()[0])

    # A malformed id in a path or body ("abc" for a UUID) is a request for something that does not
    # exist, not a server error.
    @app.exception_handler(psycopg.errors.InvalidTextRepresentation)
    async def _bad_id(_: Request, exc: Exception):
        return _error(404, "Not found.")

    # Values Postgres cannot store, e.g. text containing a NUL byte.
    @app.exception_handler(psycopg.DataError)
    async def _bad_value(_: Request, exc: Exception):
        return _error(422, "That text contains characters that cannot be stored. Remove them and try again.")

    @app.exception_handler(review.ReviewError)
    @app.exception_handler(governance.GovernanceError)
    async def _rule(_: Request, exc: Exception):
        return _error(422, str(exc))

    @app.exception_handler(LookupError)
    async def _lookup(_: Request, exc: Exception):
        if isinstance(exc, KeyError):  # a programming error, not "not found"
            return _error(500, "Something went wrong on our side. Try again.")
        return _error(404, str(exc).capitalize() + ".")

    # ------------------------------------------------------------------ auth
    def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Sign in first.")
        try:
            claims = decode_token(authorization.split(" ", 1)[1], settings.jwt_secret)
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Your session has expired. Sign in again.")
        except jwt.PyJWTError:
            raise HTTPException(401, "Your sign-in is not valid. Sign in again.")
        with db.as_user(claims["sub"], claims.get("email")) as conn:
            row = conn.execute(PROFILE_SQL + " where p.id = auth.uid()").fetchone()
        if row is None:
            raise HTTPException(403, "No profile is set up for this account.")
        return CurrentUser(**row)

    def require_si(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.is_si:
            raise HTTPException(403, "Only S&I analysts can do that.")
        return user

    def as_user(user: CurrentUser):
        return db.as_user(user.id, user.email)

    # The writer and search checks are cached for a minute: the ask page calls health on every visit.
    checks = {"at": float("-inf")}

    @app.get("/api/health")
    def health():
        now = time.monotonic()
        if now - checks["at"] > 60:
            llm_ready, llm_problem = writer_ready(llm)
            ready, problem = search_ready(embedder)
            checks.update(at=now, llm_ready=llm_ready, llm_problem=llm_problem, search_ready=ready, search_problem=problem)
        return {"ok": True, "llm": llm.name, "embedder": embedder.name, "commissioning_adapter": adapter.name,
                **{k: v for k, v in checks.items() if k != "at"}}

    if settings.demo_mode:
        @app.get("/api/demo/personas")
        def personas():
            with db.as_service() as conn:
                return conn.execute(PROFILE_SQL + " order by p.role desc, p.display_name").fetchall()

        @app.post("/api/demo/login")
        def demo_login(body: LoginBody):
            with db.as_service() as conn:
                row = conn.execute(PROFILE_SQL + " where p.email = %s", [body.email]).fetchone()
            if row is None:
                raise HTTPException(404, "No demo persona with that email.")
            return {"token": issue_token(row["id"], row["email"], settings.jwt_secret), "profile": row}

    @app.get("/api/me")
    def me(user: CurrentUser = Depends(current_user)):
        return user.__dict__

    @app.get("/api/teams")
    def teams(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return conn.execute("select id::text as id, name, kind from public.teams order by kind desc, name").fetchall()

    # ------------------------------------------------------------------ briefs
    @app.post("/api/briefs")
    def ask(body: AskBody, user: CurrentUser = Depends(current_user)):
        try:
            brief = briefs.ask(user, body.question, body.reader_role, report=progress.reporter(user.id))
        finally:
            progress.clear(user.id)
        with as_user(user) as conn:   # page numbers and report links for citations ("SI-2026-014 · p.4")
            documents.attach_citations(conn, brief.get("sources") or {})
        return brief

    @app.post("/api/briefs/{brief_id}/follow-up")
    def follow_up(brief_id: str, body: AskBody, user: CurrentUser = Depends(current_user)):
        """A new brief that continues an earlier one of the caller's ("What about Mindanao?")."""
        with as_user(user) as conn:
            parent = conn.execute(
                "select id::text as id, question from public.briefs where id = %s and user_id = auth.uid()",
                [brief_id]).fetchone()
        if parent is None:
            raise HTTPException(404, "Brief not found.")
        try:
            brief = briefs.ask(user, body.question, body.reader_role, report=progress.reporter(user.id),
                               follow_up_of=parent)
        finally:
            progress.clear(user.id)
        with as_user(user) as conn:
            documents.attach_citations(conn, brief.get("sources") or {})
        return brief

    @app.get("/api/briefs/progress")
    def brief_progress(user: CurrentUser = Depends(current_user)):
        """The step the caller's brief is on (polled by the ask page), or null when none is running."""
        return progress.current(user.id)

    @app.get("/api/briefs")
    def my_briefs(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return conn.execute(
                "select id::text as id, coalesce(payload ->> 'question', question) as question, confidence, created_at "
                "from public.briefs "
                "where user_id = auth.uid() order by created_at desc limit 20").fetchall()

    @app.get("/api/briefs/{brief_id}")
    def get_brief(brief_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            row = conn.execute(
                "select b.id::text as id, b.payload, b.created_at, "
                "(select json_build_object('id', e.id::text, 'status', e.status, 'reason', e.reason, 'response', e.response) "
                " from public.escalations e where e.brief_id = b.id order by e.created_at desc limit 1) as escalation "
                "from public.briefs b where b.id = %s", [brief_id]).fetchone()
            if row is not None:   # page numbers and report links, re-checked against current access
                documents.attach_citations(conn, row["payload"].get("sources") or {})
            # Escalation thread (consultation 2): every escalation on this brief, oldest first.
            # "escalation" above stays the latest one for compatibility.
            thread = governance.brief_escalations(conn, brief_id) if row else []
            # A conflict already with an analyst from an earlier brief is linked, not re-raised, so
            # this brief has no escalation row of its own: show the open one (when RLS lets the
            # reader see it) instead of nothing.
            if row is not None and row["escalation"] is None and row["payload"].get("unresolved_conflicts"):
                linked = governance.open_conflict_escalation(
                    conn, governance.conflict_keys(row["payload"]["unresolved_conflicts"]))
                if linked is not None:
                    row = {**row, "escalation": {**linked, "response": None}}
        if row is None:
            raise HTTPException(404, "Brief not found.")
        return {**row["payload"], "id": row["id"], "created_at": row["created_at"].isoformat(), "escalation": row["escalation"],
                "escalations": thread}

    # ------------------------------------------------------------------ studies and review (checkpoint 1)
    @app.get("/api/studies/{study_id}")
    def get_study(study_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            detail = review.study_detail(conn, study_id, today())
            if detail is not None:   # provenance, the report document and each finding's page
                documents.augment_study_detail(conn, detail)
            if detail is not None and user.is_si and detail.get("review_status") == "pending_review":
                # Checkpoint 1 aids: personal data in findings, and approved studies this one overlaps.
                detail["privacy"] = privacy.study_flags(conn, study_id)
                detail["overlaps"] = overlap.find_overlaps(conn, study_id, embedder.name)
        if detail is None:
            raise HTTPException(404, "Study not found, or you do not have access to it.")
        if not user.is_si:
            detail.pop("source_text", None)
        return detail

    @app.get("/api/review/queue")
    def queue(user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return review.review_queue(conn)

    @app.patch("/api/review/studies/{study_id}")
    def patch_study(study_id: str, body: StudyPatch, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            detail = review.update_study(conn, study_id, body, today())
            if detail is not None:   # keep the report link and page numbers on the edited card
                documents.augment_study_detail(conn, detail)
            return detail

    @app.patch("/api/review/findings/{finding_id}")
    def patch_finding(finding_id: str, body: FindingPatch, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return review.update_finding(conn, finding_id, body, embedder)

    @app.post("/api/review/studies/{study_id}/decision")
    def decide_study(study_id: str, body: ReviewDecision, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            review.decide_study(conn, study_id, body.approve, body.note, user.id, body.privacy_checked)
            detail = review.study_detail(conn, study_id, today())
            if detail is not None:
                documents.augment_study_detail(conn, detail)
        # After the approval commits: earlier questions this study now answers, each searched as its asker.
        raised = alerts.notify_new_answers(db, embedder, study_id, user) if body.approve and detail else []
        return {**detail, "answer_alerts": len(raised)} if detail is not None else detail

    @app.post("/api/ingest")
    def ingest(body: IngestBody, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            try:
                study_id = ingestion.ingest_report(
                    conn, llm, embedder, report_text=body.report_text, owner_team_id=body.owner_team_id,
                    access_level=body.access_level, source_name=body.source_name, user_id=user.id, today=today())
            except LLMError:
                study_id = ingestion.ingest_report(
                    conn, offline, embedder, report_text=body.report_text, owner_team_id=body.owner_team_id,
                    access_level=body.access_level, source_name=body.source_name, user_id=user.id, today=today())
            return review.study_detail(conn, study_id, today())

    @app.post("/api/admin/recompute-tiers")
    def recompute(user: CurrentUser = Depends(require_si)):
        return {"changed": recompute_all(db, today(), actor_id=user.id)}

    # ------------------------------------------------------------------ access (checkpoint 2)
    @app.get("/api/access-requests")
    def access_requests(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.list_access_requests(conn)

    @app.post("/api/access-requests")
    def request_access(body: AccessRequestBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.request_access(conn, body.study_id, body.purpose, user.id)

    @app.post("/api/access-requests/{request_id}/decision")
    def decide_access(request_id: str, body: AccessDecisionBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            decision = governance.decide_access(conn, request_id, body.approve, body.note, body.expires_at)
        if body.approve and decision.get("status") == "approved":
            # The requester can now read the study: their earlier unanswered questions may be answered.
            with db.as_service() as conn:
                req = conn.execute("select requester_id::text as requester_id, study_id::text as study_id "
                                   "from public.access_requests where id = %s", [request_id]).fetchone()
            if req:
                raised = alerts.notify_new_answers(db, embedder, req["study_id"], user, only_user=req["requester_id"])
                decision = {**decision, "answer_alerts": len(raised)}
        return decision

    # ------------------------------------------------------------------ answer alerts
    @app.get("/api/alerts")
    def my_alerts(user: CurrentUser = Depends(current_user)):
        """Earlier questions of the caller's that a newly readable study now answers."""
        with as_user(user) as conn:
            return alerts.list_alerts(conn)

    @app.post("/api/alerts/{alert_id}/read")
    def read_alert(alert_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            row = alerts.mark_read(conn, alert_id)
        if row is None:
            raise HTTPException(404, "Alert not found.")
        return row

    # ------------------------------------------------------------------ research-gap map (S&I)
    @app.get("/api/gaps")
    def gap_map(days: int = 90, user: CurrentUser = Depends(require_si)):
        # Unanswered questions asked before embeddings were stored get one, once (one call each).
        with db.as_service() as conn:
            missing = conn.execute(
                "select id::text as id, question from public.briefs where question_embedding is null "
                "and coalesce(cardinality(retrieved_finding_ids), 0) = 0 limit 50").fetchall()
        if missing:
            vectors = [(to_pgvector(embedder.embed_query(m["question"])), m["id"]) for m in missing]
            with db.as_service() as conn:
                for vector, brief_id in vectors:
                    conn.execute("update public.briefs set question_embedding = %s::extensions.vector where id = %s",
                                 [vector, brief_id])
        with as_user(user) as conn:
            return gaps.gap_map(conn, today(), min(max(days, 1), 365))

    # ------------------------------------------------------------------ escalation (checkpoint 3)
    @app.get("/api/escalations")
    def escalations(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.list_escalations(conn)

    @app.post("/api/escalations")
    def escalate(body: EscalationBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.create_escalation(conn, user.id, body.brief_id, body.note,
                                                gaps=body.gaps, suggested_question=body.suggested_question)

    @app.post("/api/escalations/{escalation_id}/respond")
    def respond(escalation_id: str, body: EscalationResponseBody, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return governance.respond_escalation(conn, escalation_id, body.response, user.id)

    # ------------------------------------------------------------------ commissioning (checkpoint 4)
    @app.post("/api/commissioning/coverage")
    def coverage(body: CoverageBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return commissioning.run_coverage_check(conn, user.id, body.title, body.objectives, embedder, llm, offline,
                                                    today=today())

    @app.get("/api/commissioning")
    def my_checks(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return conn.execute(
                "select id::text as id, title, created_at, adapter, submitted_at from public.commissioning_checks "
                "where created_by = auth.uid() order by created_at desc limit 20").fetchall()

    # S&I's inbox: every check a requester chose to send (RLS lets S&I read all checks). Declared
    # before /api/commissioning/{check_id} so "submitted" is not taken for an id.
    @app.get("/api/commissioning/submitted")
    def submitted_checks(user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return conn.execute(
                "select c.id::text as id, c.title, c.created_at, c.submitted_at, c.adapter, "
                "p.display_name as requested_by, t.name as requester_team, "
                "(select count(*) from jsonb_array_elements(c.result->'objectives') o "
                " where o->>'coverage' = 'gap') as new_problems, "
                "jsonb_array_length(c.result->'objectives') as objectives "
                "from public.commissioning_checks c "
                "join public.profiles p on p.id = c.created_by join public.teams t on t.id = p.team_id "
                "where c.submitted_at is not null order by c.submitted_at desc limit 100").fetchall()

    def _check_with_findings(conn, check_id: str) -> tuple[dict, dict]:
        check = commissioning.load_check(conn, check_id)
        if check is None:
            raise HTTPException(404, "Coverage check not found.")
        ids = sorted({fid for o in check["result"]["objectives"] for fid in o["finding_ids"]})
        sources = load_sources(conn, "f.id = any(%s::uuid[])", [ids]) if ids else []
        return check, {s.finding_id: source_view(s) for s in sources}

    @app.get("/api/commissioning/{check_id}")
    def get_check(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, findings = _check_with_findings(conn, check_id)
            documents.attach_citations(conn, findings)
        return {**check, "findings": findings}

    @app.post("/api/commissioning/{check_id}/submit")
    def submit_check(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, _ = _check_with_findings(conn, check_id)
        previous = commissioning.existing_submission(check)
        if previous:
            return previous   # handed over once; a repeat submit changes nothing
        try:
            outcome = adapter.submit(check)
        except httpx.HTTPError as exc:
            with as_user(user) as conn:
                audit.log(conn, "commissioning.submit_failed", "commissioning_check", check_id,
                          {"adapter": adapter.name, "error": str(exc)})
            raise HTTPException(502, f"The commissioning system did not accept the request: {exc}")
        with as_user(user) as conn:
            return commissioning.record_submission(conn, check, adapter, outcome)

    @app.get("/api/commissioning/{check_id}/export.json")
    def export_json(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, findings = _check_with_findings(conn, check_id)
            audit.log(conn, "commissioning.exported", "commissioning_check", check_id, {"format": "json"})
        return JSONResponse(
            commissioning.export_json(check, findings),
            headers={"Content-Disposition": f'attachment; filename="coverage-{check_id[:8]}.json"'})

    @app.get("/api/commissioning/{check_id}/export.pdf")
    def export_pdf(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, findings = _check_with_findings(conn, check_id)
            audit.log(conn, "commissioning.exported", "commissioning_check", check_id, {"format": "pdf"})
        return Response(commissioning.export_pdf(check, findings), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="coverage-{check_id[:8]}.pdf"'})

    # ------------------------------------------------------------------ brief rules (S&I consultation 2)
    # Ask an analyst: a specific escalation drafted from a stored brief. Read-only; the brief row is
    # loaded under RLS, so only its author (or S&I) can draft from it. Send the edited draft to
    # POST /api/escalations with {brief_id, note, gaps: [ticked gap texts], suggested_question}.
    @app.get("/api/briefs/{brief_id}/escalation-draft")
    def escalation_draft(brief_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            row = conn.execute("select id::text as id, payload from public.briefs where id = %s", [brief_id]).fetchone()
        if row is None:
            raise HTTPException(404, "Brief not found.")
        return governance.draft_escalation({**row["payload"], "id": row["id"]})

    # ------------------------------------------------------------------ audit
    @app.get("/api/audit/summary")
    def usage_summary(days: int = 30, user: CurrentUser = Depends(require_si)):
        """What business teams asked and what happened next, for S&I (counts from the audit log)."""
        with as_user(user) as conn:
            return usage.summary(conn, min(max(days, 1), 365))

    @app.get("/api/audit")
    def audit_log(limit: int = 200, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            rows = conn.execute(
                "select a.id, a.occurred_at, a.action, a.entity_type, a.entity_id, a.details, "
                "coalesce(p.display_name, 'System') as actor from public.audit_log a "
                "left join public.profiles p on p.id = a.actor_id order by a.id desc limit %s",
                [min(max(limit, 1), 1000)]).fetchall()
        return rows

    # ------------------------------------------------------------------ study documents
    register_document_routes(app, settings=settings, db=db, llm=llm, offline=offline, embedder=embedder,
                             today=today, current_user=current_user, require_si=require_si)

    return app
