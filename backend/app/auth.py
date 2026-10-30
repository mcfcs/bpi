"""Authentication: Supabase-style JWTs (HS256 with the project's JWT secret).

In production the frontend signs in with Supabase Auth and sends its access token. In demo mode,
/api/demo/login issues tokens for the seeded synthetic personas.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    role: str
    team_id: str
    team_name: str

    @property
    def is_si(self) -> bool:
        return self.role == "si_analyst"


def issue_token(user_id: str, email: str, secret: str, ttl_seconds: int = 8 * 3600) -> str:
    now = int(time.time())
    claims = {"sub": user_id, "email": email, "role": "authenticated", "aud": "authenticated",
              "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    """Verify signature, audience and expiry. A token must carry `exp` and a UUID `sub` (the user
    id RLS keys on); anything else is rejected as invalid rather than failing later."""
    claims = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated",
                        options={"require": ["exp", "sub"]})
    try:
        uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise jwt.InvalidTokenError("sub is not a user id") from exc
    return claims
