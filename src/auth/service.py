"""Email + one-time-code authentication.

Flow
----
* **Log in**: ``start_login(email)``. An unknown email raises ``not_registered`` so
  the UI can point the person to sign-up; a known one gets a 6-digit code.
* **Sign up**: ``start_signup(email, name)``. An email that already has an account
  raises ``already_registered``; otherwise a code is sent and the account is
  created only once the code is verified (so nobody can claim an inbox they
  don't control).
* **Verify**: ``verify(email, code, purpose)`` checks the code and returns the
  user plus a new session token for an HttpOnly cookie.

Protections: codes are salted SHA-256 hashes compared in constant time; they
expire after ``code_ttl_s`` (10 min); 5 wrong guesses burn the code; a new code
can be requested every ``resend_cooldown_s`` (30 s) and at most
``max_sends_per_hour`` (5) times an hour per email; sessions last 14 days and
are stored as token hashes.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from src.auth.mailer import ConsoleMailer, Mailer
from src.auth.store import AuthStore

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """An auth failure the UI should show. ``code`` is machine-readable."""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def normalise_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AuthError(422, "invalid_email", "Enter a valid email address, like name@company.com.")
    return email


def _hash_code(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class AuthService:
    store: AuthStore
    mailer: Mailer = field(default_factory=ConsoleMailer)
    admin_emails: Set[str] = field(default_factory=set)
    code_ttl_s: int = 600
    max_attempts: int = 5
    resend_cooldown_s: int = 30
    max_sends_per_hour: int = 5
    session_ttl_s: int = 14 * 86400
    expose_dev_codes: bool = False  # return the code in the API response (console delivery only)

    def __post_init__(self) -> None:
        self.admin_emails = {e.strip().lower() for e in self.admin_emails if e and e.strip()}

    # ----------------------------------------------------------------- public
    def is_admin(self, user: Dict[str, Any]) -> bool:
        return user.get("email", "").lower() in self.admin_emails

    def public_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": user["id"], "email": user["email"], "name": user["name"], "is_admin": self.is_admin(user),
                "created_at": user.get("created_at")}

    def start_login(self, email: str) -> Dict[str, Any]:
        email = normalise_email(email)
        user = self.store.user_by_email(email)
        if not user:
            raise AuthError(404, "not_registered", f"{email} isn't registered with ContentBlitz yet. Sign up to create an account.")
        return self._send(email, "login", user["name"])

    def start_signup(self, email: str, name: str) -> Dict[str, Any]:
        email = normalise_email(email)
        name = re.sub(r"\s+", " ", (name or "").strip())
        if not 1 <= len(name) <= 80:
            raise AuthError(422, "invalid_name", "Enter your name (up to 80 characters).")
        if self.store.user_by_email(email):
            raise AuthError(409, "already_registered", f"{email} already has an account. Log in instead.")
        return self._send(email, "signup", name)

    def verify(self, email: str, code: str, purpose: str) -> Tuple[Dict[str, Any], str]:
        email = normalise_email(email)
        if purpose not in ("login", "signup"):
            raise AuthError(422, "invalid_purpose", "Unknown verification type.")
        code = re.sub(r"\D", "", code or "")
        otp = self.store.get_otp(email, purpose)
        if not otp or otp["expires_at"] < time.time():
            if otp:
                self.store.delete_otp(email, purpose)
            raise AuthError(410, "code_expired", "That code has expired. Request a new one.")
        if otp["attempts"] >= self.max_attempts:
            self.store.delete_otp(email, purpose)
            raise AuthError(429, "too_many_attempts", "Too many wrong codes. Request a new one.")
        if not hmac.compare_digest(otp["code_hash"], _hash_code(code, otp["salt"])):
            self.store.bump_otp_attempts(email, purpose)
            left = self.max_attempts - otp["attempts"] - 1
            if left <= 0:
                self.store.delete_otp(email, purpose)
                raise AuthError(429, "too_many_attempts", "Too many wrong codes. Request a new one.")
            raise AuthError(401, "wrong_code", f"That code isn't right. {left} attempt{'s' if left != 1 else ''} left.",
                            attempts_left=left)
        self.store.delete_otp(email, purpose)

        user = self.store.user_by_email(email)
        if purpose == "signup" and not user:
            user = self.store.create_user(email, otp["name"] or email.split("@")[0])
        if not user:
            raise AuthError(404, "not_registered", f"{email} isn't registered with ContentBlitz yet. Sign up to create an account.")
        self.store.touch_login(user["id"])
        token = secrets.token_urlsafe(32)
        self.store.create_session(hash_token(token), user["id"], self.session_ttl_s)
        return self.store.user_by_id(user["id"]), token  # type: ignore[return-value]

    def user_for_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        return self.store.session_user(hash_token(token)) if token else None

    def logout(self, token: Optional[str]) -> None:
        if token:
            self.store.delete_session(hash_token(token))

    # ---------------------------------------------------------------- private
    def _send(self, email: str, purpose: str, name: Optional[str]) -> Dict[str, Any]:
        now = time.time()
        last = self.store.get_otp(email, purpose)
        if last and now - last["created_at"] < self.resend_cooldown_s:
            wait = int(self.resend_cooldown_s - (now - last["created_at"])) + 1
            raise AuthError(429, "resend_too_soon", f"A code was just sent. You can ask for another in {wait}s.",
                            retry_after=wait)
        if self.store.sends_since(email, now - 3600) >= self.max_sends_per_hour:
            raise AuthError(429, "too_many_codes", "Too many codes requested for this email. Try again in an hour.")
        code = f"{secrets.randbelow(10**6):06d}"
        salt = secrets.token_hex(8)
        try:
            self.mailer.send_code(email, code, purpose, self.code_ttl_s // 60, name)
        except Exception as exc:  # noqa: BLE001 - SMTP failures become a clear message
            raise AuthError(502, "email_failed", "We couldn't send the email. Check the address or try again shortly.") from exc
        self.store.put_otp(email, purpose, _hash_code(code, salt), salt, name if purpose == "signup" else None,
                           self.code_ttl_s)
        out: Dict[str, Any] = {"sent": True, "email": email, "purpose": purpose, "delivery": self.mailer.delivery,
                               "expires_in": self.code_ttl_s, "resend_after": self.resend_cooldown_s}
        if self.expose_dev_codes and self.mailer.delivery == "console":
            out["dev_code"] = code
        return out


def parse_admins(value: Optional[str] | Iterable[str]) -> Set[str]:
    if value is None:
        return set()
    items = value.split(",") if isinstance(value, str) else value
    return {i.strip().lower() for i in items if i and i.strip()}
