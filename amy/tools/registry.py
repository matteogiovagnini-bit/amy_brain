"""Registro degli strumenti disponibili."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from ..core.errors import ToolError
from ..core.logging_setup import get_logger
from .base import Tool, ToolContext, ToolResult, run_with_timeout
from .schema import validate_arguments

_log = get_logger("tools.registry")


class ToolNotFoundError(ToolError):
    code = "tool_not_found"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.spec.name
        if not name or not isinstance(name, str):
            raise ValueError("Ogni strumento deve avere un nome.")
        if name in self._tools:
            raise ValueError("Strumento già registrato: %s" % name)
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if not tool:
            raise ToolNotFoundError("Strumento sconosciuto: %s" % name)
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> List[str]:
        return sorted(self._tools)

    def all(self) -> Iterable[Tool]:
        for name in sorted(self._tools):
            yield self._tools[name]

    def catalog(self, *, include_hidden: bool = False) -> List[Dict[str, Any]]:
        return [
            tool.spec.to_dict()
            for tool in self.all()
            if include_hidden or not tool.spec.hidden
        ]

    def catalog_json(self) -> str:
        return json.dumps(self.catalog(), ensure_ascii=False, indent=2)

    def execute(self, name: str, args: Optional[Dict[str, Any]], context: ToolContext) -> ToolResult:
        tool = self.get(name)
        args = args or {}
        validate_arguments(tool.spec.parameters, args)
        try:
            return run_with_timeout(tool, args, context)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - l'errore diventa un esito verificabile
            _log.exception("Errore interno dello strumento %s", name)
            return ToolResult.failure(
                "Errore interno durante l'esecuzione di %s." % name,
                error_code="internal_error",
                data={"detail": str(exc)[:500]},
            )
