"""Registro di audit append-only.

Ogni esecuzione di strumento, conferma, rifiuto e evento robotico viene
registrata in JSONL. Il registro non è un sostituto dei log applicativi:
è la traccia verificabile di *chi ha autorizzato cosa*.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.logging_setup import get_logger, redact

_log = get_logger("security.audit")


class AuditLog:
    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch(mode=0o600)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def record(self, event: str, **fields: Any) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
        }
        entry.update(redact(fields))
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                _log.error("Impossibile scrivere l'audit: %s", exc)
        return entry

    def tail(self, limit: int = 50) -> list:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        result = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result


class NullAudit:
    """Audit no-op per test unitari che non devono scrivere su disco."""

    def record(self, event: str, **fields: Any) -> Dict[str, Any]:
        return {"event": event, **fields}

    def tail(self, limit: int = 50) -> list:
        return []
