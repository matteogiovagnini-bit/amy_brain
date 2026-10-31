"""Memoria persistente di Amy su SQLite.

Contiene:
- sessioni e messaggi della conversazione;
- fatti e preferenze ricordati dall'utente;
- registro delle attività (esiti degli strumenti);
- eventi robotici ricevuti.

La memoria è locale, ispezionabile, esportabile e cancellabile. Non salva
segreti: gli argomenti vengono redatti prima della scrittura.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logging_setup import redact


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'utente',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT '',
    tool TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '{}',
    risk TEXT NOT NULL DEFAULT 'A',
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_started ON activities(started_at);
CREATE TABLE IF NOT EXISTS robot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
"""


class MemoryStore:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '1')"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ sessioni
    def create_session(self, title: str = "") -> str:
        session_id = "ses_" + uuid.uuid4().hex[:20]
        now = utc_now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions(id, title, created_at, updated_at) VALUES(?,?,?,?)",
                (session_id, title[:200], now, now),
            )
            self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def latest_session(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_session_summary(self, session_id: str, summary: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET summary=?, updated_at=? WHERE id=?",
                (summary[:4000], utc_now(), session_id),
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            self._conn.commit()

    # ------------------------------------------------------------------ messaggi
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = utc_now()
        payload = json.dumps(redact(meta or {}), ensure_ascii=False)
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at, meta) VALUES(?,?,?,?,?)",
                (session_id, role, content, now, payload),
            )
            self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
            self._conn.commit()
            return int(cursor.lastrowid)

    def history(self, session_id: str, limit: int = 24) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, created_at, meta FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_history(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            self._conn.commit()

    def message_count(self, session_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)
            ).fetchone()
        return int(row[0]) if row else 0

    # -------------------------------------------------------------------- fatti
    def set_fact(self, key: str, value: str, source: str = "utente") -> None:
        key = key.strip()[:200]
        if not key:
            raise ValueError("La chiave del fatto non può essere vuota.")
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO facts(key, value, source, created_at, updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    source=excluded.source, updated_at=excluded.updated_at
                """,
                (key, str(value)[:4000], source[:100], now, now),
            )
            self._conn.commit()

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM facts WHERE key=?", (key.strip(),)).fetchone()
        return dict(row) if row else None

    def list_facts(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (max(1, int(limit)),)
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_fact(self, key: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM facts WHERE key=?", (key.strip(),))
            self._conn.commit()
            return cursor.rowcount > 0

    # ----------------------------------------------------------------- attività
    def start_activity(
        self,
        *,
        session_id: str,
        tool: str,
        args: Dict[str, Any],
        risk: str,
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO activities(session_id, tool, args, risk, status, started_at) VALUES(?,?,?,?,?,?)",
                (
                    session_id,
                    tool,
                    json.dumps(redact(args), ensure_ascii=False),
                    risk,
                    "in_corso",
                    utc_now(),
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def finish_activity(self, activity_id: int, *, status: str, result: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE activities SET status=?, result=?, finished_at=? WHERE id=?",
                (
                    status,
                    json.dumps(redact(result), ensure_ascii=False)[:20000],
                    utc_now(),
                    activity_id,
                ),
            )
            self._conn.commit()

    def list_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM activities ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            for key in ("args", "result"):
                try:
                    item[key] = json.loads(item[key])
                except (TypeError, json.JSONDecodeError):
                    pass
            output.append(item)
        return output

    # -------------------------------------------------------------- eventi robot
    def record_robot_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO robot_events(ts, type, payload) VALUES(?,?,?)",
                (utc_now(), event_type, json.dumps(redact(payload), ensure_ascii=False)[:20000]),
            )
            self._conn.commit()

    def list_robot_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM robot_events ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except (TypeError, json.JSONDecodeError):
                pass
            output.append(item)
        return output

    # ------------------------------------------------------------------ servizio
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            messages = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            activities = self._conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            facts = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            sessions = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {
            "sessions": sessions,
            "messages": messages,
            "activities": activities,
            "facts": facts,
            "db_path": str(self.path),
        }

    def export_all(self) -> Dict[str, Any]:
        return {
            "sessions": self.list_sessions(1000),
            "facts": self.list_facts(1000),
            "activities": self.list_activities(1000),
            "robot_events": self.list_robot_events(1000),
            "stats": self.stats(),
        }
