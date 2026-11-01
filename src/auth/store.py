"""SQLite persistence for accounts, one-time codes, sessions, conversation ownership
and the admin's server settings.

One small file (``CONTENTBLITZ_AUTH_DB``, default ``data/contentblitz_auth.sqlite``)
keeps everything the auth layer needs. Secrets are never stored in the clear:
one-time codes are salted SHA-256 hashes and session tokens are stored as hashes,
so a copy of the database can't be used to log in.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    last_login  REAL
);
CREATE TABLE IF NOT EXISTS otps (
    email       TEXT NOT NULL,
    purpose     TEXT NOT NULL,            -- 'login' | 'signup'
    code_hash   TEXT NOT NULL,
    salt        TEXT NOT NULL,
    name        TEXT,                     -- sign-up only: the name to create the account with
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, purpose)
);
CREATE TABLE IF NOT EXISTS otp_sends (
    email       TEXT NOT NULL,
    sent_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    thread_id   TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS threads_by_user ON threads(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS kv (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


class AuthStore:
    """Thread-safe wrapper around one SQLite connection."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # ------------------------------------------------------------------ helpers
    def _one(self, sql: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _write(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.lastrowid or cur.rowcount

    # -------------------------------------------------------------------- users
    def user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM users WHERE email = ?", (email,))

    def user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM users WHERE id = ?", (user_id,))

    def create_user(self, email: str, name: str) -> Dict[str, Any]:
        self._write("INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)", (email, name, time.time()))
        return self.user_by_email(email)  # type: ignore[return-value]

    def touch_login(self, user_id: int) -> None:
        self._write("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), user_id))

    def list_users(self) -> List[Dict[str, Any]]:
        return self._all("""SELECT u.id, u.email, u.name, u.created_at, u.last_login,
                                   COUNT(t.thread_id) AS conversations
                            FROM users u LEFT JOIN threads t ON t.user_id = u.id
                            GROUP BY u.id ORDER BY u.created_at DESC""")

    # --------------------------------------------------------------------- otps
    def put_otp(self, email: str, purpose: str, code_hash: str, salt: str, name: Optional[str], ttl_s: float) -> None:
        now = time.time()
        self._write("""INSERT OR REPLACE INTO otps (email, purpose, code_hash, salt, name, created_at, expires_at, attempts)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0)""", (email, purpose, code_hash, salt, name, now, now + ttl_s))
        self._write("INSERT INTO otp_sends (email, sent_at) VALUES (?, ?)", (email, now))
        self._write("DELETE FROM otp_sends WHERE sent_at < ?", (now - 86400,))

    def get_otp(self, email: str, purpose: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM otps WHERE email = ? AND purpose = ?", (email, purpose))

    def bump_otp_attempts(self, email: str, purpose: str) -> None:
        self._write("UPDATE otps SET attempts = attempts + 1 WHERE email = ? AND purpose = ?", (email, purpose))

    def delete_otp(self, email: str, purpose: str) -> None:
        self._write("DELETE FROM otps WHERE email = ? AND purpose = ?", (email, purpose))

    def sends_since(self, email: str, since: float) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM otp_sends WHERE email = ? AND sent_at >= ?", (email, since))
        return int(row["n"]) if row else 0

    # ----------------------------------------------------------------- sessions
    def create_session(self, token_hash: str, user_id: int, ttl_s: float) -> None:
        now = time.time()
        self._write("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token_hash, user_id, now, now + ttl_s))
        self._write("DELETE FROM sessions WHERE expires_at < ?", (now,))

    def session_user(self, token_hash: str) -> Optional[Dict[str, Any]]:
        return self._one("""SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                            WHERE s.token_hash = ? AND s.expires_at > ?""", (token_hash, time.time()))

    def delete_session(self, token_hash: str) -> None:
        self._write("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # ------------------------------------------------------------------ threads
    def thread_owner(self, thread_id: str) -> Optional[int]:
        row = self._one("SELECT user_id FROM threads WHERE thread_id = ?", (thread_id,))
        return int(row["user_id"]) if row else None

    def claim_thread(self, thread_id: str, user_id: int, title: str = "") -> None:
        now = time.time()
        self._write("INSERT OR IGNORE INTO threads (thread_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (thread_id, user_id, title, now, now))

    def touch_thread(self, thread_id: str, title_if_empty: str = "") -> None:
        self._write("""UPDATE threads SET updated_at = ?,
                              title = CASE WHEN title = '' THEN ? ELSE title END
                       WHERE thread_id = ?""", (time.time(), title_if_empty, thread_id))

    def rename_thread(self, thread_id: str, title: str) -> None:
        self._write("UPDATE threads SET title = ? WHERE thread_id = ?", (title, thread_id))

    def delete_thread(self, thread_id: str) -> None:
        self._write("DELETE FROM threads WHERE thread_id = ?", (thread_id,))

    def threads_for(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        return self._all("""SELECT thread_id, title, created_at, updated_at FROM threads
                            WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?""", (user_id, limit))

    def count_threads(self) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM threads")
        return int(row["n"]) if row else 0

    # ----------------------------------------------------------------------- kv
    def get_json(self, key: str, default: Any = None) -> Any:
        row = self._one("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else default

    def set_json(self, key: str, value: Any) -> None:
        self._write("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value)))
