"""Integrazione con la CLI OpenCode 2 (``opencode2``).

Amy non riscrive il codice al posto di OpenCode: gli affida una richiesta in una
sessione persistente, nella cartella di progetto scelta. È un agente esterno e
può modificare file ed eseguire comandi: per questo lo strumento è di livello C
e richiede sempre una conferma esplicita.

Nessuna shell: ``opencode2`` viene avviato con una lista di argomenti, senza
``--auto`` e con un timeout finito.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.errors import AmyError
from ..core.restart import schedule_restart
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


class OpenCodeError(AmyError):
    code = "opencode_error"


def _sessions_path(config) -> Path:
    db = Path(str(config.get("memory.db_path", "~/.amy/amy.db"))).expanduser()
    return db.parent / "opencode_sessions.json"


def _load_sessions(config) -> Dict[str, Any]:
    path = _sessions_path(config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"sessions": {}}


def _save_sessions(config, data: Dict[str, Any]) -> None:
    path = _sessions_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # La sessione resta valida anche se non è possibile ricordarla.
        pass


def _enabled(config) -> bool:
    return bool(config.get("opencode.enabled", False))


def _binary(config) -> str:
    name = str(config.get("opencode.binary", "opencode2") or "opencode2")
    path = shutil.which(name)
    if not path:
        raise OpenCodeError(
            "OpenCode 2 non è installato o non è nel PATH.",
            detail="Installa la CLI gratuita opencode2 e riprova.",
        )
    return path


def _project_dir(value: str, context: ToolContext) -> Path:
    configured = str(context.config.get("opencode.project_dir", "") or "")
    raw = value or configured or os.getcwd()
    return context.path_guard.resolve(raw, must_exist=True)


def _parse_events(stdout: str) -> Dict[str, Any]:
    session_id = ""
    texts: List[str] = []
    cost = 0.0
    tokens: Dict[str, Any] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        sid = event.get("sessionID")
        if sid:
            session_id = str(sid)
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event.get("type") == "text" and part.get("type") == "text":
            text = str(part.get("text", "")).strip()
            if text:
                texts.append(text)
        if event.get("type") == "step_finish":
            cost += float(part.get("cost") or 0)
            if part.get("tokens"):
                tokens = part["tokens"]
    return {
        "session_id": session_id,
        "text": texts[-1] if texts else "",
        "steps_text": len(texts),
        "cost": cost,
        "tokens": tokens,
    }


def run_request(
    request: str,
    *,
    directory: str = "",
    new_session: bool = False,
    title: str = "",
    context: ToolContext,
) -> Dict[str, Any]:
    if not _enabled(context.config):
        raise OpenCodeError(
            "OpenCode è disattivato nella configurazione.",
            detail="Imposta opencode.enabled = true in ~/.amy/config.json.",
        )
    prompt = str(request or "").strip()
    if not prompt:
        raise OpenCodeError("La richiesta per OpenCode è vuota.")
    if len(prompt) > 20000:
        raise OpenCodeError("La richiesta è troppo lunga (massimo 20.000 caratteri).")
    project = _project_dir(directory, context)
    binary = _binary(context.config)

    sessions = _load_sessions(context.config)
    key = str(project)
    existing = sessions["sessions"].get(key, {}) if isinstance(sessions["sessions"].get(key), dict) else {}
    session_id = "" if new_session else str(existing.get("id", "") or "")

    command = [binary, "run", prompt, "--format", "json"]
    if session_id:
        command.extend(["--session", session_id])
    if title:
        command.extend(["--title", str(title)[:120]])
    try:
        timeout = float(context.config.get("opencode.timeout_s", 300))
    except (TypeError, ValueError):
        timeout = 300.0
    timeout = max(30.0, min(timeout, 900.0))

    try:
        completed = subprocess.run(
            command,
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenCodeError(
            "OpenCode non ha terminato entro %d secondi." % int(timeout),
            detail=(exc.stderr or "")[-500:] if exc.stderr else "",
        ) from exc
    except OSError as exc:
        raise OpenCodeError("Impossibile avviare OpenCode.", detail=str(exc)) from exc

    parsed = _parse_events(completed.stdout or "")
    if completed.returncode != 0 and not parsed["text"]:
        raise OpenCodeError(
            "OpenCode è terminato con errore (codice %s)." % completed.returncode,
            detail=(completed.stderr or completed.stdout or "")[-800:],
        )
    if not parsed["session_id"]:
        parsed["session_id"] = session_id
    if parsed["session_id"]:
        sessions["sessions"][key] = {
            "id": parsed["session_id"],
            "directory": key,
            "updated": time.time(),
        }
        _save_sessions(context.config, sessions)

    limit = int(context.config.get("opencode.max_output_chars", 8000) or 8000)
    text = parsed["text"]
    truncated = len(text) > limit
    return {
        "session_id": parsed["session_id"],
        "directory": key,
        "text": text[:limit],
        "truncated": truncated,
        "steps_text": parsed["steps_text"],
        "cost": parsed["cost"],
        "tokens": parsed["tokens"],
        "returncode": completed.returncode,
        "new_session": bool(new_session),
    }


def _run(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = run_request(
        str(args["request"]),
        directory=str(args.get("directory", "") or ""),
        new_session=bool(args.get("new_session", False)),
        title=str(args.get("title", "") or ""),
        context=context,
    )
    if not data["text"]:
        return ToolResult.failure(
            "OpenCode non ha restituito una risposta testuale.",
            data=data,
        )
    if args.get("restart_after"):
        try:
            data["restart"] = schedule_restart(
                float(context.config.get("opencode.restart_delay_s", 12))
            )
        except Exception as exc:  # noqa: BLE001 - il risultato di OpenCode resta valido
            data["restart"] = {"scheduled": False, "error": str(exc)}
    prefix = "Nuova sessione" if data["new_session"] else "Sessione"
    if data.get("restart", {}).get("scheduled"):
        message = "%s OpenCode %s completata. Amy si riavvia tra %d secondi." % (
            prefix,
            data["session_id"] or "?",
            int(data["restart"]["delay_s"]),
        )
    else:
        message = "%s OpenCode %s: risposta pronta." % (prefix, data["session_id"] or "?")
    return ToolResult.success(data, message)


def _status(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    sessions = _load_sessions(context.config)
    project = ""
    try:
        project = str(_project_dir("", context))
    except AmyError:
        project = ""
    return ToolResult.success(
        {
            "enabled": _enabled(context.config),
            "binary": str(context.config.get("opencode.binary", "opencode2")),
            "project_dir": project,
            "sessions": sessions["sessions"],
        },
        "OpenCode %s." % ("attivo" if _enabled(context.config) else "disattivato"),
    )


OPENCODE_RUN = ToolSpec(
    name="opencode.run",
    description=(
        "Affida una richiesta a OpenCode 2 in una sessione persistente nella "
        "cartella di progetto. OpenCode può leggere e modificare file ed eseguire "
        "comandi con i permessi dell'utente: richiede sempre conferma."
    ),
    parameters={
        "type": "object",
        "properties": {
            "request": {"type": "string", "minLength": 1, "maxLength": 20000},
            "directory": {"type": "string", "maxLength": 1000},
            "new_session": {"type": "boolean"},
            "restart_after": {"type": "boolean"},
            "title": {"type": "string", "maxLength": 120},
        },
        "required": ["request"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Un agente esterno può modificare il progetto e il sistema.",
    consequences=(
        "OpenCode lavora nella cartella indicata con i permessi dell'utente: può "
        "creare, modificare o cancellare file ed eseguire comandi. La sessione è "
        "persistente e le richieste successive continuano la stessa conversazione. "
        "Con restart_after=true Amy si riavvia al termine per caricare le modifiche."
    ),
    undo="Nessuno automatico: controlla il risultato e usa Git o i backup del progetto.",
    timeout_s=910.0,
    tags=("opencode", "agente", "progetto"),
)

OPENCODE_STATUS = ToolSpec(
    name="opencode.status",
    description="Mostra lo stato di OpenCode 2 e le sessioni ricordate per cartella.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura della configurazione di OpenCode.",
    timeout_s=30.0,
    tags=("opencode", "agente"),
)


def register(registry) -> None:
    registry.register(FunctionTool(OPENCODE_STATUS, _status))
    registry.register(FunctionTool(OPENCODE_RUN, _run))
