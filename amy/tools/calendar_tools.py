"""Strumenti per Calendar.app: elenco calendari, eventi e creazione appuntamenti."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..core.logging_setup import get_logger
from ..macos import create_event, delete_event, list_calendars, list_events
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec

_log = get_logger("tools.calendar")

UPCOMING_DAYS = 7
UPCOMING_LIMIT = 8
UPCOMING_BUDGET_S = 15.0
UPCOMING_MAX_DAYS = 14


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

def _upcoming_unavailable(moment: datetime, dates: List[Any], reason: str) -> Dict[str, Any]:
    """Risultato onesto quando la lettura del calendario non è possibile."""
    return {
        "available": False,
        "reason": reason,
        "date": moment.date().isoformat(),
        "to": dates[-1].isoformat(),
        "days": len(dates),
        "checked_days": 0,
        "failed_days": len(dates),
        "calendar": "",
        "events": [],
    }


def collect_upcoming(
    registry,
    context: ToolContext,
    *,
    days: int = UPCOMING_DAYS,
    limit: int = UPCOMING_LIMIT,
    now: Optional[datetime] = None,
    budget_s: float = UPCOMING_BUDGET_S,
) -> Dict[str, Any]:
    """Raccoglie i prossimi appuntamenti eseguendo ``calendar.events`` più volte.

    La dashboard legge un intervallo di giorni, ma lo strumento esistente
    accetta una data sola: ogni giorno viene quindi interrogato con lo stesso
    strumento di sola lettura, senza modificare il suo contratto. Gli eventi già
    terminati vengono scartati, i duplicati (eventi su più giorni) uniti per UID
    e i giorni non leggibili dichiarati: nessun dato viene inventato.

    Da qui non può partire alcuna azione di livello B o C: il nome dello
    strumento è fisso e il suo livello di rischio viene verificato prima
    dell'esecuzione. È una lettura richiesta dalla UI locale, non un'azione
    proposta dal modello, quindi non passa dalla conferma in due fasi.
    """
    moment = now or datetime.now()
    total_days = max(1, min(int(days), UPCOMING_MAX_DAYS))
    max_events = max(1, min(int(limit), 20))
    today = moment.date()
    dates = [today + timedelta(days=offset) for offset in range(total_days)]
    stamp = moment.strftime("%Y-%m-%dT%H:%M")
    started = time.monotonic()

    try:
        tool = registry.get("calendar.events")
    except Exception as exc:  # noqa: BLE001 - il registro può non averlo
        return _upcoming_unavailable(moment, dates, "Strumento calendar.events non disponibile: %s" % exc)
    if tool.spec.risk != RiskLevel.A:
        return _upcoming_unavailable(
            moment, dates, "calendar.events non è più di livello A: lettura bloccata."
        )

    events: List[Dict[str, Any]] = []
    seen = set()
    calendar_name = ""
    failed_days = 0
    reasons: List[str] = []

    for index, day in enumerate(dates):
        if time.monotonic() - started > budget_s:
            failed_days += len(dates) - index
            reasons.append("Tempo massimo di lettura superato.")
            break
        try:
            result = registry.execute("calendar.events", {"date": day.isoformat()}, context)
        except Exception as exc:  # noqa: BLE001 - un giorno non deve bloccare gli altri
            _log.warning("Lettura del calendario del %s non riuscita: %s", day, exc)
            failed_days += 1
            reasons.append(str(exc)[:200])
            continue
        if not result.ok or not isinstance(result.data, dict):
            failed_days += 1
            if result.message:
                reasons.append(str(result.message)[:200])
            continue
        data = result.data
        if not calendar_name:
            calendar_name = str(data.get("calendar") or "")
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            start = str(event.get("start") or "")
            end = str(event.get("end") or start)
            if not event.get("title") or not start or end < stamp:
                continue
            key = str(event.get("uid") or "") or (str(event.get("title")), start)
            if key in seen:
                continue
            seen.add(key)
            events.append(event)

    events.sort(key=lambda item: str(item.get("start") or ""))
    available = failed_days < len(dates)
    if not available:
        reason = reasons[0] if reasons else "Calendario non leggibile."
    elif failed_days:
        reason = "Lettura parziale: %d giorni non disponibili." % failed_days
    else:
        reason = ""
    return {
        "available": available,
        "reason": reason,
        "date": today.isoformat(),
        "to": dates[-1].isoformat(),
        "days": len(dates),
        "checked_days": len(dates) - failed_days,
        "failed_days": failed_days,
        "calendar": calendar_name,
        "events": events[:max_events],
    }


def register(registry) -> None:
    registry.register(FunctionTool(CALENDAR_LIST, _list_calendars))
    registry.register(FunctionTool(CALENDAR_EVENTS, _list_events))
    registry.register(FunctionTool(CALENDAR_CREATE, _create_event))
    registry.register(FunctionTool(CALENDAR_DELETE, _delete_event))
