"""Strumenti per applicazioni macOS."""

from __future__ import annotations

import subprocess
from typing import Any, Dict

from ..macos import (
    activate_application,
    application_is_running,
    find_application,
    frontmost_application,
    list_installed_apps,
    open_application,
    quit_application,
)
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _list_apps(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    query = str(args.get("query", "")).strip().lower()
    limit = int(args.get("limit", 50))
    apps = list_installed_apps()
    if query:
        apps = [app for app in apps if query in app["name"].lower()]
    total = len(apps)
    return ToolResult.success(
        {"applicazioni": apps[:limit], "totale": total},
        "Trovate %d applicazioni." % total,
    )


def _open_app(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    result = open_application(str(args["name"]))
    return ToolResult.success(result, "%s è stata aperta." % result["name"])


def _quit_app(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    result = quit_application(str(args["name"]))
    return ToolResult.success(result, "Richiesta di chiusura inviata a %s." % result["name"])


def _focus_app(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    result = activate_application(str(args["name"]))
    return ToolResult.success(result, "%s è in primo piano." % result["name"])


def _is_running(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    name = str(args["name"])
    running = application_is_running(name)
    return ToolResult.success(
        {"name": name, "running": running},
        "%s è in esecuzione." % name if running else "%s non è in esecuzione." % name,
    )


def _frontmost(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    name = frontmost_application()
    return ToolResult.success({"name": name}, "Applicazione in primo piano: %s." % name)


APP_LIST = ToolSpec(
    name="apps.list",
    description="Elenca le applicazioni installate, con ricerca facoltativa per nome.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura dell'elenco applicazioni installate.",
    tags=("macos", "applicazioni"),
)

APP_OPEN = ToolSpec(
    name="apps.open",
    description="Apre un'applicazione installata sul Mac, cercandola per nome o percorso .app.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Apertura di un'applicazione già installata.",
    consequences="L'applicazione viene avviata e portata in primo piano.",
    undo="Puoi chiuderla con apps.quit.",
    tags=("macos", "applicazioni"),
)

APP_QUIT = ToolSpec(
    name="apps.quit",
    description="Chiede la chiusura di un'applicazione. Può far perdere modifiche non salvate.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Chiusura di un'applicazione con possibili documenti aperti.",
    consequences="L'applicazione può mostrare una richiesta di salvataggio o chiudersi.",
    undo="Riapri l'applicazione con apps.open; i dati non salvati non sono recuperabili da Amy.",
    tags=("macos", "applicazioni"),
)

APP_FOCUS = ToolSpec(
    name="apps.focus",
    description="Porta in primo piano un'applicazione già in esecuzione.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Cambio dell'applicazione in primo piano.",
    tags=("macos", "applicazioni"),
)

APP_RUNNING = ToolSpec(
    name="apps.running",
    description="Verifica se un'applicazione è in esecuzione.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Verifica dello stato di un'applicazione.",
    tags=("macos", "applicazioni"),
)

APP_FRONTMOST = ToolSpec(
    name="apps.frontmost",
    description="Restituisce il nome dell'applicazione attualmente in primo piano.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dell'applicazione attiva.",
    tags=("macos", "applicazioni"),
)


def register(registry) -> None:
    registry.register(FunctionTool(APP_LIST, _list_apps))
    registry.register(FunctionTool(APP_OPEN, _open_app))
    registry.register(FunctionTool(APP_QUIT, _quit_app))
    registry.register(FunctionTool(APP_FOCUS, _focus_app))
    registry.register(FunctionTool(APP_RUNNING, _is_running))
    registry.register(FunctionTool(APP_FRONTMOST, _frontmost))
