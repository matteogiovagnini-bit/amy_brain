"""Strumenti per Promemoria: liste, promemoria, completamento ed eliminazione."""

from __future__ import annotations

from typing import Any, Dict

from ..macos import (
    complete_reminder,
    create_reminder,
    delete_reminder,
    list_reminder_lists,
    list_reminders,
)
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _default_list(context: ToolContext) -> str:
    try:
        return str(context.config.get("reminders.default_list", "") or "")
    except Exception:  # pragma: no cover - configurazione assente nei test
        return ""


def _lists(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    rows = list_reminder_lists()
    return ToolResult.success(
        {"liste": rows, "predefinita": _default_list(context)},
        "Trovate %d liste di promemoria." % len(rows),
    )


def _list(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = list_reminders(
        list_name=str(args.get("list", "") or ""),
        default_list=_default_list(context),
        include_completed=bool(args.get("include_completed", False)),
        limit=int(args.get("limit", 100)),
    )
    count = len(data["reminders"])
    return ToolResult.success(
        data,
        "Nessun promemoria nella lista %s." % data["list"]
        if count == 0
        else "%d promemoria nella lista %s." % (count, data["list"]),
    )


def _create(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = create_reminder(
        name=str(args["name"]),
        due=str(args.get("due", "") or ""),
        list_name=str(args.get("list", "") or ""),
        default_list=_default_list(context),
        notes=str(args.get("notes", "") or ""),
    )
    when = (" per il %s" % data["due"].replace("T", " alle ")) if data["due"] else ""
    data["message"] = "Promemoria «%s» creato%s." % (data["name"], when)
    return ToolResult.success(data, data["message"])


def _complete(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = complete_reminder(
        identifier=str(args["identifier"]),
        list_name=str(args.get("list", "") or ""),
        default_list=_default_list(context),
    )
    return ToolResult.success(data, "Promemoria completato.")


def _delete(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = delete_reminder(
        identifier=str(args["identifier"]),
        list_name=str(args.get("list", "") or ""),
        default_list=_default_list(context),
    )
    return ToolResult.success(data, "Promemoria eliminato.")


REMINDERS_LISTS = ToolSpec(
    name="reminders.lists",
    description="Elenca le liste di Promemoria.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dei nomi delle liste di promemoria.",
    timeout_s=30.0,
    tags=("macos", "promemoria"),
)

REMINDERS_LIST = ToolSpec(
    name="reminders.list",
    description=(
        "Elenca i promemoria di una lista, con scadenza e stato. Per impostazione "
        "predefinita mostra solo quelli da completare."
    ),
    parameters={
        "type": "object",
        "properties": {
            "list": {"type": "string", "maxLength": 100},
            "include_completed": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura dei promemoria dell'utente.",
    timeout_s=30.0,
    consequences="Nessuna modifica: Promemoria viene solo interrogato.",
    tags=("macos", "promemoria"),
)

REMINDERS_CREATE = ToolSpec(
    name="reminders.create",
    description=(
        "Crea un promemoria reale. La scadenza è facoltativa e usa il formato "
        "YYYY-MM-DDTHH:MM."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 300},
            "due": {"type": "string", "maxLength": 40},
            "list": {"type": "string", "maxLength": 100},
            "notes": {"type": "string", "maxLength": 2000},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Scrittura di un promemoria nell'elenco dell'utente.",
    timeout_s=60.0,
    consequences="Il promemoria compare in Promemoria e può sincronizzarsi con gli altri dispositivi.",
    undo="Elimina il promemoria con l'ID indicato nel risultato.",
    tags=("macos", "promemoria", "scrittura"),
)

REMINDERS_COMPLETE = ToolSpec(
    name="reminders.complete",
    description="Segna un promemoria come completato, per ID oppure per nome esatto.",
    parameters={
        "type": "object",
        "properties": {
            "identifier": {"type": "string", "minLength": 1, "maxLength": 300},
            "list": {"type": "string", "maxLength": 100},
        },
        "required": ["identifier"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Modifica dello stato di un promemoria.",
    timeout_s=45.0,
    consequences="Il promemoria viene segnato come completato; resta recuperabile.",
    undo="Imposta di nuovo completed = false dalla app Promemoria.",
    tags=("macos", "promemoria"),
)

REMINDERS_DELETE = ToolSpec(
    name="reminders.delete",
    description="Elimina un promemoria, per ID oppure per nome esatto.",
    parameters={
        "type": "object",
        "properties": {
            "identifier": {"type": "string", "minLength": 1, "maxLength": 300},
            "list": {"type": "string", "maxLength": 100},
        },
        "required": ["identifier"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Cancellazione definitiva di un promemoria.",
    timeout_s=45.0,
    consequences="Il promemoria sparisce da Promemoria e, se sincronizzato, dagli altri dispositivi.",
    undo="Nessuno automatico: il promemoria va ricreato.",
    tags=("macos", "promemoria", "cancellazione"),
)


def register(registry) -> None:
    registry.register(FunctionTool(REMINDERS_LISTS, _lists))
    registry.register(FunctionTool(REMINDERS_LIST, _list))
    registry.register(FunctionTool(REMINDERS_CREATE, _create))
    registry.register(FunctionTool(REMINDERS_COMPLETE, _complete))
    registry.register(FunctionTool(REMINDERS_DELETE, _delete))
