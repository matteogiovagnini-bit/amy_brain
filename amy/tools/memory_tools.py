"""Strumenti di memoria: fatti, progetti e preferenze controllabili."""

from __future__ import annotations

from typing import Any, Dict

from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _remember(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    key = str(args["key"]).strip()
    value = str(args["value"]).strip()
    category = str(args.get("category", "personal") or "personal").strip()
    tags = str(args.get("tags", "") or "")
    verified = bool(args.get("verified", False))
    confidence = float(args.get("confidence", 0.5))
    expires_at = str(args.get("expires_at", "") or "") or None
    if category == "personal" and not tags and not verified and expires_at is None:
        # Compatibilità: i fatti personali restano nella tabella storica.
        context.memory.set_fact(key, value, source="utente")
    else:
        context.memory.set_memory(
            category,
            key,
            value,
            source="utente",
            confidence=confidence,
            verified=verified,
            tags=tags,
            expires_at=expires_at,
        )
    return ToolResult.success(
        {"key": key, "value": value, "category": category, "tags": tags},
        "Ho memorizzato «%s» nella categoria %s." % (key, category),
    )


def _forget(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    key = str(args["key"]).strip()
    category = str(args.get("category", "") or "").strip()
    if category and category != "personal":
        removed = context.memory.delete_memory(category, key)
    else:
        removed = context.memory.delete_fact(key)
        if not removed:
            removed = context.memory.delete_memory("personal", key)
    return ToolResult.success(
        {"key": key, "category": category or "personal", "removed": removed},
        "Ho rimosso «%s» dalla memoria." % key if removed else "Non avevo memorizzato «%s»." % key,
    )


def _list_memories(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    category = str(args.get("category", "") or "") or None
    query = str(args.get("query", "") or "").strip()
    include_expired = bool(args.get("include_expired", False))
    if query:
        items = context.memory.search_memories(
            query, category=category, limit=int(args.get("limit", 50)), include_expired=include_expired
        )
    else:
        items = context.memory.list_memories(
            category=category, limit=int(args.get("limit", 50)), include_expired=include_expired
        )
    facts = context.memory.list_facts(int(args.get("limit", 50)))
    return ToolResult.success(
        {
            "elementi": items,
            "fatti": [{"key": item["key"], "value": item["value"], "updated_at": item["updated_at"]} for item in facts],
            "categorie": context.memory.memory_categories(),
        },
        "Ci sono %d elementi in memoria." % len(items),
    )


def _search(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    query = str(args["query"]).strip()
    category = str(args.get("category", "") or "") or None
    items = context.memory.search_memories(
        query,
        category=category,
        limit=int(args.get("limit", 50)),
        include_expired=bool(args.get("include_expired", False)),
    )
    return ToolResult.success(
        {"query": query, "elementi": items, "count": len(items)},
        "Trovati %d elementi per «%s»." % (len(items), query),
    )


def _update(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    category = str(args.get("category", "personal") or "personal").strip()
    key = str(args["key"]).strip()
    changed = context.memory.update_memory(
        category,
        key,
        value=args.get("value"),
        tags=args.get("tags"),
        verified=args.get("verified"),
        confidence=args.get("confidence"),
        expires_at=args.get("expires_at"),
    )
    return ToolResult.success(
        {"key": key, "category": category, "updated": changed},
        "Memoria aggiornata." if changed else "Nessuna memoria corrispondente da aggiornare.",
    )


def _categories(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    items = context.memory.memory_categories()
    return ToolResult.success(
        {"categorie": items},
        "Trovate %d categorie di memoria." % len(items),
    )


REMEMBER = ToolSpec(
    name="memory.remember",
    description=(
        "Salva un fatto, una preferenza o una nota duratura. Usa category per "
        "distinguere personal, project, operational."
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "minLength": 1, "maxLength": 200},
            "value": {"type": "string", "minLength": 1, "maxLength": 4000},
            "category": {"type": "string", "maxLength": 50},
            "tags": {"type": "string", "maxLength": 500},
            "verified": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "expires_at": {"type": "string", "maxLength": 40},
        },
        "required": ["key", "value"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Salvataggio di una preferenza o di un fatto indicato dall'utente.",
    consequences="Il dato resta nella memoria locale finché non viene eliminato.",
    undo="Usa memory.forget con la stessa chiave e categoria.",
    tags=("memoria",),
)

FORGET = ToolSpec(
    name="memory.forget",
    description="Elimina un fatto o un elemento di memoria dalla categoria indicata.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "minLength": 1, "maxLength": 200},
            "category": {"type": "string", "maxLength": 50},
        },
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
    description="Elenca fatti e memorie, con filtro per categoria e ricerca facoltativa.",
    parameters={
        "type": "object",
        "properties": {
            "category": {"type": "string", "maxLength": 50},
            "query": {"type": "string", "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            "include_expired": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura della memoria locale.",
    tags=("memoria",),
)

SEARCH = ToolSpec(
    name="memory.search",
    description="Cerca testo in chiavi, valori e tag della memoria, con filtro per categoria.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "category": {"type": "string", "maxLength": 50},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            "include_expired": {"type": "boolean"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Ricerca nella memoria locale, senza modifiche.",
    tags=("memoria",),
)

UPDATE = ToolSpec(
    name="memory.update",
    description="Aggiorna valore, tag, verificabilità, confidenza o scadenza di una memoria.",
    parameters={
        "type": "object",
        "properties": {
            "category": {"type": "string", "maxLength": 50},
            "key": {"type": "string", "minLength": 1, "maxLength": 200},
            "value": {"type": "string", "maxLength": 8000},
            "tags": {"type": "string", "maxLength": 500},
            "verified": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "expires_at": {"type": "string", "maxLength": 40},
        },
        "required": ["key"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Aggiornamento di un dato di memoria già esistente.",
    tags=("memoria",),
)

CATEGORIES = ToolSpec(
    name="memory.categories",
    description="Elenca le categorie di memoria con il numero di elementi.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura delle categorie di memoria.",
    tags=("memoria",),
)


def register(registry) -> None:
    registry.register(FunctionTool(REMEMBER, _remember))
    registry.register(FunctionTool(FORGET, _forget))
    registry.register(FunctionTool(LIST_MEMORIES, _list_memories))
    registry.register(FunctionTool(SEARCH, _search))
    registry.register(FunctionTool(UPDATE, _update))
    registry.register(FunctionTool(CATEGORIES, _categories))
