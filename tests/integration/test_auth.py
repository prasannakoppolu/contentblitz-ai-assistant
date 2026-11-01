"""Sign-up, log-in with email codes, sessions, conversation ownership and the admin API."""
from __future__ import annotations

import smtplib

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.auth import AuthService, AuthStore, ConsoleMailer, SMTPMailer, mailer_from_env, parse_admins
from src.auth.mailer import render
from tests.integration.auth_helpers import ADMIN, last_code, make_auth, signed_in


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path))
    return create_app({"app": {"use_mock": True, "max_retries": 0}}, env="test", serve_frontend=False, auth=make_auth())


@pytest.fixture
def anon(app):
    return TestClient(app)


def test_everything_but_health_config_and_auth_needs_a_session(anon):
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/config").status_code == 200
    for method, url in [("get", "/api/auth/me"), ("get", "/api/threads"), ("post", "/api/threads"),
                        ("get", "/api/threads/t/state"), ("get", "/api/admin/overview"),
                        ("get", "/api/images/x.png"), ("get", "/api/threads/t/export/blog/md")]:
        r = getattr(anon, method)(url)
        assert r.status_code == 401 and r.json()["code"] == "not_signed_in", url
    assert anon.post("/api/threads/t/chat", json={"message": "hi"}).status_code == 401


def test_login_with_unregistered_email_says_so(anon):
    r = anon.post("/api/auth/login/start", json={"email": "New.Person@Example.com"})
    assert r.status_code == 404 and r.json()["code"] == "not_registered"
    assert "new.person@example.com isn't registered" in r.json()["detail"]
    assert anon.post("/api/auth/login/start", json={"email": "not-an-email"}).json()["code"] == "invalid_email"


def test_signup_then_login_with_codes(anon):
    r = anon.post("/api/auth/signup/start", json={"email": "Ana@Example.com", "name": "  Ana   Lopez "})
    assert r.status_code == 200 and r.json()["delivery"] == "console" and "dev_code" not in r.json()
    code = last_code(anon)
    assert len(code) == 6 and code.isdigit()
    # The account only exists once the code is confirmed.
    assert anon.post("/api/auth/login/start", json={"email": "ana@example.com"}).status_code == 404
    v = anon.post("/api/auth/verify", json={"email": "ana@example.com", "code": code, "purpose": "signup"})
    assert v.status_code == 200 and v.json()["user"] == {**v.json()["user"], "name": "Ana Lopez", "is_admin": False}
    assert "httponly" in v.headers["set-cookie"].lower() and "samesite=lax" in v.headers["set-cookie"].lower()
    assert anon.get("/api/auth/me").json()["user"]["email"] == "ana@example.com"

    assert anon.post("/api/auth/signup/start", json={"email": "ana@example.com", "name": "Ana"}).json()["code"] == \
        "already_registered"
    anon.post("/api/auth/logout")
    assert anon.get("/api/auth/me").status_code == 401

    assert anon.post("/api/auth/login/start", json={"email": "ana@example.com"}).status_code == 200
    assert anon.post("/api/auth/verify", json={"email": "ana@example.com", "code": last_code(anon)}).status_code == 200
    assert anon.get("/api/auth/me").json()["user"]["name"] == "Ana Lopez"


def test_wrong_codes_are_limited_and_codes_are_single_use(anon):
    signed_in(anon, "bo@example.com", "Bo")
    anon.post("/api/auth/logout")
    anon.post("/api/auth/login/start", json={"email": "bo@example.com"})
    good = last_code(anon)
    bad = "000000" if good != "000000" else "111111"
    r = anon.post("/api/auth/verify", json={"email": "bo@example.com", "code": bad})
    assert r.status_code == 401 and r.json()["attempts_left"] == 4
    for _ in range(3):
        anon.post("/api/auth/verify", json={"email": "bo@example.com", "code": bad})
    assert anon.post("/api/auth/verify", json={"email": "bo@example.com", "code": bad}).json()["code"] == "too_many_attempts"
    # The code is burnt now, even the right one.
    assert anon.post("/api/auth/verify", json={"email": "bo@example.com", "code": good}).json()["code"] == "code_expired"


def test_codes_expire_resends_are_throttled_and_stored_hashed(tmp_path):
    auth = AuthService(AuthStore(tmp_path / "a.sqlite"), ConsoleMailer(), code_ttl_s=-1, resend_cooldown_s=30,
                       max_sends_per_hour=2)
    auth.store.create_user("cy@example.com", "Cy")
    auth.start_login("cy@example.com")
    code = auth.mailer.outbox[-1]["code"]
    row = auth.store.get_otp("cy@example.com", "login")
    assert code not in str(dict(row))  # only a salted hash is stored
    with pytest.raises(Exception) as too_soon:
        auth.start_login("cy@example.com")
    assert too_soon.value.code == "resend_too_soon" and too_soon.value.extra["retry_after"] > 0
    with pytest.raises(Exception) as expired:
        auth.verify("cy@example.com", code, "login")
    assert expired.value.code == "code_expired"
    auth.resend_cooldown_s = 0
    auth.start_login("cy@example.com")
    with pytest.raises(Exception) as hourly:
        auth.start_login("cy@example.com")
    assert hourly.value.code == "too_many_codes"


def test_dev_codes_only_with_console_delivery():
    auth = AuthService(AuthStore(), ConsoleMailer(), expose_dev_codes=True, resend_cooldown_s=0)
    assert auth.start_signup("d@example.com", "D")["dev_code"] == auth.mailer.outbox[-1]["code"]

    class Sent:
        delivery = "email"

        def send_code(self, *a, **k):
            pass

    assert "dev_code" not in AuthService(AuthStore(), Sent(), expose_dev_codes=True).start_signup("e@example.com", "E")


def test_email_failure_is_reported_and_no_code_is_stored():
    class Broken:
        delivery = "email"

        def send_code(self, *a, **k):
            raise smtplib.SMTPException("relay denied")

    auth = AuthService(AuthStore(), Broken())
    with pytest.raises(Exception) as err:
        auth.start_signup("f@example.com", "F")
    assert err.value.code == "email_failed" and auth.store.get_otp("f@example.com", "signup") is None


def test_conversations_belong_to_their_owner(app):
    alice = signed_in(TestClient(app), "alice@example.com", "Alice")
    bob = signed_in(TestClient(app), "bob@example.com", "Bob")
    tid = alice.post("/api/threads").json()["thread_id"]
    alice.post(f"/api/threads/{tid}/chat", json={"message": "Write a LinkedIn post about hybrid work"})
    assert alice.get("/api/threads").json()["threads"][0]["title"] == "Write a LinkedIn post about hybrid work"
    assert bob.get("/api/threads").json()["threads"] == []
    for method, url, body in [("get", f"/api/threads/{tid}/state", None),
                              ("post", f"/api/threads/{tid}/chat", {"message": "hi"}),
                              ("put", f"/api/threads/{tid}/artifacts/linkedin", {"text": "x"}),
                              ("get", f"/api/threads/{tid}/export/linkedin/txt", None),
                              ("patch", f"/api/threads/{tid}", {"title": "mine now"}),
                              ("delete", f"/api/threads/{tid}", None)]:
        kw = {"json": body} if body else {}
        assert getattr(bob, method)(url, **kw).status_code == 404, url
    assert alice.patch(f"/api/threads/{tid}", json={"title": "Hybrid work post"}).json()["title"] == "Hybrid work post"
    assert alice.delete(f"/api/threads/{tid}").json() == {"ok": True}
    assert alice.get("/api/threads").json()["threads"] == []


def test_admin_overview_and_settings_are_admin_only(app):
    customer = signed_in(TestClient(app), "c@example.com", "Cat")
    assert customer.get("/api/admin/overview").status_code == 403
    assert customer.put("/api/admin/settings", json={"demo_mode": False}).status_code == 403

    admin = signed_in(TestClient(app), ADMIN, "Ada Admin")
    assert admin.get("/api/auth/me").json()["user"]["is_admin"] is True
    ov = admin.get("/api/admin/overview").json()
    assert ov["effective"]["demo_mode"] is True and ov["usage"]["offline"] is True
    assert ov["totals"]["users"] == 2 and {u["email"] for u in ov["users"]} == {ADMIN, "c@example.com"}
    assert "openai" in ov["key_providers"] and ov["email_delivery"] == "console"

    r = admin.put("/api/admin/settings", json={"llm_primary": "anthropic", "quality_threshold": 80})
    assert r.status_code == 200
    ov = admin.get("/api/admin/overview").json()
    assert ov["settings"]["quality_threshold"] == 80 and ov["effective"]["quality_threshold"] == 80
    assert ov["fallback_chains"]["llm"][0] == "anthropic"
    assert ov["usage"]["providers"]["llm"] == ["mock"]  # offline mode still serves until keys exist
    assert admin.put("/api/admin/settings", json={"quality_threshold": 10}).status_code == 422

    # Customer chat runs on the admin's server settings.
    tid = customer.post("/api/threads").json()["thread_id"]
    customer.post(f"/api/threads/{tid}/chat", json={"message": "Research hybrid work"})
    assert admin.get("/api/admin/overview").json()["usage"]["calls"] > 0


def test_mailer_from_env_and_email_body(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert isinstance(mailer_from_env(), ConsoleMailer)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    m = mailer_from_env()
    assert isinstance(m, SMTPMailer) and m.port == 465 and m.sender == "ContentBlitz <bot@example.com>"
    text, html = render("123456", "signup", 10, "Ana")
    assert "123456" in text and "finish creating your account" in text and "123456" in html
    assert parse_admins(" A@x.com, ,b@y.com ") == {"a@x.com", "b@y.com"}


def test_smtp_mailer_sends_multipart_message(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = u

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    SMTPMailer("smtp.example.com", 587, "u@example.com", "pw", "CB <u@example.com>").send_code("to@example.com", "654321",
                                                                                               "login", 10)
    msg = sent["msg"]
    assert sent["tls"] and sent["login"] == "u@example.com" and msg["To"] == "to@example.com"
    assert msg["Subject"] == "Your ContentBlitz sign-in code" and msg.is_multipart()
