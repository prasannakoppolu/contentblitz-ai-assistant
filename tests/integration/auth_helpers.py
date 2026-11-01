"""Helpers for signing test clients in through the real email-code flow."""
from __future__ import annotations

from src.auth import AuthService, AuthStore, ConsoleMailer

ADMIN = "admin@example.com"


def make_auth(**kw) -> AuthService:
    """In-memory store, console mailer (codes land in ``mailer.outbox``), no resend cooldown."""
    kw.setdefault("resend_cooldown_s", 0)
    kw.setdefault("max_sends_per_hour", 100)
    return AuthService(AuthStore(":memory:"), ConsoleMailer(), {ADMIN}, **kw)


def last_code(client) -> str:
    return client.app.state.auth.mailer.outbox[-1]["code"]


def signed_in(client, email: str = "writer@example.com", name: str = "Wren Writer"):
    """Sign up (or log in, if the account exists) and keep the session cookie on the client."""
    if client.post("/api/auth/signup/start", json={"email": email, "name": name}).status_code == 409:
        assert client.post("/api/auth/login/start", json={"email": email}).status_code == 200
        purpose = "login"
    else:
        purpose = "signup"
    r = client.post("/api/auth/verify", json={"email": email, "code": last_code(client), "purpose": purpose})
    assert r.status_code == 200, r.text
    return client
