"""Strumenti di informazione sul sistema macOS."""

from __future__ import annotations

from typing import Any, Dict

from ..core.restart import schedule_restart
from ..macos import battery_status, battery_summary, open_system_settings, system_info, top_processes
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _system_info(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    info = system_info()
    return ToolResult.success(info, "Informazioni di sistema lette.")


def _battery(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    """Legge lo stato della batteria del Mac (comando di sola lettura)."""
    data = battery_status()
    return ToolResult.success(data, battery_summary(data))


def _top_processes(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    rows = top_processes(int(args.get("limit", 10)), sort_by=str(args.get("sort_by", "cpu")))
    return ToolResult.success(
        {"processi": rows, "ordinati_per": args.get("sort_by", "cpu")},
        "Trovati %d processi." % len(rows),
    )


def _restart(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = schedule_restart(float(args.get("delay_s", 10)))
    data["message"] = "Riavvio di Amy programmato tra %d secondi." % data["delay_s"]
    return ToolResult.success(data, data["message"])


def _open_settings(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    result = open_system_settings(str(args.get("panel", "privacy")))
    return ToolResult.success(result, "Impostazioni di Sistema aperte.")


APP_RESTART = ToolSpec(
    name="app.restart",
    description=(
        "Chiude e riapre l'app nativa Amy Core, per caricare modifiche al codice. "
        "La sessione e la memoria restano. Richiede sempre conferma."
    ),
    parameters={
        "type": "object",
        "properties": {"delay_s": {"type": "number", "minimum": 1, "maximum": 60}},
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Riavvio dell'assistente: interrompe la conversazione in corso.",
    consequences=(
        "Amy si chiude e si riapre dopo il ritardo indicato. La sessione SQLite e le "
        "impostazioni restano; un'operazione in corso viene interrotta."
    ),
    undo="Nessuno automatico: se il riavvio fallisce, riapri Amy Core a mano.",
    timeout_s=15.0,
    tags=("app", "riavvio"),
)

SYSTEM_INFO = ToolSpec(
    name="system.info",
    description="Legge informazioni sul Mac: versione macOS, architettura, CPU, RAM, disco e utente.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura di informazioni di sistema non sensibili.",
    tags=("macos", "sistema"),
)

BATTERY = ToolSpec(
    name="system.battery",
    description=(
        "Legge lo stato della batteria del Mac: percentuale di carica, "
        "carica o scarica e tempo residuo stimato."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dello stato della batteria del computer.",
    consequences="Nessuna: il comando `pmset -g batt` è di sola lettura.",
    undo="Non serve: nessuna modifica viene effettuata.",
    tags=("macos", "sistema", "energia"),
)

TOP_PROCESSES = ToolSpec(
    name="system.processes",
    description="Elenca i processi che usano più CPU o memoria.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            "sort_by": {"type": "string", "enum": ["cpu", "memory"]},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura dell'elenco processi.",
    tags=("macos", "sistema"),
)

OPEN_SETTINGS = ToolSpec(
    name="system.settings",
    description="Apre il pannello pertinente di Impostazioni di Sistema per guidare l'utente sui permessi.",
    parameters={
        "type": "object",
        "properties": {
            "panel": {
                "type": "string",
                "enum": ["privacy", "automation", "accessibility", "microphone", "sound", "network"],
            }
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Apre un pannello di impostazioni, senza modificare permessi.",
    tags=("macos", "permessi"),
)


def register(registry) -> None:
    registry.register(FunctionTool(APP_RESTART, _restart))
    registry.register(FunctionTool(SYSTEM_INFO, _system_info))
    registry.register(FunctionTool(BATTERY, _battery))
    registry.register(FunctionTool(TOP_PROCESSES, _top_processes))
    registry.register(FunctionTool(OPEN_SETTINGS, _open_settings))
