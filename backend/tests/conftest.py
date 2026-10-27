"""Test fixtures.

Tests run against a real Postgres with pgvector (pgserver, embedded), with the Supabase migrations and
the local auth shim applied, so row-level security is exercised exactly as deployed. A migrated and
seeded template database is built once; every test gets its own copy.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path

import pgserver
import psycopg
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import CurrentUser  # noqa: E402
from app.config import DEV_JWT_SECRET, Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.llm import OfflineLLM  # noqa: E402
from app.main import create_app  # noqa: E402
from app.migrations import apply_migrations  # noqa: E402
from app.seed import seed  # noqa: E402

TODAY = date(2026, 10, 27)
EMAILS = {
    "ana": "ana.reyes@example.com",       # S&I analyst
    "ben": "ben.santos@example.com",      # SME Banking (owns SI-2026-014)
    "dino": "dino.cruz@example.com",      # SME Banking approver
    "carla": "carla.mendoza@example.com", # Cards & Payments (owns SI-2026-027)
}
SME_QUESTION = "Why do SME owners drop off during online loan applications?"
QR_QUESTION = "How do market vendors feel about accepting QR payments?"
CARDS_QUESTION = "Do young professionals prefer cashback or travel rewards on credit cards?"


@pytest.fixture(scope="session")
def pg_server():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="si-evidence-tests-"), cleanup_mode="delete")
    yield server
    server.cleanup()


@pytest.fixture(scope="session")
def template_name(pg_server) -> str:
    name = "si_template"
    with psycopg.connect(pg_server.get_uri(), autocommit=True) as conn:
        conn.execute(f"drop database if exists {name}")
        conn.execute(f"create database {name}")
    uri = pg_server.get_uri(name)
    apply_migrations(uri)
    db = Database(uri, max_size=2)
    seed(db, TODAY)
    db.close()
    return name


@pytest.fixture
def db(pg_server, template_name):
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = pg_server.get_uri()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'create database "{name}" template {template_name}')
    database = Database(pg_server.get_uri(name), max_size=4)
    yield database
    database.close()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'drop database "{name}" with (force)')


@pytest.fixture
def people(db) -> dict[str, CurrentUser]:
    with db.as_service() as conn:
        rows = conn.execute(
            "select p.id::text as id, p.email, p.display_name, p.role, p.team_id::text as team_id, t.name as team_name "
            "from public.profiles p join public.teams t on t.id = p.team_id"
        ).fetchall()
    by_email = {r["email"]: CurrentUser(**r) for r in rows}
    return {short: by_email[email] for short, email in EMAILS.items()}


@pytest.fixture
def study_ids(db) -> dict[str, str]:
    with db.as_service() as conn:
        return {r["code"]: r["id"] for r in conn.execute("select code, id::text as id from public.studies").fetchall()}


TEST_SETTINGS = Settings(
    database_url="", jwt_secret=DEV_JWT_SECRET, demo_mode=True, llm_provider="offline", llm_model="offline",
    llm_effort="low", commissioning_adapter="noop", commissioning_webhook_url=None,
    commissioning_webhook_headers={}, cors_origins=("http://localhost:3000",),
)


@pytest.fixture
def make_client(db):
    def _make(llm=None, adapter=None) -> TestClient:
        app = create_app(TEST_SETTINGS, db=db, llm=llm or OfflineLLM(), today=lambda: TODAY, adapter=adapter)
        return TestClient(app)
    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def auth(client: TestClient, who: str) -> dict[str, str]:
    response = client.post("/api/demo/login", json={"email": EMAILS[who]})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def brief_text(brief: dict) -> str:
    """Every piece of prose a reader sees in a brief."""
    parts = [c["text"] for c in brief["claims"]]
    parts += [n["explanation"] for n in brief["context_notes"] + brief["unresolved_conflicts"]]
    parts += brief["gaps"] + brief["confidence"]["reasons"]
    parts += [brief.get("no_headline_message") or "", brief.get("disclaimer") or ""]
    return "\n".join(parts)
