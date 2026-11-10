"""Contratti di base per gli strumenti di Amy.

Uno strumento dichiara:
- nome e descrizione (italiano);
- schema JSON dei parametri;
- livello di rischio e note per la conferma;
- timeout;
- una funzione di esecuzione che restituisce un risultato verificabile.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..core.logging_setup import get_logger
from ..security.risk import RiskLevel

_log = get_logger("tools")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    risk: RiskLevel = RiskLevel.A
    reason: str = ""
    consequences: str = ""
    undo: str = ""
    timeout_s: float = 20.0
    tags: tuple = ()
    hidden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk": self.risk.value,
            "reason": self.reason,
            "consequences": self.consequences,
            "undo": self.undo,
            "timeout_s": self.timeout_s,
            "tags": list(self.tags),
        }


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    message: str = ""
    error_code: str = ""
    started_at: float = field(default_factory=time.time)
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": self.ok,
            "message": self.message,
            "duration_ms": self.duration_ms,
        }
        if self.data is not None:
            payload["data"] = self.data
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload

    @classmethod
    def success(cls, data: Any = None, message: str = "") -> "ToolResult":
        return cls(ok=True, data=data, message=message)

    @classmethod
    def failure(cls, message: str, *, error_code: str = "tool_error", data: Any = None) -> "ToolResult":
        return cls(ok=False, data=data, message=message, error_code=error_code)


@dataclass
class ToolContext:
    """Dipendenze condivise passate a ogni strumento."""

    config: Any
    memory: Any
    path_guard: Any
    audit: Any
    session_id: str = ""
    robot_link: Any = None
    voice: Any = None
    telegram: Any = None
    logger: Any = None

    def child(self, **overrides: Any) -> "ToolContext":
        values = dict(self.__dict__)
        values.update(overrides)
        return ToolContext(**values)


class Tool:
    spec: ToolSpec

    def run(self, args: Dict[str, Any], context: ToolContext) -> ToolResult:  # pragma: no cover - astratto
        raise NotImplementedError

    # Hook opzionale: rischio dipendente dagli argomenti.
    def risk_for(self, args: Dict[str, Any]) -> RiskLevel:
        return self.spec.risk


class FunctionTool(Tool):
    """Strumento costruito a partire da una funzione."""

    def __init__(self, spec: ToolSpec, func) -> None:
        self.spec = spec
        self._func = func

    def run(self, args: Dict[str, Any], context: ToolContext) -> ToolResult:
        return self._func(args, context)


def run_with_timeout(tool: Tool, args: Dict[str, Any], context: ToolContext) -> ToolResult:
    """Esegue lo strumento in un thread con timeout applicativo.

    Python non può interrompere in modo sicuro un thread bloccato: allo scadere
    del timeout Amy restituisce un errore verificabile e lascia che il thread
    termini da solo. Gli strumenti devono comunque avere timeout interni
    (per esempio ``subprocess.run(timeout=...)``).
    """
    timeout = float(tool.spec.timeout_s or 20.0)
    result_box: Dict[str, Optional[ToolResult]] = {"result": None}
    error_box: Dict[str, BaseException] = {}

    def target() -> None:
        try:
            result_box["result"] = tool.run(args, context)
        except BaseException as exc:  # noqa: BLE001 - incapsuliamo per il chiamante
            error_box["error"] = exc

    started = time.time()
    thread = threading.Thread(target=target, name="amy-tool-%s" % tool.spec.name, daemon=True)
    thread.start()
    thread.join(timeout)
    elapsed_ms = int((time.time() - started) * 1000)

    if thread.is_alive():
        _log.warning("Strumento %s scaduto dopo %.1fs", tool.spec.name, timeout)
        return ToolResult.failure(
            "Lo strumento ha superato il tempo massimo di %.0f secondi." % timeout,
            error_code="timeout",
        )
    if "error" in error_box:
        raise error_box["error"]
    result = result_box["result"]
    if result is None:
        return ToolResult.failure("Lo strumento non ha restituito alcun risultato.", error_code="empty_result")
    result.duration_ms = elapsed_ms
    return result
