"""Adapter del modulo Developer Assistant: OpenCode e riavvio dell'app."""

from __future__ import annotations

import shutil
from typing import Any, List

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import dev_tools, opencode_tools, system
from ..base import BaseAdapter, collect_tools, tool_names


class DeveloperAdapter(BaseAdapter):
    def __init__(self) -> None:
        tools: List[Any] = list(collect_tools(dev_tools.register))
        tools.extend(collect_tools(opencode_tools.register))
        tools.extend(
            tool
            for tool in collect_tools(system.register)
            if getattr(getattr(tool, "spec", None), "name", "") == "app.restart"
        )
        super().__init__(
            ModuleManifest(
                name="developer",
                title="Developer Assistant",
                version="0.1.0",
                description="OpenCode 2, analisi del progetto e riavvio dopo le modifiche.",
                default_enabled=False,
                capabilities=("dev.read", "dev.write", "dev.execute", "dev.restart"),
                requires=("opencode2",),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        config = getattr(self._context, "config", None) if self._context is not None else None
        if config is not None and not bool(config.get("opencode.enabled", False)):
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "OpenCode disattivato; analisi del progetto disponibile"
            return base
        binary = str((config.get("opencode.binary", "opencode2") if config is not None else "opencode2"))
        if not shutil.which(binary):
            base.state = ModuleState.OFFLINE
            base.available = False
            base.detail = "OpenCode 2 non trovato nel PATH"
            return base
        base.detail = "OpenCode 2 disponibile; ogni richiesta richiede conferma"
        base.data = {"binary": binary}
        return base
