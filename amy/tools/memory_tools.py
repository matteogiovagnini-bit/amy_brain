"""Strumenti di memoria: fatti e preferenze controllabili dall'utente."""

from __future__ import annotations

from typing import Any, Dict

from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _remember(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    key = str(args["key"]).strip()
    value = str(args["value"]).strip()
    context.memory.set_fact(key, value, source="utente")
    return ToolResult.success(
        {"key": key, "value": value},
        "Ho memorizzato «%s»." % key,
    )


def _forget(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    key = str(args["key"]).strip()
    removed = context.memory.delete_fact(key)
    return ToolResult.success(
        {"key": key, "removed": removed},
        "Ho rimosso «%s» dalla memoria." % key if removed else "Non avevo memorizzato «%s»." % key,
    )


def _list_memories(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    facts = context.memory.list_facts(int(args.get("limit", 50)))
    return ToolResult.success(
        {"fatti": [{"key": item["key"], "value": item["value"], "updated_at": item["updated_at"]} for item in facts]},
        "Ci sono %d elementi in memoria." % len(facts),
    )


REMEMBER = ToolSpec(
    name="memory.remember",
    description="Salva un fatto o una preferenza duratura sull'utente (per esempio: città, stile di risposta, progetto preferito).",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "minLength": 1, "maxLength": 200},
            "value": {"type": "string", "minLength": 1, "maxLength": 4000},
        },
        "required": ["key", "value"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Salvataggio di una preferenza o di un fatto indicato dall'utente.",
    consequences="Il dato resta nella memoria locale finché non viene eliminato.",
    undo="Usa memory.forget con la stessa chiave.",
    tags=("memoria",),
)

FORGET = ToolSpec(
    name="memory.forget",
    description="Elimina un fatto o una preferenza dalla memoria locale.",
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["key"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Rimozione di un dato di memoria richiesta dall'utente.",
    consequences="Il fatto non sarà più disponibile nelle conversazioni future.",
    tags=("memoria",),
)

LIST_MEMORIES = ToolSpec(
    name="memory.list",
    description="Elenca i fatti e le preferenze salvati nella memoria locale.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura della memoria locale.",
    tags=("memoria",),
)


def register(registry) -> None:
    registry.register(FunctionTool(REMEMBER, _remember))
    registry.register(FunctionTool(FORGET, _forget))
    registry.register(FunctionTool(LIST_MEMORIES, _list_memories))
