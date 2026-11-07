"""Adapter del modulo Mac Control attorno agli strumenti macOS/file/sistema."""

from __future__ import annotations

from typing import Any, List

from ...shared.module import ModuleManifest, ModuleStatus
from ...tools import apps, files, shell, system, web
from ..base import BaseAdapter, collect_tools, tool_names


class MacControlAdapter(BaseAdapter):
    def __init__(self) -> None:
        tools: List[Any] = []
        for register in (apps.register, files.register, shell.register, system.register, web.register):
            tools.extend(collect_tools(register))
        # app.restart appartiene al Developer Assistant: qui resta solo il Mac.
        tools = [
            tool
            for tool in tools
            if getattr(getattr(tool, "spec", None), "name", "") != "app.restart"
        ]
        super().__init__(
            ModuleManifest(
                name="mac_control",
                title="Mac Control",
                version="0.1.0",
                description="Applicazioni, file, sistema, shell in sola lettura e web.",
                default_enabled=True,
                capabilities=(
                    "mac.app",
                    "mac.file",
                    "mac.shell.read",
                    "mac.system",
                    "mac.web",
                ),
                requires=(),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        base.detail = "macOS: applicazioni, file, sistema e web"
        base.data = {"tools": len(self._tools)}
        return base
