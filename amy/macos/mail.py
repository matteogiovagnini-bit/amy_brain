"""Posta di macOS tramite AppleScript.

Legge account, cassette e messaggi da Mail.app. Non invia e non modifica nulla:
la lettura del corpo è di livello B perché il contenuto può essere inviato al
provider IA configurato.

Il primo uso richiede il permesso **Automazione** per Mail. Mail.app può essere
lento ad aprire il dizionario AppleScript: i timeout sono ampi.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List

from ..core.errors import AmyError
from .applescript import escape_applescript, run_osascript

US = "\x1f"
RS = "\x1e"

#: Mail.app può impiegare decine di secondi al primo AppleScript (avvio,
#: indicizzazione). Gli account cambiano raramente: si tengono in cache.
_ACCOUNTS_TTL_S = 300.0
_ACCOUNTS_LOCK = threading.Lock()
_ACCOUNTS_CACHE: Dict[str, Any] = {"at": 0.0, "items": []}


class MailError(AmyError):
    code = "mail_error"


def _text(value: str) -> str:
    escaped = escape_applescript(str(value or ""))
    return escaped.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def list_accounts(*, force: bool = False) -> List[Dict[str, str]]:
    now = time.monotonic()
    with _ACCOUNTS_LOCK:
        cached = _ACCOUNTS_CACHE["items"]
        if not force and cached and now - _ACCOUNTS_CACHE["at"] < _ACCOUNTS_TTL_S:
            return [dict(item) for item in cached]
        script = """tell application "Mail"
set us to (ASCII character 31)
set rs to (ASCII character 30)
set out to ""
repeat with a in accounts
set out to out & (name of a) & us & (email addresses of a as string) & rs
end repeat
return out
end tell"""
        raw = run_osascript(script, timeout=120.0)
        accounts = []
        for record in raw.split(RS):
            if not record:
                continue
            parts = record.split(US)
            if len(parts) >= 2:
                addresses = [item.strip() for item in parts[1].split(",") if item.strip()]
                accounts.append({"name": parts[0], "addresses": addresses})
        _ACCOUNTS_CACHE["at"] = time.monotonic()
        _ACCOUNTS_CACHE["items"] = [dict(item) for item in accounts]
        return accounts


def resolve_account(value: str = "", *, default: str = "") -> Dict[str, str]:
    accounts = list_accounts()
    if not accounts:
        raise MailError(
            "Nessun account configurato in Mail.",
            detail="Apri Mail e configura un account, poi riprova.",
        )
    wanted = (value or default or "").strip().lower()
    if wanted:
        for account in accounts:
            if account["name"].lower() == wanted:
                return account
            if any(address.lower() == wanted for address in account["addresses"]):
                return account
        raise MailError(
            "Account non trovato: %s" % (value or default),
            detail="Account disponibili: "
            + ", ".join(
                "%s (%s)" % (account["name"], ", ".join(account["addresses"]))
                for account in accounts
            ),
        )
    return accounts[0]


def list_mailboxes(account_name: str = "", *, default_account: str = "") -> Dict[str, Any]:
    account = resolve_account(account_name, default=default_account)
    script = """tell application "Mail"
set us to (ASCII character 31)
set rs to (ASCII character 30)
set out to ""
repeat with m in mailboxes of account "{account}"
set out to out & (name of m) & us & (unread count of m as string) & us & (count of messages of m as string) & rs
end repeat
return out
end tell""".format(account=_text(account["name"]))
    raw = run_osascript(script, timeout=60.0)
    boxes = []
    for record in raw.split(RS):
        if not record:
            continue
        parts = record.split(US)
        if len(parts) >= 3:
            boxes.append(
                {
                    "name": parts[0],
                    "unread": int(parts[1] or 0),
                    "total": int(parts[2] or 0),
                }
            )
    return {"account": account["name"], "mailboxes": boxes}


def list_messages(
    *,
    account_name: str = "",
    mailbox: str = "INBOX",
    limit: int = 10,
    unread_only: bool = False,
    default_account: str = "",
) -> Dict[str, Any]:
    account = resolve_account(account_name, default=default_account)
    count = max(1, min(int(limit), 50))
    condition = " whose read status is false" if unread_only else ""
    script = """tell application "Mail"
set us to (ASCII character 31)
set rs to (ASCII character 30)
set out to ""
tell mailbox "{mailbox}" of account "{account}"
set found to (messages{condition})
set total to count of found
if total is 0 then return ""
if total > {count} then set total to {count}
repeat with i from 1 to total
set m to item i of found
set d to date received of m
set out to out & (id of m as string) & us & (subject of m as string) & us & (sender of m as string) & us & (read status of m as string) & us & (year of d as string) & us & (month of d as integer as string) & us & (day of d as string) & us & (hours of d as string) & us & (minutes of d as string) & rs
end repeat
end tell
return out
end tell""".format(
        mailbox=_text(mailbox), account=_text(account["name"]), condition=condition, count=count
    )
    raw = run_osascript(script, timeout=90.0)
    messages = []
    for record in raw.split(RS):
        if not record:
            continue
        parts = record.split(US)
        if len(parts) < 9:
            continue
        try:
            received = datetime(
                int(parts[4]), int(parts[5]), int(parts[6]), int(parts[7]), int(parts[8])
            ).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            received = ""
        messages.append(
            {
                "id": parts[0],
                "subject": parts[1],
                "sender": parts[2],
                "read": parts[3].strip().lower() == "true",
                "received": received,
            }
        )
    return {
        "account": account["name"],
        "mailbox": mailbox,
        "messages": messages,
        "unread_only": bool(unread_only),
    }


def read_message(
    *,
    message_id: str,
    account_name: str = "",
    mailbox: str = "INBOX",
    default_account: str = "",
    max_chars: int = 8000,
) -> Dict[str, Any]:
    identifier = str(message_id or "").strip()
    if not identifier.isdigit():
        raise MailError(
            "ID del messaggio non valido: %s" % message_id,
            detail="Usa l'ID numerico restituito da mail.list.",
        )
    account = resolve_account(account_name, default=default_account)
    script = """tell application "Mail"
set us to (ASCII character 31)
set rs to (ASCII character 30)
tell mailbox "{mailbox}" of account "{account}"
set found to (messages whose id is {identifier})
if (count of found) is 0 then error "Messaggio non trovato."
set m to item 1 of found
set d to date received of m
return (subject of m as string) & us & (sender of m as string) & us & (year of d as string) & us & (month of d as integer as string) & us & (day of d as string) & us & (hours of d as string) & us & (minutes of d as string) & us & (content of m as string)
end tell
end tell""".format(
        mailbox=_text(mailbox), account=_text(account["name"]), identifier=identifier
    )
    raw = run_osascript(script, timeout=90.0)
    parts = raw.split(US)
    if len(parts) < 8:
        raise MailError("Risposta di Mail non interpretabile.")
    try:
        received = datetime(
            int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5]), int(parts[6])
        ).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        received = ""
    body = US.join(parts[7:]).strip()
    limit = max(200, min(int(max_chars), 20000))
    truncated = len(body) > limit
    return {
        "id": identifier,
        "account": account["name"],
        "mailbox": mailbox,
        "subject": parts[0],
        "sender": parts[1],
        "received": received,
        "body": body[:limit],
        "truncated": truncated,
    }


def search_messages(
    *,
    query: str,
    account_name: str = "",
    mailbox: str = "INBOX",
    limit: int = 10,
    default_account: str = "",
) -> Dict[str, Any]:
    needle = str(query or "").strip().lower()
    if not needle:
        raise MailError("Cerca qualcosa: mittente o oggetto.")
    data = list_messages(
        account_name=account_name,
        mailbox=mailbox,
        limit=100,
        default_account=default_account,
    )
    matches = [
        message
        for message in data["messages"]
        if needle in message["subject"].lower() or needle in message["sender"].lower()
    ]
    data["messages"] = matches[: max(1, min(int(limit), 50))]
    data["query"] = query
    return data


def account_label(account_name: str = "", default_account: str = "") -> str:
    account = resolve_account(account_name, default=default_account)
    return account["name"]

def _recipients(value: str) -> List[str]:
    """Divide indirizzi separati da virgola o punto e virgola."""
    items = []
    for part in str(value or "").replace(";", ",").split(","):
        address = part.strip()
        if not address:
            continue
        if "\n" in address or "\r" in address or " " in address:
            raise MailError("Indirizzo email non valido: %s" % address)
        if "@" not in address or address.startswith("@") or address.endswith("@"):
            raise MailError("Indirizzo email non valido: %s" % address)
        items.append(address)
    return items


def send_message(
    *,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    account_name: str = "",
    default_account: str = "",
) -> Dict[str, Any]:
    """Crea e invia un messaggio con Mail.app.

    L'invio è irreversibile: questa funzione va chiamata solo dopo una conferma
    esplicita (livello C). Restituisce lo stato reale: Mail ha accettato il
    messaggio, non garantisce la consegna al destinatario.
    """
    recipients = _recipients(to)
    if not recipients:
        raise MailError("Serve almeno un destinatario.")
    if len(recipients) > 10:
        raise MailError("Troppi destinatari: massimo 10.")
    clean_subject = " ".join(str(subject or "").split())
    if not clean_subject:
        raise MailError("L'oggetto è vuoto.")
    if len(clean_subject) > 300:
        clean_subject = clean_subject[:300]
    text = str(body or "")
    if not text.strip():
        raise MailError("Il corpo del messaggio è vuoto.")
    if len(text) > 20000:
        raise MailError("Il corpo è troppo lungo: massimo 20.000 caratteri.")
    copy = _recipients(cc) if cc else []
    blind = _recipients(bcc) if bcc else []
    account = resolve_account(account_name, default=default_account)
    sender = account["addresses"][0] if account["addresses"] else account["name"]

    def recipients_script(label: str, addresses: List[str]) -> str:
        lines = []
        for address in addresses:
            lines.append(
                'make new %s recipient at end of %s recipients with properties {address:"%s"}'
                % (label, label, _text(address))
            )
        return "\n".join(lines)

    script = """tell application "Mail"
set newMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:false}}
tell newMessage
set sender to "{sender}"
{to_script}
{cc_script}
{bcc_script}
end tell
send newMessage
end tell""".format(
        subject=_text(clean_subject),
        body=_text(text),
        sender=_text(sender),
        to_script=recipients_script("to", recipients),
        cc_script=recipients_script("cc", copy),
        bcc_script=recipients_script("bcc", blind),
    )
    run_osascript(script, timeout=120.0)
    return {
        "account": account["name"],
        "sender": sender,
        "to": recipients,
        "cc": copy,
        "bcc": blind,
        "subject": clean_subject,
        "chars": len(text),
        "accepted": True,
        "note": "Mail ha accettato il messaggio; la consegna non è verificabile da Amy.",
    }
