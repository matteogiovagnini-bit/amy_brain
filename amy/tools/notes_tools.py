"""Strumenti per le note personali."""

from __future__ import annotations

from typing import Any, Dict

from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _create(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    note_id = context.memory.add_note(
        str(args["body"]),
        title=str(args.get("title", "") or ""),
        tags=str(args.get("tags", "") or ""),
    )
    return ToolResult.success({"id": note_id}, "Nota creata (ID %d)." % note_id)


def _list(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    notes = context.memory.list_notes(int(args.get("limit", 100)))
    return ToolResult.success(
        {"notes": notes, "count": len(notes)},
        "Ci sono %d note." % len(notes),
    )


def _update(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    if not any(key in args for key in ("title", "body", "tags")):
        raise ValueError("Nessun campo da aggiornare.")
    changed = context.memory.update_note(
        int(args["id"]),
        title=args.get("title"),
        body=args.get("body"),
        tags=args.get("tags"),
    )
    return ToolResult.success(
        {"id": int(args["id"]), "updated": changed},
        "Nota aggiornata." if changed else "Nota non trovata.",
    )


def _delete(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    removed = context.memory.delete_note(int(args["id"]))
    return ToolResult.success(
        {"id": int(args["id"]), "removed": removed},
        "Nota eliminata." if removed else "Nota non trovata.",
    )


NOTES_CREATE = ToolSpec(
    name="notes.create",
    description="Crea una nota con titolo e tag facoltativi.",
    parameters={
        "type": "object",
        "properties": {
            "body": {"type": "string", "minLength": 1, "maxLength": 20000},
            "title": {"type": "string", "maxLength": 200},
            "tags": {"type": "string", "maxLength": 500},
        },
        "required": ["body"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Scrittura di una nota nella memoria locale.",
    undo="Usa notes.delete con l'ID restituito.",
    tags=("personal", "note"),
)

NOTES_LIST = ToolSpec(
    name="notes.list",
    description="Elenca le note, dalla più recente.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura delle note locali.",
    tags=("personal", "note"),
)

NOTES_UPDATE = ToolSpec(
    name="notes.update",
    description="Aggiorna titolo, corpo o tag di una nota.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "maxLength": 200},
            "body": {"type": "string", "maxLength": 20000},
            "tags": {"type": "string", "maxLength": 500},
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Modifica di una nota esistente.",
    tags=("personal", "note"),
)

NOTES_DELETE = ToolSpec(
    name="notes.delete",
    description="Elimina definitivamente una nota.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer", "minimum": 1}},
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Cancellazione definitiva di una nota.",
    consequences="La nota non è recuperabile.",
    tags=("personal", "note", "cancellazione"),
)


def register(registry) -> None:
    registry.register(FunctionTool(NOTES_CREATE, _create))
    registry.register(FunctionTool(NOTES_LIST, _list))
    registry.register(FunctionTool(NOTES_UPDATE, _update))
    registry.register(FunctionTool(NOTES_DELETE, _delete))
