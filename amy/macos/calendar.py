"""Calendario macOS tramite AppleScript.

Qui si creano e si leggono eventi reali in Calendar.app. Ogni stringa passa da
``escape_applescript`` e le date vengono costruite per componenti, così non
dipendono dalla lingua del sistema.

Il primo uso richiede il permesso **Automazione** per Calendar (Impostazioni di
Sistema → Privacy e Sicurezza → Automazione). Se manca, l'errore lo dice.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..core.errors import AmyError
from .applescript import escape_applescript, run_osascript

#: Calendari di sistema che non hanno senso come destinazione predefinita.
SPECIAL_CALENDARS = (
    "festività",
    "festivita",
    "compleanni",
    "suggerimenti di siri",
    "promemoria programmati",
)


class CalendarError(AmyError):
    code = "calendar_error"


def _text(value: str) -> str:
    """Testo sicuro per un literal AppleScript."""
    escaped = escape_applescript(str(value or ""))
    return escaped.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def _components(moment: datetime) -> Dict[str, int]:
    return {
        "y": moment.year,
        "m": moment.month,
        "d": moment.day,
        "hh": moment.hour,
        "mm": moment.minute,
    }


def _set_date_script(name: str, moment: datetime) -> str:
    parts = _components(moment)
    return """set {name} to current date
set year of {name} to {y}
set month of {name} to {m}
set day of {name} to {d}
set hours of {name} to {hh}
set minutes of {name} to {mm}
set seconds of {name} to 0""".format(name=name, **parts)


def list_calendars() -> List[Dict[str, Any]]:
    """Elenca i calendari con l'indicazione se sono scrivibili."""
    script = """tell application "Calendar"
set out to ""
repeat with c in calendars
set out to out & (name of c) & (ASCII character 31) & (writable of c as string) & (ASCII character 30)
end repeat
return out
end tell"""
    raw = run_osascript(script, timeout=20.0)
    calendars = []
    for record in raw.split("\x1e"):
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 2:
            continue
        calendars.append(
            {
                "name": parts[0],
                "writable": parts[1].strip().lower() == "true",
            }
        )
    return calendars


def resolve_calendar(name: str = "", *, default_name: str = "Calendario") -> Dict[str, Any]:
    """Sceglie un calendario scrivibile per nome, oppure il predefinito."""
    calendars = list_calendars()
    writable = [item for item in calendars if item["writable"]]
    if not writable:
        raise CalendarError(
            "Nessun calendario scrivibile trovato.",
            detail="Apri Calendar e crea un calendario, poi riprova.",
        )
    wanted = (name or default_name or "").strip()
    if wanted:
        for item in writable:
            if item["name"].lower() == wanted.lower():
                return item
        if name:
            raise CalendarError(
                "Calendario non trovato: %s" % name,
                detail="Calendari disponibili: %s"
                % ", ".join(item["name"] for item in writable),
            )
    for item in writable:
        lowered = item["name"].lower()
        if not any(special in lowered for special in SPECIAL_CALENDARS):
            return item
    return writable[0]


def parse_start(value: str) -> datetime:
    """Converte una data ISO in un datetime locale senza fuso orario."""
    text = str(value or "").strip()
    if not text:
        raise CalendarError("Data di inizio mancante.")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CalendarError(
            "Data non valida: %s" % value,
            detail="Usa il formato YYYY-MM-DDTHH:MM oppure YYYY-MM-DD HH:MM.",
        ) from exc
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def create_event(
    *,
    title: str,
    start: str,
    duration_minutes: int = 60,
    calendar_name: str = "",
    default_calendar: str = "Calendario",
    notes: str = "",
    location: str = "",
    all_day: bool = False,
) -> Dict[str, Any]:
    """Crea un evento reale e restituisce l'UID assegnato da Calendar."""
    clean_title = " ".join(str(title or "").split())
    if not clean_title:
        raise CalendarError("Il titolo dell'evento è vuoto.")
    moment = parse_start(start)
    calendar = resolve_calendar(calendar_name, default_name=default_calendar)

    if all_day:
        begin = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end = begin + timedelta(days=1)
        duration_seconds = 0
        allday = "true"
    else:
        try:
            minutes = int(duration_minutes)
        except (TypeError, ValueError):
            minutes = 60
        minutes = max(5, min(minutes, 24 * 60))
        begin = moment.replace(second=0, microsecond=0)
        end = begin + timedelta(minutes=minutes)
        duration_seconds = minutes * 60
        allday = "false"

    script = """tell application "Calendar"
set theCal to calendar "{calendar}"
{start_script}
{end_script}
set newEvent to make new event at end of events of theCal with properties {{summary:"{title}", start date:startDate, end date:endDate, description:"{notes}", location:"{location}", allday event:{allday}}}
return (uid of newEvent)
end tell""".format(
        calendar=_text(calendar["name"]),
        start_script=_set_date_script("startDate", begin),
        end_script=_set_date_script("endDate", end),
        title=_text(clean_title),
        notes=_text(notes),
        location=_text(location),
        allday=allday,
    )
    try:
        uid = run_osascript(script, timeout=30.0)
    except AmyError:
        raise
    except Exception as exc:  # pragma: no cover - difensivo
        raise CalendarError("Creazione dell'evento non riuscita.", detail=str(exc)) from exc

    return {
        "uid": uid.strip(),
        "calendar": calendar["name"],
        "title": clean_title,
        "start": begin.strftime("%Y-%m-%dT%H:%M"),
        "end": end.strftime("%Y-%m-%dT%H:%M"),
        "all_day": bool(all_day),
        "duration_minutes": 0 if all_day else duration_seconds // 60,
    }


def list_events(*, date: str, calendar_name: str = "", default_calendar: str = "Calendario") -> Dict[str, Any]:
    """Elenca gli eventi di un giorno nel calendario indicato."""
    moment = parse_start(date).replace(hour=0, minute=0, second=0, microsecond=0)
    calendar = resolve_calendar(calendar_name, default_name=default_calendar)
    script = """tell application "Calendar"
set us to (ASCII character 31)
set rs to (ASCII character 30)
{start_script}
set endDate to startDate + 86400
set out to ""
tell calendar "{calendar}"
set found to (every event whose start date is greater than or equal to startDate and start date is less than endDate)
repeat with e in found
set sd to start date of e
set ed to end date of e
set out to out & (year of sd as string) & us & (month of sd as integer as string) & us & (day of sd as string) & us & (hours of sd as string) & us & (minutes of sd as string) & us & (year of ed as string) & us & (month of ed as integer as string) & us & (day of ed as string) & us & (hours of ed as string) & us & (minutes of ed as string) & us & (summary of e) & us & (uid of e) & rs
end repeat
end tell
return out
end tell""".format(
        start_script=_set_date_script("startDate", moment),
        calendar=_text(calendar["name"]),
    )
    raw = run_osascript(script, timeout=30.0)
    events = []
    for record in raw.split("\x1e"):
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 12:
            continue
        try:
            started = datetime(
                int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
            )
            ended = datetime(
                int(parts[5]), int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])
            )
        except ValueError:
            continue
        events.append(
            {
                "uid": parts[11],
                "title": parts[10],
                "start": started.strftime("%Y-%m-%dT%H:%M"),
                "end": ended.strftime("%Y-%m-%dT%H:%M"),
                "calendar": calendar["name"],
            }
        )
    events.sort(key=lambda item: item["start"])
    return {"date": moment.strftime("%Y-%m-%d"), "calendar": calendar["name"], "events": events}

def delete_event(
    *,
    uid: str = "",
    title: str = "",
    date: str = "",
    calendar_name: str = "",
    default_calendar: str = "Calendario",
) -> Dict[str, Any]:
    """Elimina un evento per UID oppure per titolo e giorno.

    La cancellazione è di livello C nel registro degli strumenti: questa
    funzione deve essere chiamata solo dopo una conferma esplicita.
    """
    calendar = resolve_calendar(calendar_name, default_name=default_calendar)
    target_uid = str(uid or "").strip()

    if not target_uid:
        if not title or not date:
            raise CalendarError(
                "Serve l'UID dell'evento oppure il titolo e la data.",
            )
        day = list_events(date=date, calendar_name=calendar["name"], default_calendar=default_calendar)
        matches = [
            event for event in day["events"]
            if str(event.get("title", "")).strip().lower() == str(title).strip().lower()
        ]
        if not matches:
            raise CalendarError(
                "Nessun evento «%s» trovato il %s." % (title, day["date"]),
                detail="Controlla il titolo con calendar.events.",
            )
        if len(matches) > 1:
            raise CalendarError(
                "Ci sono %d eventi con questo titolo: indica l'UID." % len(matches),
                detail="UID: " + ", ".join(event["uid"] for event in matches),
            )
        target_uid = matches[0]["uid"]

    script = """tell application "Calendar"
tell calendar "{calendar}"
set found to (every event whose uid is "{uid}")
if (count of found) is 0 then error "Evento non trovato."
delete (item 1 of found)
end tell
return "eliminato"
end tell""".format(calendar=_text(calendar["name"]), uid=_text(target_uid))
    run_osascript(script, timeout=30.0)
    return {"uid": target_uid, "calendar": calendar["name"], "deleted": True}
