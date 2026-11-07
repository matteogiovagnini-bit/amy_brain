"""Strumenti del Developer Assistant nativo.

Sola lettura per stato, diff e analisi. La suite è l'unica esecuzione di codice
e resta di livello B. Nessuna shell arbitraria: i comandi Git sono una lista
chiusa e l'ambiente è il progetto autorizzato.
"""

from __future__ import annotations

from typing import Any, Dict

from ..dev import DevError, analyze, diff, run_tests, status
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _failure(exc: DevError) -> ToolResult:
    return ToolResult.failure(
        exc.message,
        error_code=exc.code,
        data={"detail": exc.detail} if exc.detail else None,
    )


def _status(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        data = status(context)
    except DevError as exc:
        return _failure(exc)
    return ToolResult.success(
        data,
        "Repository %s, ramo %s: %d modifiche e %d file non tracciati."
        % (
            data["project"],
            data["branch"],
            data["modified"],
            data["untracked"],
        ),
    )


def _diff(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        data = diff(
            context,
            staged=bool(args.get("staged", False)),
            path=str(args.get("path", "") or ""),
            stat_only=bool(args.get("stat_only", False)),
        )
    except DevError as exc:
        return _failure(exc)
    if data["empty"]:
        return ToolResult.success(data, "Nessuna modifica da mostrare.")
    return ToolResult.success(
        data,
        "Diff %sletto dal progetto%s."
        % (
            "in stage " if data["staged"] else "",
            " (troncato)" if data["truncated"] else "",
        ),
    )


def _analyze(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        data = analyze(
            context,
            path=str(args.get("path", "") or ""),
            limit=int(args.get("limit", 1000)),
        )
    except DevError as exc:
        return _failure(exc)
    return ToolResult.success(
        data,
        "Analizzati %d file, %d righe, %d segnalazioni TODO/FIXME e %d errori di sintassi."
        % (
            data["files"],
            data["lines"],
            len(data["todos"]),
            len(data["syntax_errors"]),
        ),
    )


def _test(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        data = run_tests(context)
    except DevError as exc:
        return _failure(exc)
    if data["timed_out"]:
        return ToolResult.failure(
            "La suite ha superato il tempo massimo di %.0f secondi." % data["timeout_s"],
            error_code="test_timeout",
            data=data,
        )
    if not data["ok"]:
        return ToolResult.failure(
            "La suite è terminata con codice %d: %d test eseguiti."
            % (data["exit_code"], data["tests"]),
            error_code="tests_failed",
            data=data,
        )
    return ToolResult.success(
        data,
        "Suite superata: %d test." % data["tests"],
    )


DEV_STATUS = ToolSpec(
    name="dev.status",
    description=(
        "Legge lo stato del progetto: ramo Git, modifiche, ultimo commit e file "
        "di dipendenze. Non modifica nulla."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dello stato del repository locale.",
    tags=("sviluppo", "git", "sola_lettura"),
)

DEV_DIFF = ToolSpec(
    name="dev.diff",
    description=(
        "Mostra il diff del progetto, anche in stage, con limite di output. "
        "Non applica modifiche."
    ),
    parameters={
        "type": "object",
        "properties": {
            "staged": {"type": "boolean"},
            "path": {"type": "string", "maxLength": 500},
            "stat_only": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura delle modifiche presenti nel progetto.",
    tags=("sviluppo", "git", "diff", "sola_lettura"),
)

DEV_ANALYZE = ToolSpec(
    name="dev.analyze",
    description=(
        "Analizza file o cartelle del progetto: conteggi, file più grandi, "
        "TODO/FIXME ed errori di sintassi Python. Non modifica nulla."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "maxLength": 500},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura statica dei file del progetto.",
    tags=("sviluppo", "analisi", "sola_lettura"),
)

DEV_TEST = ToolSpec(
    name="dev.test",
    description=(
        "Esegue la suite unittest del progetto con timeout e output limitato. "
        "Può eseguire codice di test: richiede conferma."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.B,
    reason="Esecuzione della suite di test del progetto.",
    consequences=(
        "I test possono leggere file e usare risorse locali; non modificano il "
        "codice, ma eseguono codice del progetto."
    ),
    undo="Nessuna modifica permanente: i risultati restano nel log e nell'audit.",
    timeout_s=920.0,
    tags=("sviluppo", "test", "verifica"),
)


def register(registry) -> None:
    registry.register(FunctionTool(DEV_STATUS, _status))
    registry.register(FunctionTool(DEV_DIFF, _diff))
    registry.register(FunctionTool(DEV_ANALYZE, _analyze))
    registry.register(FunctionTool(DEV_TEST, _test))
