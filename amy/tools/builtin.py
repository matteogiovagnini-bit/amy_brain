"""Registrazione centralizzata degli strumenti predefiniti."""

from __future__ import annotations

from . import apps, files, memory_tools, robot_tools, shell, system, voice_tools, web
from .registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    system.register(registry)
    apps.register(registry)
    files.register(registry)
    shell.register(registry)
    web.register(registry)
    memory_tools.register(registry)
    voice_tools.register(registry)
    robot_tools.register(registry)
    return registry
