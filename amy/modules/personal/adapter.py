"""Adapter del modulo Personal Manager: calendario, promemoria e mail."""

from __future__ import annotations

from typing import Any, List

from ...shared.module import ModuleManifest, ModuleStatus
from ...tools import calendar_tools, mail_tools, notes_tools, reminders_tools, tasks_tools
from ..base import BaseAdapter, collect_tools, tool_names


class PersonalAdapter(BaseAdapter):
    def __init__(self) -> None:
        tools: List[Any] = []
        for register in (
            calendar_tools.register,
            reminders_tools.register,
            mail_tools.register,
            tasks_tools.register,
            notes_tools.register,
        ):
            tools.extend(collect_tools(register))
        super().__init__(
            ModuleManifest(
                name="personal",
                title="Personal Manager",
                version="0.1.0",
                description="Calendario, promemoria e posta tramite le app di macOS.",
                default_enabled=True,
                capabilities=(
                    "personal.calendar",
                    "personal.reminders",
                    "personal.mail",
                    "personal.tasks",
                    "personal.notes",
                ),
                requires=("automation",),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        base.detail = "AppleScript: Calendar, Promemoria e Mail"
        base.data = {"tools": len(self._tools)}
        return base
