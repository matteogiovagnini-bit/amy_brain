"""Strumenti per Calendar.app: elenco calendari, eventi e creazione appuntamenti."""

from __future__ import annotations

from typing import Any, Dict

from ..macos import create_event, delete_event, list_calendars, list_events
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _default_calendar(context: ToolContext) -> str:
    try:
        return str(context.config.get("calendar.default_name", "Calendario") or "Calendario")
    except Exception:  # pragma: no cover - configurazione assente nei test
        return "Calendario"


def _list_calendars(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    rows = list_calendars()
    writable = [row for row in rows if row["writable"]]
    return ToolResult.success(
        {"calendari": rows, "scrivibili": len(writable), "predefinito": _default_calendar(context)},
        "Trovati %d calendari, %d scrivibili." % (len(rows), len(writable)),
    )


def _list_events(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = list_events(
        date=str(args["date"]),
        calendar_name=str(args.get("calendar", "") or ""),
        default_calendar=_default_calendar(context),
    )
    count = len(data["events"])
    return ToolResult.success(
        data,
        "Nessun evento il %s." % data["date"]
        if count == 0
        else "%d eventi il %s." % (count, data["date"]),
    )


def _delete_event(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = delete_event(
        uid=str(args.get("uid", "") or ""),
        title=str(args.get("title", "") or ""),
        date=str(args.get("date", "") or ""),
        calendar_name=str(args.get("calendar", "") or ""),
        default_calendar=_default_calendar(context),
    )
    return ToolResult.success(data, "Evento eliminato dal calendario %s." % data["calendar"])


def _create_event(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = create_event(
        title=str(args["title"]),
        start=str(args["start"]),
        duration_minutes=int(args.get("duration_minutes", 60)),
        calendar_name=str(args.get("calendar", "") or ""),
        default_calendar=_default_calendar(context),
        notes=str(args.get("notes", "") or ""),
        location=str(args.get("location", "") or ""),
        all_day=bool(args.get("all_day", False)),
    )
    when = data["start"].replace("T", " alle ")
    data["message"] = "Appuntamento «%s» creato per il %s." % (data["title"], when)
    return ToolResult.success(data, data["message"])


CALENDAR_LIST = ToolSpec(
    name="calendar.list",
    description="Elenca i calendari di Calendar e indica quali sono scrivibili.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dei nomi dei calendari locali.",
    timeout_s=30.0,
    tags=("macos", "calendario"),
)

CALENDAR_EVENTS = ToolSpec(
    name="calendar.events",
    description=(
        "Elenca gli eventi di un giorno in un calendario. Usa una data nel formato "
        "YYYY-MM-DD."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {"type": "string", "minLength": 8, "maxLength": 40},
            "calendar": {"type": "string", "maxLength": 100},
        },
        "required": ["date"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura degli eventi del calendario.",
    timeout_s=30.0,
    consequences="Nessuna modifica: Calendar viene solo interrogato.",
    tags=("macos", "calendario"),
)

CALENDAR_CREATE = ToolSpec(
    name="calendar.create",
    description=(
        "Crea un appuntamento reale in Calendar.app. La data di inizio usa il formato "
        "YYYY-MM-DDTHH:MM e la durata è in minuti."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "start": {"type": "string", "minLength": 8, "maxLength": 40},
            "duration_minutes": {"type": "integer", "minimum": 5, "maximum": 1440},
            "calendar": {"type": "string", "maxLength": 100},
            "notes": {"type": "string", "maxLength": 2000},
            "location": {"type": "string", "maxLength": 300},
            "all_day": {"type": "boolean"},
        },
        "required": ["title", "start"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Scrittura di un evento nel calendario dell'utente.",
    timeout_s=45.0,
    consequences=(
        "L'evento compare in Calendar e può sincronizzarsi con gli altri dispositivi "
        "collegati allo stesso account."
    ),
    undo="Elimina l'evento con l'UID indicato nel risultato.",
    tags=("macos", "calendario", "scrittura"),
)




CALENDAR_DELETE = ToolSpec(
    name="calendar.delete",
    description=(
        "Elimina un evento dal calendario. Indica l'UID ottenuto da "
        "calendar.events, oppure il titolo e la data (YYYY-MM-DD)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "uid": {"type": "string", "maxLength": 200},
            "title": {"type": "string", "maxLength": 200},
            "date": {"type": "string", "maxLength": 40},
            "calendar": {"type": "string", "maxLength": 100},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Cancellazione definitiva di un evento del calendario.",
    timeout_s=45.0,
    consequences="L'evento sparisce da Calendar e, se sincronizzato, anche dagli altri dispositivi.",
    undo="Nessuno automatico: l'evento va ricreato a mano.",
    tags=("macos", "calendario", "cancellazione"),
)

def register(registry) -> None:
    registry.register(FunctionTool(CALENDAR_LIST, _list_calendars))
    registry.register(FunctionTool(CALENDAR_EVENTS, _list_events))
    registry.register(FunctionTool(CALENDAR_CREATE, _create_event))
    registry.register(FunctionTool(CALENDAR_DELETE, _delete_event))
