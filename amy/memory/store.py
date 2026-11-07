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
CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'utente',
    confidence REAL NOT NULL DEFAULT 0.5,
    verified INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE(category, key)
);
CREATE INDEX IF NOT EXISTS idx_memory_items_category ON memory_items(category, updated_at);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aperta',
    priority TEXT NOT NULL DEFAULT 'normale',
    due_at TEXT,
    list_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
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
            self._migrate_facts()
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
        # I fatti restano la tabella storica; memory_items è la vista estesa.
        self.set_memory(
            "personal",
            key,
            value,
            source=source,
            confidence=1.0,
            verified=True,
        )

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
            self._conn.execute(
                "DELETE FROM memory_items WHERE category='personal' AND key=?",
                (key.strip(),),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def _migrate_facts(self) -> None:
        """Copia i fatti esistenti in memory_items una sola volta."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        try:
            version = int(row[0]) if row else 1
        except (TypeError, ValueError):
            version = 1
        if version >= 2:
            return
        rows = self._conn.execute("SELECT * FROM facts").fetchall()
        for item in rows:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO memory_items(
                    category, key, value, source, confidence, verified, tags,
                    created_at, updated_at, expires_at
                ) VALUES('personal', ?, ?, ?, 1.0, 1, '', ?, ?, NULL)
                """,
                (
                    item["key"],
                    item["value"],
                    item["source"],
                    item["created_at"],
                    item["updated_at"],
                ),
            )
        self._conn.execute("UPDATE meta SET value='2' WHERE key='schema_version'")

    # ------------------------------------------------------------ memoria estesa
    def set_memory(
        self,
        category: str,
        key: str,
        value: str,
        *,
        source: str = "utente",
        confidence: float = 0.5,
        verified: bool = False,
        tags: str = "",
        expires_at: Optional[str] = None,
    ) -> None:
        category = str(category or "personal").strip()[:50] or "personal"
        key = str(key or "").strip()[:200]
        if not key:
            raise ValueError("La chiave della memoria non può essere vuota.")
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memory_items(
                    category, key, value, source, confidence, verified, tags,
                    created_at, updated_at, expires_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value=excluded.value,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    verified=excluded.verified,
                    tags=excluded.tags,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (
                    category,
                    key,
                    str(value)[:8000],
                    str(source)[:100],
                    max(0.0, min(float(confidence), 1.0)),
                    1 if verified else 0,
                    str(tags or "")[:500],
                    now,
                    now,
                    expires_at,
                ),
            )
            self._conn.commit()

    def get_memory(self, category: str, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_items WHERE category=? AND key=?",
                (str(category), str(key).strip()),
            ).fetchone()
        return dict(row) if row else None

    def list_memories(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        *,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if category:
            clauses.append("category=?")
            params.append(str(category))
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(utc_now())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, min(int(limit), 1000)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_items" + where + " ORDER BY updated_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_memories(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        limit: int = 50,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        needle = "%" + str(query or "").strip() + "%"
        clauses = ["(key LIKE ? OR value LIKE ? OR tags LIKE ?)"]
        params: List[Any] = [needle, needle, needle]
        if category:
            clauses.append("category=?")
            params.append(str(category))
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(utc_now())
        params.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_items WHERE "
                + " AND ".join(clauses)
                + " ORDER BY verified DESC, updated_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_memory(
        self,
        category: str,
        key: str,
        *,
        value: Optional[str] = None,
        tags: Optional[str] = None,
        verified: Optional[bool] = None,
        confidence: Optional[float] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        fields = []
        params: List[Any] = []
        if value is not None:
            fields.append("value=?")
            params.append(str(value)[:8000])
        if tags is not None:
            fields.append("tags=?")
            params.append(str(tags)[:500])
        if verified is not None:
            fields.append("verified=?")
            params.append(1 if verified else 0)
        if confidence is not None:
            fields.append("confidence=?")
            params.append(max(0.0, min(float(confidence), 1.0)))
        if expires_at is not None:
            fields.append("expires_at=?")
            params.append(expires_at)
        if not fields:
            return False
        fields.append("updated_at=?")
        params.append(utc_now())
        params.extend([str(category), str(key).strip()])
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE memory_items SET " + ", ".join(fields) + " WHERE category=? AND key=?",
                tuple(params),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_memory(self, category: str, key: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM memory_items WHERE category=? AND key=?",
                (str(category), str(key).strip()),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def memory_categories(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT category, COUNT(*) AS count FROM memory_items GROUP BY category ORDER BY category"
            ).fetchall()
        return [{"category": row["category"], "count": int(row["count"])} for row in rows]

    # ------------------------------------------------------------ task e note
    def add_task(
        self,
        title: str,
        *,
        priority: str = "normale",
        due_at: Optional[str] = None,
        list_name: str = "",
        status: str = "aperta",
    ) -> int:
        title = str(title or "").strip()[:300]
        if not title:
            raise ValueError("Il titolo del task non può essere vuoto.")
        now = utc_now()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO tasks(title, status, priority, due_at, list_name, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    title,
                    str(status)[:30],
                    str(priority)[:30],
                    due_at,
                    str(list_name)[:100],
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        list_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if status:
            clauses.append("status=?")
            params.append(str(status))
        if list_name:
            clauses.append("list_name=?")
            params.append(str(list_name))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, min(int(limit), 1000)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks" + where + " ORDER BY "
                "CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: int, **fields: Any) -> bool:
        allowed = {"title", "status", "priority", "due_at", "list_name", "completed_at"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return False
        values["updated_at"] = utc_now()
        assignments = ", ".join("%s=?" % key for key in values)
        params = list(values.values()) + [int(task_id)]
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE tasks SET " + assignments + " WHERE id=?", tuple(params)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def complete_task(self, task_id: int) -> bool:
        return self.update_task(
            task_id,
            status="completata",
            completed_at=utc_now(),
        )

    def delete_task(self, task_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM tasks WHERE id=?", (int(task_id),))
            self._conn.commit()
            return cursor.rowcount > 0

    def add_note(self, body: str, *, title: str = "", tags: str = "") -> int:
        body = str(body or "").strip()[:20000]
        if not body:
            raise ValueError("La nota è vuota.")
        now = utc_now()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO notes(title, body, tags, created_at, updated_at) VALUES(?,?,?,?,?)",
                (str(title or "")[:200], body, str(tags or "")[:500], now, now),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_notes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notes ORDER BY updated_at DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_note(self, note_id: int, *, title: Optional[str] = None, body: Optional[str] = None, tags: Optional[str] = None) -> bool:
        fields = []
        params: List[Any] = []
        if title is not None:
            fields.append("title=?")
            params.append(str(title)[:200])
        if body is not None:
            fields.append("body=?")
            params.append(str(body)[:20000])
        if tags is not None:
            fields.append("tags=?")
            params.append(str(tags)[:500])
        if not fields:
            return False
        fields.append("updated_at=?")
        params.append(utc_now())
        params.append(int(note_id))
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE notes SET " + ", ".join(fields) + " WHERE id=?", tuple(params)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_note(self, note_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM notes WHERE id=?", (int(note_id),))
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
            memory_items = self._conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
            tasks = self._conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            notes = self._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            categories = self._conn.execute("SELECT COUNT(DISTINCT category) FROM memory_items").fetchone()[0]
            sessions = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {
            "sessions": sessions,
            "messages": messages,
            "activities": activities,
            "facts": facts,
            "memory_items": memory_items,
            "memory_categories": categories,
            "tasks": tasks,
            "notes": notes,
            "db_path": str(self.path),
        }

    def export_all(self) -> Dict[str, Any]:
        return {
            "sessions": self.list_sessions(1000),
            "facts": self.list_facts(1000),
            "memory_items": self.list_memories(limit=1000, include_expired=True),
            "tasks": self.list_tasks(limit=1000),
            "notes": self.list_notes(limit=1000),
            "activities": self.list_activities(1000),
            "robot_events": self.list_robot_events(1000),
            "stats": self.stats(),
        }
