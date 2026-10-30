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
