"""Strumenti per le attività personali (task)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _due(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Scadenza non valida: usa YYYY-MM-DD o YYYY-MM-DDTHH:MM.") from exc
    return text


def _create(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    task_id = context.memory.add_task(
        str(args["title"]),
        priority=str(args.get("priority", "normale") or "normale"),
        due_at=_due(args.get("due_at")),
        list_name=str(args.get("list", "") or ""),
    )
    return ToolResult.success(
        {"id": task_id, "title": str(args["title"])},
        "Attività creata (ID %d)." % task_id,
    )


def _list(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    tasks = context.memory.list_tasks(
        status=str(args.get("status", "") or "") or None,
        list_name=str(args.get("list", "") or "") or None,
        limit=int(args.get("limit", 100)),
    )
    return ToolResult.success(
        {"tasks": tasks, "count": len(tasks)},
        "Ci sono %d attività." % len(tasks),
    )


def _update(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    fields = {}
    for key in ("title", "status", "priority", "list_name"):
        if key in args and args[key] is not None:
            fields[key] = args[key]
    if "due_at" in args:
        fields["due_at"] = _due(args.get("due_at"))
    if not fields:
        raise ValueError("Nessun campo da aggiornare.")
    changed = context.memory.update_task(int(args["id"]), **fields)
    return ToolResult.success(
        {"id": int(args["id"]), "updated": changed},
        "Attività aggiornata." if changed else "Attività non trovata.",
    )


def _complete(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    changed = context.memory.complete_task(int(args["id"]))
    return ToolResult.success(
        {"id": int(args["id"]), "completed": changed},
        "Attività completata." if changed else "Attività non trovata.",
    )


def _delete(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    removed = context.memory.delete_task(int(args["id"]))
    return ToolResult.success(
        {"id": int(args["id"]), "removed": removed},
        "Attività eliminata." if removed else "Attività non trovata.",
    )


TASKS_CREATE = ToolSpec(
    name="tasks.create",
    description="Crea un'attività con priorità, scadenza facoltativa e lista.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 300},
            "priority": {"type": "string", "enum": ["bassa", "normale", "alta"]},
            "due_at": {"type": "string", "maxLength": 40},
            "list": {"type": "string", "maxLength": 100},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Scrittura di un'attività nella memoria locale.",
    consequences="L'attività resta nel database locale finché non viene eliminata.",
    undo="Usa tasks.delete con l'ID restituito.",
    tags=("personal", "task"),
)

TASKS_LIST = ToolSpec(
    name="tasks.list",
    description="Elenca le attività, con filtro per stato e lista.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "maxLength": 30},
            "list": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura delle attività locali.",
    tags=("personal", "task"),
)

TASKS_UPDATE = ToolSpec(
    name="tasks.update",
    description="Aggiorna titolo, priorità, scadenza, lista o stato di un'attività.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "maxLength": 300},
            "priority": {"type": "string", "enum": ["bassa", "normale", "alta"]},
            "due_at": {"type": "string", "maxLength": 40},
            "list": {"type": "string", "maxLength": 100},
            "status": {"type": "string", "maxLength": 30},
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Modifica di un'attività esistente.",
    tags=("personal", "task"),
)

TASKS_COMPLETE = ToolSpec(
    name="tasks.complete",
    description="Segna un'attività come completata.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer", "minimum": 1}},
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Modifica dello stato di un'attività.",
    tags=("personal", "task"),
)

TASKS_DELETE = ToolSpec(
    name="tasks.delete",
    description="Elimina definitivamente un'attività.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer", "minimum": 1}},
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Cancellazione definitiva di un'attività.",
    consequences="L'attività non è recuperabile.",
    tags=("personal", "task", "cancellazione"),
)


def register(registry) -> None:
    registry.register(FunctionTool(TASKS_CREATE, _create))
    registry.register(FunctionTool(TASKS_LIST, _list))
    registry.register(FunctionTool(TASKS_UPDATE, _update))
    registry.register(FunctionTool(TASKS_COMPLETE, _complete))
    registry.register(FunctionTool(TASKS_DELETE, _delete))
