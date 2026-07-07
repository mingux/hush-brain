"""SQLite event store. Zero external dependencies, WAL mode (Mission Control style)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    agent   TEXT NOT NULL,
    kind    TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_kind  ON events(kind);
"""


class EventStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def insert(self, ts: float, agent: str, kind: str, payload: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (ts, agent, kind, payload) VALUES (?, ?, ?, ?)",
                (ts, agent, kind, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.commit()
            return cur.lastrowid

    def recent(self, limit: int = 100, agent: str | None = None, kind: str | None = None) -> list[dict]:
        query = "SELECT id, ts, agent, kind, payload FROM events"
        clauses, args = [], []
        if agent:
            clauses.append("agent = ?")
            args.append(agent)
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [
            {"id": r[0], "ts": r[1], "agent": r[2], "kind": r[3], "payload": json.loads(r[4])}
            for r in rows
        ]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def token_totals(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(json_extract(payload, '$.input_tokens')), 0),
                       COALESCE(SUM(json_extract(payload, '$.output_tokens')), 0)
                FROM events WHERE kind = 'llm.call'
                """
            ).fetchone()
        return {"input_tokens": int(row[0]), "output_tokens": int(row[1])}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
