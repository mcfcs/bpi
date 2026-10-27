"""HTTP API for the S&I evidence assistant."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import audit, commissioning, governance, ingestion, review
from .auth import CurrentUser, decode_token, issue_token
from .commissioning import CommissioningAdapter, build_adapter
from .config import Settings, get_settings
from .db import Database
from .describe import source_view
from .embeddings import Embedder, HashingEmbedder
from .jobs.recompute_tiers import recompute_all
from .llm import OfflineLLM, build_llm
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
    embedder = embedder or HashingEmbedder()
    adapter = adapter or build_adapter(settings)
    offline = OfflineLLM()
    briefs = BriefService(db, llm, embedder, fallback_llm=offline, today=today)

    app = FastAPI(title="S&I evidence assistant", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    app.state.db = db

    # ------------------------------------------------------------------ errors
    def _error(status: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": message})

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

    @app.exception_handler(psycopg.errors.IntegrityError)
    async def _integrity(_: Request, exc: Exception):
        return _error(422, str(exc).splitlines()[0])

    @app.exception_handler(review.ReviewError)
    @app.exception_handler(governance.GovernanceError)
    async def _rule(_: Request, exc: Exception):
        return _error(422, str(exc))

    @app.exception_handler(LookupError)
    async def _lookup(_: Request, exc: Exception):
        return _error(404, str(exc).capitalize() + ".")

    # ------------------------------------------------------------------ auth
    def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Sign in first.")
        try:
            claims = decode_token(authorization.split(" ", 1)[1], settings.jwt_secret)
        except jwt.PyJWTError:
            raise HTTPException(401, "Your session has expired. Sign in again.")
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

    @app.get("/api/health")
    def health():
        return {"ok": True, "llm": llm.name, "commissioning_adapter": adapter.name}

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
        return briefs.ask(user, body.question)

    @app.get("/api/briefs")
    def my_briefs(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return conn.execute(
                "select id::text as id, question, confidence, created_at from public.briefs "
                "where user_id = auth.uid() order by created_at desc limit 20").fetchall()

    @app.get("/api/briefs/{brief_id}")
    def get_brief(brief_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            row = conn.execute(
                "select b.id::text as id, b.payload, b.created_at, "
                "(select json_build_object('id', e.id::text, 'status', e.status, 'reason', e.reason, 'response', e.response) "
                " from public.escalations e where e.brief_id = b.id order by e.created_at desc limit 1) as escalation "
                "from public.briefs b where b.id = %s", [brief_id]).fetchone()
        if row is None:
            raise HTTPException(404, "Brief not found.")
        return {**row["payload"], "id": row["id"], "created_at": row["created_at"].isoformat(), "escalation": row["escalation"]}

    # ------------------------------------------------------------------ studies and review (checkpoint 1)
    @app.get("/api/studies/{study_id}")
    def get_study(study_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            detail = review.study_detail(conn, study_id, today())
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
            return review.update_study(conn, study_id, body, today())

    @app.patch("/api/review/findings/{finding_id}")
    def patch_finding(finding_id: str, body: FindingPatch, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return review.update_finding(conn, finding_id, body, embedder)

    @app.post("/api/review/studies/{study_id}/decision")
    def decide_study(study_id: str, body: ReviewDecision, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            review.decide_study(conn, study_id, body.approve, body.note, user.id)
            return review.study_detail(conn, study_id, today())

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
            return governance.decide_access(conn, request_id, body.approve, body.note, body.expires_at)

    # ------------------------------------------------------------------ escalation (checkpoint 3)
    @app.get("/api/escalations")
    def escalations(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.list_escalations(conn)

    @app.post("/api/escalations")
    def escalate(body: EscalationBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return governance.create_escalation(conn, user.id, body.brief_id, body.note)

    @app.post("/api/escalations/{escalation_id}/respond")
    def respond(escalation_id: str, body: EscalationResponseBody, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            return governance.respond_escalation(conn, escalation_id, body.response, user.id)

    # ------------------------------------------------------------------ commissioning (checkpoint 4)
    @app.post("/api/commissioning/coverage")
    def coverage(body: CoverageBody, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return commissioning.run_coverage_check(conn, user.id, body.title, body.objectives, embedder, llm, offline)

    @app.get("/api/commissioning")
    def my_checks(user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            return conn.execute(
                "select id::text as id, title, created_at, adapter, submitted_at from public.commissioning_checks "
                "where created_by = auth.uid() order by created_at desc limit 20").fetchall()

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
        return {**check, "findings": findings}

    @app.post("/api/commissioning/{check_id}/submit")
    def submit_check(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, _ = _check_with_findings(conn, check_id)
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
            check, _ = _check_with_findings(conn, check_id)
            audit.log(conn, "commissioning.exported", "commissioning_check", check_id, {"format": "json"})
        return JSONResponse(
            {"id": check["id"], "title": check["title"], "created_at": check["created_at"], **check["result"]},
            headers={"Content-Disposition": f'attachment; filename="coverage-{check_id[:8]}.json"'})

    @app.get("/api/commissioning/{check_id}/export.pdf")
    def export_pdf(check_id: str, user: CurrentUser = Depends(current_user)):
        with as_user(user) as conn:
            check, findings = _check_with_findings(conn, check_id)
            audit.log(conn, "commissioning.exported", "commissioning_check", check_id, {"format": "pdf"})
        return Response(commissioning.export_pdf(check, findings), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="coverage-{check_id[:8]}.pdf"'})

    # ------------------------------------------------------------------ audit
    @app.get("/api/audit")
    def audit_log(limit: int = 200, user: CurrentUser = Depends(require_si)):
        with as_user(user) as conn:
            rows = conn.execute(
                "select a.id, a.occurred_at, a.action, a.entity_type, a.entity_id, a.details, "
                "coalesce(p.display_name, 'System') as actor from public.audit_log a "
                "left join public.profiles p on p.id = a.actor_id order by a.id desc limit %s",
                [min(max(limit, 1), 1000)]).fetchall()
        return rows

    return app
