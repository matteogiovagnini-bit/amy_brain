"""Registrazione centralizzata degli strumenti predefiniti."""

from __future__ import annotations

from . import apps, calendar_tools, files, mail_tools, memory_tools, opencode_tools, reminders_tools, robot_tools, shell, system, voice_tools, web
from .registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    system.register(registry)
    apps.register(registry)
    calendar_tools.register(registry)
    reminders_tools.register(registry)
    mail_tools.register(registry)
    opencode_tools.register(registry)
    files.register(registry)
    shell.register(registry)
    web.register(registry)
    memory_tools.register(registry)
    voice_tools.register(registry)
    robot_tools.register(registry)
    return registry
