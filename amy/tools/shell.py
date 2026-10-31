"""Esecuzione shell controllata.

Amy non esegue stringhe di shell arbitrarie. Questo strumento espone solo un
insieme chiuso di comandi di **sola lettura**, avviati senza ``shell=True`` e
con una directory di lavoro validata dalla policy dei percorsi.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.errors import ToolValidationError
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec

MAX_OUTPUT = 20000


def _run(argv: List[str], *, cwd: str, timeout: float) -> Tuple[int, str, str]:
    process = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return process.returncode, process.stdout, process.stderr


def _shell_run(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    command = str(args["command"])
    timeout = min(float(context.config.get("security.shell_timeout_s", 20)), 30.0)
    cwd_path = Path(context.path_guard.roots[0])
    target = args.get("path")
    if target:
        cwd_path = context.path_guard.resolve(str(target), must_exist=True)
        if cwd_path.is_file():
            cwd_path = cwd_path.parent

    if command in {"git_status", "git_diff", "git_log"} and not args.get("path"):
        raise ToolValidationError("Per i comandi Git indica la cartella del repository in 'path'.")

    if command == "disk_usage":
        argv = ["df", "-h", str(cwd_path)]
    elif command == "list_directory":
        argv = ["ls", "-la", str(cwd_path)]
    elif command == "git_status":
        argv = ["git", "status", "--short", "--branch"]
    elif command == "git_diff":
        argv = ["git", "diff", "--stat"]
    elif command == "git_log":
        count = int(args.get("limit", 10))
        argv = ["git", "log", "--oneline", "-n", str(count)]
    elif command == "python_version":
        argv = ["python3", "--version"]
    elif command == "uptime":
        argv = ["uptime"]
    elif command == "date":
        argv = ["date"]
    elif command == "whoami":
        argv = ["whoami"]
    elif command == "sw_vers":
        argv = ["sw_vers"]
    elif command == "processes":
        argv = ["ps", "-axo", "pid=,pcpu=,pmem=,comm=", "-r"]
    else:  # pragma: no cover - protetto anche dall'enum dello schema
        raise ToolValidationError("Comando non ammesso: %s" % command)

    try:
        code, stdout, stderr = _run(argv, cwd=str(cwd_path), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return ToolResult.failure(
            "Il comando ha superato il tempo massimo di %.0f secondi." % timeout,
            error_code="timeout",
        )
    except OSError as exc:
        return ToolResult.failure("Impossibile avviare il comando.", error_code="spawn_error", data=str(exc))

    output = stdout
    if command == "processes":
        output = "\n".join(stdout.splitlines()[: int(args.get("limit", 10))])
    truncated = len(output) > MAX_OUTPUT
    if truncated:
        output = output[:MAX_OUTPUT]
    return ToolResult(
        ok=code == 0,
        data={
            "command": command,
            "cwd": str(cwd_path),
            "exit_code": code,
            "stdout": output,
            "stderr": stderr[:4000],
            "troncato": truncated,
        },
        message="Comando completato con codice %d." % code if code == 0 else "Il comando è terminato con errore %d." % code,
        error_code="" if code == 0 else "command_failed",
    )


SHELL_RUN = ToolSpec(
    name="shell.run",
    description=(
        "Esegue uno dei comandi di sola lettura predefiniti (df, ls, git status/diff/log, ps, "
        "sw_vers, date, uptime, whoami, python3 --version). Non accetta stringhe di shell arbitrarie."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": [
                    "disk_usage",
                    "list_directory",
                    "git_status",
                    "git_diff",
                    "git_log",
                    "python_version",
                    "uptime",
                    "date",
                    "whoami",
                    "sw_vers",
                    "processes",
                ],
            },
            "path": {"type": "string", "maxLength": 1000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Esecuzione di un comando predefinito di sola lettura.",
    consequences="Nessuna modifica al sistema; viene solo letto lo stato richiesto.",
    tags=("shell", "sviluppo", "sistema"),
)


def register(registry) -> None:
    registry.register(FunctionTool(SHELL_RUN, _shell_run))
