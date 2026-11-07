"""Adapter del modulo Memory attorno a SQLite e agli strumenti di memoria."""

from __future__ import annotations

from typing import Any, Optional

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import memory_tools
from ..base import BaseAdapter, collect_tools, tool_names


class MemoryAdapter(BaseAdapter):
    def __init__(self, memory: Optional[Any] = None) -> None:
        tools = collect_tools(memory_tools.register)
        super().__init__(
            ModuleManifest(
                name="memory",
                title="Memory",
                version="0.1.0",
                description="Fatti, sessioni, attività e memoria a lungo termine.",
                default_enabled=True,
                capabilities=("memory.read", "memory.write", "memory.delete"),
                requires=("sqlite",),
                tools=tool_names(tools),
                optional=False,
            ),
            tools,
        )
        self.memory = memory

    def status(self) -> ModuleStatus:
        base = super().status()
        if self.memory is None:
            base.detail = "strumenti pronti; archivio non collegato"
            return base
        try:
            stats = self.memory.stats()
        except Exception as exc:  # noqa: BLE001
            base.state = ModuleState.ERROR
            base.available = False
            base.detail = "memoria non leggibile: %s" % exc
            return base
        base.detail = "SQLite locale"
        base.data = stats
        return base
