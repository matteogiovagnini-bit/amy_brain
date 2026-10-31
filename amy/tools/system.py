"""Strumenti di informazione sul sistema macOS."""

from __future__ import annotations

from typing import Any, Dict

from ..macos import open_system_settings, system_info, top_processes
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _system_info(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    info = system_info()
    return ToolResult.success(info, "Informazioni di sistema lette.")


def _top_processes(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    rows = top_processes(int(args.get("limit", 10)), sort_by=str(args.get("sort_by", "cpu")))
    return ToolResult.success(
        {"processi": rows, "ordinati_per": args.get("sort_by", "cpu")},
        "Trovati %d processi." % len(rows),
    )


def _open_settings(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    result = open_system_settings(str(args.get("panel", "privacy")))
    return ToolResult.success(result, "Impostazioni di Sistema aperte.")


SYSTEM_INFO = ToolSpec(
    name="system.info",
    description="Legge informazioni sul Mac: versione macOS, architettura, CPU, RAM, disco e utente.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura di informazioni di sistema non sensibili.",
    tags=("macos", "sistema"),
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
    registry.register(FunctionTool(SYSTEM_INFO, _system_info))
    registry.register(FunctionTool(TOP_PROCESSES, _top_processes))
    registry.register(FunctionTool(OPEN_SETTINGS, _open_settings))
