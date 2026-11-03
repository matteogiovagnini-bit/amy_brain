"""Promemoria macOS tramite AppleScript.

Legge, crea, completa ed elimina promemoria reali in Reminders.app. Come per il
calendario, i testi sono escapati e le date costruite per componenti.

Il primo uso richiede il permesso **Automazione** per Promemoria.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.errors import AmyError
from .applescript import escape_applescript, run_osascript
from .calendar import parse_start, _set_date_script

US = "\x1f"
RS = "\x1e"


class RemindersError(AmyError):
    code = "reminders_error"


def _text(value: str) -> str:
    escaped = escape_applescript(str(value or ""))
    return escaped.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def list_reminder_lists() -> List[Dict[str, Any]]:
    """Elenca le liste di Promemoria con il loro identificatore."""
    script = """tell application "Reminders"
set out to ""
repeat with l in lists
set out to out & (name of l) & (ASCII character 31) & (id of l) & (ASCII character 30)
end repeat
return out
end tell"""
    raw = run_osascript(script, timeout=20.0)
    items = []
    for record in raw.split(RS):
        if not record:
            continue
        parts = record.split(US)
        if len(parts) >= 2:
            items.append({"name": parts[0], "id": parts[1]})
    return items


def resolve_list(name: str = "", *, default_name: str = "") -> Dict[str, Any]:
    lists = list_reminder_lists()
    if not lists:
        raise RemindersError(
            "Nessuna lista di promemoria trovata.",
            detail="Apri Promemoria e crea una lista, poi riprova.",
        )
    wanted = (name or default_name or "").strip()
    if wanted:
        for item in lists:
            if item["name"].lower() == wanted.lower():
                return item
        if name:
            raise RemindersError(
                "Lista di promemoria non trovata: %s" % name,
                detail="Liste disponibili: %s" % ", ".join(item["name"] for item in lists),
            )
    return lists[0]


def _due_script(name: str, due: str) -> str:
    moment = parse_start(due)
    return _set_date_script(name, moment)


def list_reminders(
    *,
    list_name: str = "",
    default_list: str = "",
    include_completed: bool = False,
    limit: int = 100,
) -> Dict[str, Any]:
    target = resolve_list(list_name, default_name=default_list)
    condition = "true" if include_completed else "false"
    script = """tell application "Reminders"
set us to (ASCII character 31)
set rs to (ASCII character 30)
set out to ""
tell list "{name}"
set found to (every reminder whose completed is {condition})
repeat with r in found
set dueText to us & us & us & us & us
try
set d to due date of r
if d is not missing value then
set dueText to us & (year of d as string) & us & (month of d as integer as string) & us & (day of d as string) & us & (hours of d as string) & us & (minutes of d as string)
end if
end try
set bodyText to body of r
if bodyText is missing value then set bodyText to ""
set out to out & (id of r) & us & (name of r) & us & (completed of r as string) & dueText & us & bodyText & rs
end repeat
end tell
return out
end tell""".format(name=_text(target["name"]), condition=condition)
    raw = run_osascript(script, timeout=30.0)
    reminders = []
    for record in raw.split(RS):
        if not record:
            continue
        parts = record.split(US)
        if len(parts) < 9:
            continue
        due = ""
        if parts[3] and parts[4] and parts[5]:
            try:
                moment = datetime(
                    int(parts[3]), int(parts[4]), int(parts[5]),
                    int(parts[6] or 0), int(parts[7] or 0),
                )
                due = moment.strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                due = ""
        reminders.append(
            {
                "id": parts[0],
                "name": parts[1],
                "completed": parts[2].strip().lower() == "true",
                "due": due,
                "notes": "" if parts[8].strip() == "missing value" else parts[8],
                "list": target["name"],
            }
        )
    reminders.sort(key=lambda item: (item["completed"], item["due"] or "9999", item["name"].lower()))
    return {"list": target["name"], "reminders": reminders[: max(0, int(limit))], "total": len(reminders)}


def create_reminder(
    *,
    name: str,
    due: str = "",
    list_name: str = "",
    default_list: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    clean = " ".join(str(name or "").split())
    if not clean:
        raise RemindersError("Il testo del promemoria è vuoto.")
    target = resolve_list(list_name, default_name=default_list)
    due_script = ""
    due_value = ""
    if due:
        moment = parse_start(due)
        due_script = _due_script("dueDate", due) + "\nset due date of newReminder to dueDate"
        due_value = moment.strftime("%Y-%m-%dT%H:%M")
    script = """tell application "Reminders"
set theList to list "{list}"
set newReminder to make new reminder at end of theList with properties {{name:"{name}", body:"{notes}"}}
{due_script}
return (id of newReminder)
end tell""".format(
        list=_text(target["name"]), name=_text(clean), notes=_text(notes), due_script=due_script
    )
    identifier = run_osascript(script, timeout=30.0).strip()
    return {
        "id": identifier,
        "name": clean,
        "due": due_value,
        "list": target["name"],
        "notes": notes,
    }


def _find_script(*, list_name: str, identifier: str) -> str:
    """AppleScript che restituisce l'ID del primo promemoria corrispondente."""
    value = _text(identifier)
    if identifier.startswith("x-apple-reminder://"):
        condition = 'id is "%s"' % value
    else:
        condition = 'name is "%s"' % value
    return """tell application "Reminders"
tell list "{list}"
set found to (every reminder whose {condition})
if (count of found) is 0 then error "Promemoria non trovato."
return (id of (item 1 of found))
end tell
end tell""".format(list=_text(list_name), condition=condition)


def complete_reminder(*, identifier: str, list_name: str = "", default_list: str = "") -> Dict[str, Any]:
    target = resolve_list(list_name, default_name=default_list)
    found = run_osascript(_find_script(list_name=target["name"], identifier=identifier), timeout=30.0).strip()
    script = """tell application "Reminders"
tell list "{list}"
set completed of (first reminder whose id is "{uid}") to true
end tell
return "completato"
end tell""".format(list=_text(target["name"]), uid=_text(found))
    run_osascript(script, timeout=30.0)
    return {"id": found, "list": target["name"], "completed": True}


def delete_reminder(*, identifier: str, list_name: str = "", default_list: str = "") -> Dict[str, Any]:
    target = resolve_list(list_name, default_name=default_list)
    found = run_osascript(_find_script(list_name=target["name"], identifier=identifier), timeout=30.0).strip()
    script = """tell application "Reminders"
tell list "{list}"
delete (first reminder whose id is "{uid}")
end tell
return "eliminato"
end tell""".format(list=_text(target["name"]), uid=_text(found))
    run_osascript(script, timeout=30.0)
    return {"id": found, "list": target["name"], "deleted": True}
