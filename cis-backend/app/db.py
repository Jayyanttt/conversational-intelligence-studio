"""SQLite access. Schema is created on startup; connections are per-operation."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    analyst_type TEXT,
    system_prompt TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,      -- 'user' or 'assistant'
    content    TEXT NOT NULL,
    metadata   TEXT,               -- JSON string, assistant messages only
    created_at TEXT NOT NULL       -- server time, ISO-8601
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    # ---- sessions / messages -------------------------------------------------

    def get_session(self, session_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_history(self, session_id: str) -> list[dict]:
        """Stored messages, oldest first, as {role, content, metadata|None}."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        out = []
        for r in rows:
            item = {"role": r["role"], "content": r["content"]}
            if r["role"] == "assistant" and r["metadata"]:
                item["metadata"] = json.loads(r["metadata"])
            out.append(item)
        return out

    def save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        metadata: dict,
        analyst_type: str | None,
        system_prompt: str | None,
    ) -> None:
        """Atomically persist a successful turn (session upsert + user + assistant)."""
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, analyst_type, system_prompt, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    analyst_type = COALESCE(excluded.analyst_type, sessions.analyst_type),
                    system_prompt = excluded.system_prompt,
                    updated_at = excluded.updated_at
                """,
                (session_id, analyst_type, system_prompt, now, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, 'user', ?, NULL, ?)",
                (session_id, user_message, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, 'assistant', ?, ?, ?)",
                (session_id, assistant_reply, json.dumps(metadata), utcnow()),
            )
