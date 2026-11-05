"""Strumenti per leggere la posta configurata in Mail.app."""

from __future__ import annotations

from typing import Any, Dict

from ..macos import (
    list_accounts,
    list_mailboxes,
    list_messages,
    read_message,
    search_messages,
    send_message,
)
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _default_account(context: ToolContext) -> str:
    try:
        return str(context.config.get("mail.default_account", "") or "")
    except Exception:  # pragma: no cover - configurazione assente nei test
        return ""


def _default_mailbox(context: ToolContext) -> str:
    try:
        return str(context.config.get("mail.default_mailbox", "INBOX") or "INBOX")
    except Exception:  # pragma: no cover
        return "INBOX"


def _accounts(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    rows = list_accounts()
    return ToolResult.success(
        {"accounts": rows, "predefinito": _default_account(context)},
        "Trovati %d account." % len(rows)
        if rows
        else "Nessun account configurato in Mail.",
    )


def _mailboxes(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = list_mailboxes(
        str(args.get("account", "") or ""),
        default_account=_default_account(context),
    )
    return ToolResult.success(
        data, "Trovate %d cassette per %s." % (len(data["mailboxes"]), data["account"])
    )


def _list(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = list_messages(
        account_name=str(args.get("account", "") or ""),
        mailbox=str(args.get("mailbox", "") or _default_mailbox(context)),
        limit=int(args.get("limit", 10)),
        unread_only=bool(args.get("unread_only", False)),
        default_account=_default_account(context),
    )
    count = len(data["messages"])
    return ToolResult.success(
        data,
        "Nessun messaggio in %s." % data["mailbox"]
        if count == 0
        else "%d messaggi in %s." % (count, data["mailbox"]),
    )


def _search(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = search_messages(
        query=str(args["query"]),
        account_name=str(args.get("account", "") or ""),
        mailbox=str(args.get("mailbox", "") or _default_mailbox(context)),
        limit=int(args.get("limit", 10)),
        default_account=_default_account(context),
    )
    return ToolResult.success(
        data,
        "Trovati %d messaggi per «%s»." % (len(data["messages"]), data["query"]),
    )


def _read(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = read_message(
        message_id=str(args["id"]),
        account_name=str(args.get("account", "") or ""),
        mailbox=str(args.get("mailbox", "") or _default_mailbox(context)),
        default_account=_default_account(context),
    )
    return ToolResult.success(data, "Messaggio «%s» letto." % data["subject"])


def _send(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = send_message(
        to=str(args["to"]),
        subject=str(args["subject"]),
        body=str(args["body"]),
        cc=str(args.get("cc", "") or ""),
        bcc=str(args.get("bcc", "") or ""),
        account_name=str(args.get("account", "") or ""),
        default_account=_default_account(context),
    )
    return ToolResult.success(
        data,
        "Email «%s» affidata a Mail per l'invio a %s."
        % (data["subject"], ", ".join(data["to"])),
    )


MAIL_ACCOUNTS = ToolSpec(
    name="mail.accounts",
    description="Elenca gli account configurati in Mail con i loro indirizzi.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura degli account di posta configurati.",
    timeout_s=120.0,
    tags=("macos", "mail"),
)

MAIL_MAILBOXES = ToolSpec(
    name="mail.mailboxes",
    description="Elenca le cassette di un account (INBOX, inviati, cestino) con i conteggi.",
    parameters={
        "type": "object",
        "properties": {"account": {"type": "string", "maxLength": 200}},
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura delle cassette di posta.",
    timeout_s=120.0,
    tags=("macos", "mail"),
)

MAIL_LIST = ToolSpec(
    name="mail.list",
    description=(
        "Elenca i messaggi recenti di una cassetta: mittente, oggetto, data e stato "
        "di lettura. Usa il parametro account per indicare l'indirizzo (per esempio "
        "info@ewp.it). Non restituisce il corpo e non serve mail.search per elencare."
    ),
    parameters={
        "type": "object",
        "properties": {
            "account": {"type": "string", "maxLength": 200},
            "mailbox": {"type": "string", "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "unread_only": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura dei metadati dei messaggi (mittente, oggetto, data).",
    consequences="Nessuna modifica: Mail viene solo interrogato.",
    timeout_s=120.0,
    tags=("macos", "mail"),
)

MAIL_SEARCH = ToolSpec(
    name="mail.search",
    description=(
        "Cerca messaggi per mittente o oggetto negli ultimi 100 messaggi. Usalo solo "
        "per una ricerca mirata, non per elencare la posta recente."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "account": {"type": "string", "maxLength": 200},
            "mailbox": {"type": "string", "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Ricerca nei metadati dei messaggi.",
    timeout_s=120.0,
    tags=("macos", "mail"),
)

MAIL_READ = ToolSpec(
    name="mail.read",
    description=(
        "Legge il corpo di un messaggio, indicando l'ID ottenuto da mail.list. "
        "Richiede conferma: il contenuto può essere inviato al provider IA configurato."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 40},
            "account": {"type": "string", "maxLength": 200},
            "mailbox": {"type": "string", "maxLength": 200},
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Lettura del contenuto di un messaggio, potenzialmente inviato al provider IA.",
    consequences=(
        "Il corpo dell'email viene letto e, se il provider è online, trasmesso a quel "
        "servizio per elaborare la risposta."
    ),
    undo="Nessuno: la lettura non modifica il messaggio.",
    timeout_s=120.0,
    tags=("macos", "mail", "privacy"),
)


MAIL_SEND = ToolSpec(
    name="mail.send",
    description=(
        "Crea e invia un'email dall'account configurato. Chiedi destinatario, "
        "oggetto e corpo se non li hai già: non inventare l'indirizzo. L'invio "
        "è irreversibile e richiede sempre conferma."
    ),
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "minLength": 3, "maxLength": 1000},
            "subject": {"type": "string", "minLength": 1, "maxLength": 300},
            "body": {"type": "string", "minLength": 1, "maxLength": 20000},
            "cc": {"type": "string", "maxLength": 1000},
            "bcc": {"type": "string", "maxLength": 1000},
            "account": {"type": "string", "maxLength": 200},
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Invio di un'email: operazione irreversibile.",
    consequences=(
        "Il messaggio parte dall'account configurato e non può essere richiamato. "
        "Controlla destinatario, oggetto e corpo prima di confermare."
    ),
    undo="Nessuno: un'email inviata non può essere annullata.",
    timeout_s=120.0,
    tags=("macos", "mail", "invio", "privacy"),
)


def register(registry) -> None:
    registry.register(FunctionTool(MAIL_ACCOUNTS, _accounts))
    registry.register(FunctionTool(MAIL_MAILBOXES, _mailboxes))
    registry.register(FunctionTool(MAIL_LIST, _list))
    registry.register(FunctionTool(MAIL_SEARCH, _search))
    registry.register(FunctionTool(MAIL_READ, _read))
    registry.register(FunctionTool(MAIL_SEND, _send))
