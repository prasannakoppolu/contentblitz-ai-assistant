"""Delivery of one-time sign-in codes.

* **SMTP** when ``SMTP_HOST`` is set (Gmail app password, SendGrid, Mailgun, SES, …).
  Port 465 uses implicit TLS; any other port upgrades with STARTTLS unless
  ``SMTP_STARTTLS=0``.
* **Console** otherwise: the code is written to the server log so the whole flow
  works locally with no email account. Never use console delivery in production.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional, Protocol

logger = logging.getLogger("contentblitz.auth")

SUBJECT = {"login": "Your ContentBlitz sign-in code", "signup": "Confirm your ContentBlitz account"}


class Mailer(Protocol):
    delivery: str

    def send_code(self, to: str, code: str, purpose: str, minutes: int, name: Optional[str] = None) -> None: ...


def render(code: str, purpose: str, minutes: int, name: Optional[str] = None) -> tuple[str, str]:
    """Plain-text and HTML bodies for the code email."""
    action = "finish creating your account" if purpose == "signup" else "sign in"
    hello = f"Hi {name}," if name else "Hi,"
    text = (f"{hello}\n\nYour ContentBlitz code is {code}\n\nEnter it to {action}. It expires in {minutes} minutes.\n"
            "If you didn't ask for this, you can ignore this email.\n")
    html = f"""<!doctype html><html><body style="margin:0;background:#eef1f4;font-family:system-ui,sans-serif;color:#17213d">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="440" cellpadding="0" cellspacing="0"
 style="background:#fff;border:1.5px solid #17213d;border-radius:12px">
<tr><td style="padding:28px 32px">
<p style="margin:0 0 4px;font-weight:700;font-size:20px">ContentBlitz</p>
<p style="margin:0 0 20px;color:#4a5470">{hello} enter this code to {action}.</p>
<p style="margin:0 0 20px;font-size:34px;letter-spacing:10px;font-weight:700;background:#fbefb8;border-radius:8px;
padding:12px 0;text-align:center">{code}</p>
<p style="margin:0;color:#7d8499;font-size:13px">It expires in {minutes} minutes. If you didn't ask for this, ignore this email.</p>
</td></tr></table></td></tr></table></body></html>"""
    return text, html


class ConsoleMailer:
    """Logs the code instead of sending it. For local development and tests."""

    delivery = "console"

    def __init__(self) -> None:
        self.outbox: list[dict] = []  # handy in tests

    def send_code(self, to: str, code: str, purpose: str, minutes: int, name: Optional[str] = None) -> None:
        self.outbox.append({"to": to, "code": code, "purpose": purpose})
        logger.warning("[dev email] %s code for %s: %s (expires in %d min). Set SMTP_HOST to send real email.",
                       purpose, to, code, minutes)


@dataclass
class SMTPMailer:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = "ContentBlitz <no-reply@localhost>"
    starttls: bool = True
    timeout: float = 15.0
    delivery: str = "email"

    def send_code(self, to: str, code: str, purpose: str, minutes: int, name: Optional[str] = None) -> None:
        text, html = render(code, purpose, minutes, name)
        msg = EmailMessage()
        msg["Subject"] = SUBJECT.get(purpose, SUBJECT["login"])
        msg["From"] = self.sender
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ctx) as smtp:
                self._deliver(smtp, msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                if self.starttls:
                    smtp.starttls(context=ctx)
                self._deliver(smtp, msg)
        logger.info("sent %s code to %s via %s", purpose, to, self.host)

    def _deliver(self, smtp: smtplib.SMTP, msg: EmailMessage) -> None:
        if self.username:
            smtp.login(self.username, self.password)
        smtp.send_message(msg)


def mailer_from_env() -> Mailer:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return ConsoleMailer()
    user = os.getenv("SMTP_USER", "").strip()
    return SMTPMailer(
        host=host,
        port=int(os.getenv("SMTP_PORT", "587")),
        username=user,
        password=os.getenv("SMTP_PASSWORD", ""),
        sender=os.getenv("SMTP_FROM", "").strip() or (f"ContentBlitz <{user}>" if "@" in user else "ContentBlitz <no-reply@localhost>"),
        starttls=os.getenv("SMTP_STARTTLS", "1").lower() not in {"0", "false", "no"},
    )
