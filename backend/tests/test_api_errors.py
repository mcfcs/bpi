"""Malformed requests get clear 4xx answers, never a 500 (from the bug hunt of 30 Oct 2026)."""

from __future__ import annotations

import time

import jwt
import pytest

from app.config import DEV_JWT_SECRET

from .conftest import auth


@pytest.mark.parametrize("method, path, body", [
    ("get", "/api/briefs/not-a-uuid", None),
    ("get", "/api/studies/not-a-uuid", None),
    ("get", "/api/commissioning/not-a-uuid", None),
    ("post", "/api/escalations/not-a-uuid/respond", {"response": "Looked into it."}),
    ("post", "/api/access-requests/not-a-uuid/decision", {"approve": True}),
    ("patch", "/api/review/findings/not-a-uuid", {"text": "x"}),
])
def test_malformed_ids_are_not_found(client, method, path, body):
    who = "ana"
    kwargs = {"headers": auth(client, who)}
    if body is not None:
        kwargs["json"] = body
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 404, response.text


def test_malformed_ids_in_bodies_are_rejected_cleanly(client):
    response = client.post("/api/escalations", headers=auth(client, "ben"),
                           json={"brief_id": "x", "note": "Please check this brief."})
    assert 400 <= response.status_code < 500, response.text


def test_nul_bytes_are_rejected_cleanly(client):
    response = client.post("/api/briefs", headers=auth(client, "ben"),
                           json={"question": "Why do SME owners\x00 drop off?"})
    assert response.status_code == 422, response.text


def _token(claims: dict) -> dict[str, str]:
    return {"Authorization": "Bearer " + jwt.encode(claims, DEV_JWT_SECRET, algorithm="HS256")}


@pytest.mark.parametrize("claims", [
    {"sub": "not-a-uuid", "aud": "authenticated", "exp": int(time.time()) + 600},       # sub not a user id
    {"aud": "authenticated", "exp": int(time.time()) + 600},                            # no sub
    {"sub": "6f2b8a40-58c1-4d4e-9a3e-5a1a3b7f0c11", "aud": "authenticated"},             # no expiry
])
def test_tokens_missing_required_claims_are_unauthorised(client, claims):
    response = client.get("/api/me", headers=_token(claims))
    assert response.status_code == 401, response.text
    assert "not valid" in response.json()["detail"]


def test_expired_tokens_say_so(client):
    claims = {"sub": "6f2b8a40-58c1-4d4e-9a3e-5a1a3b7f0c11", "aud": "authenticated", "exp": int(time.time()) - 60}
    response = client.get("/api/me", headers=_token(claims))
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_shared_secret_blocks_calls_that_skip_the_frontend(db):
    """Option D hosting: the backend has a public URL, so only requests carrying the frontend's key get
    through. Health stays open for an uptime checker; without the setting nothing changes."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import EMAILS, TEST_SETTINGS

    locked = TestClient(create_app(replace(TEST_SETTINGS, backend_shared_secret="s3cret"), db=db))
    assert locked.get("/api/health").status_code == 200
    assert locked.post("/api/demo/login", json={"email": EMAILS["ben"]}).status_code == 401
    assert locked.post("/api/demo/login", json={"email": EMAILS["ben"]},
                       headers={"x-demo-key": "wrong"}).status_code == 401
    assert locked.post("/api/demo/login", json={"email": EMAILS["ben"]},
                       headers={"x-demo-key": "s3cret"}).status_code == 200
    open_app = TestClient(create_app(TEST_SETTINGS, db=db))
    assert open_app.post("/api/demo/login", json={"email": EMAILS["ben"]}).status_code == 200
