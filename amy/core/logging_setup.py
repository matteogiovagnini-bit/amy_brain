"""Logging strutturato e redazione dei segreti.

Amy scrive log leggibili su console e un file rotante. I segreti noti
(variabili d'ambiente con nomi sensibili, token, password) vengono sostituiti
prima di raggiungere qualunque handler.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable

_SECRET_KEY_RE = re.compile(r"(password|passwd|token|secret|api[_-]?key|authorization)", re.I)
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.I)
_SK_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b")


def redact_text(value: str) -> str:
    text = _BEARER_RE.sub(r"\1[REDATTO]", value)
    text = _SK_RE.sub("[REDATTO]", text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDATTO]" if _SECRET_KEY_RE.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    """Filtra i messaggi e gli argomenti prima della formattazione."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                record.args = tuple(redact(arg) for arg in record.args)
        except Exception:
            # Un filtro non deve mai impedire la scrittura del log.
            pass
        return True


class JsonFormatter(logging.Formatter):
    """Formato JSON line, utile per analisi e trasferimento ad altri agenti."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "amy_fields", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))
        return json.dumps(redact(payload), ensure_ascii=False)


def setup_logging(
    *,
    level: str = "INFO",
    log_file: str = "~/.amy/amy.log",
    max_bytes: int = 2_000_000,
    backup_count: int = 3,
    console: bool = True,
) -> logging.Logger:
    root = logging.getLogger("amy")
    if getattr(root, "_amy_configured", False):
        return root

    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    root.propagate = False
    root.handlers.clear()
    redactor = RedactingFilter()

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s  %(message)s", "%H:%M:%S")
        )
        console_handler.addFilter(redactor)
        root.addHandler(console_handler)

    path = Path(log_file).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
    except OSError:
        # La mancanza del file non deve impedire l'avvio della console.
        root.warning("Impossibile aprire il file di log %s", path)

    setattr(root, "_amy_configured", True)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("amy.%s" % name if not name.startswith("amy.") else name)
