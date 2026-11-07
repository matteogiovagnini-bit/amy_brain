"""Costruzione del registro dei moduli (Fase 2).

Gli adapter avvolgono il codice esistente senza spostarlo. Non sono ancora
collegati ad Amy Core, al server o alla UI: `builtin.py` resta l'aggregatore di
compatibilità con i 57 strumenti attuali.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.modules import ModuleRegistry
from ..shared.events import EventBus
from .developer import DeveloperAdapter
from .home import HomeAdapter
from .mac_control import MacControlAdapter
from .memory import MemoryAdapter
from .personal import PersonalAdapter
from .robot import RobotAdapter
from .vision import VisionAdapter
from .voice import VoiceAdapter

DEFAULT_MODULES = (
    "voice",
    "mac_control",
    "personal",
    "memory",
    "developer",
    "vision",
    "home",
    "robot",
)


def build_module_registry(
    config: Optional[Any] = None,
    *,
    events: Optional[EventBus] = None,
    voice: Optional[Any] = None,
    memory: Optional[Any] = None,
    robot_link: Optional[Any] = None,
    enabled: Optional[Dict[str, bool]] = None,
) -> ModuleRegistry:
    """Crea gli otto adapter e li registra, senza avviarli."""
    registry = ModuleRegistry(events=events)
    adapters = [
        VoiceAdapter(voice),
        MacControlAdapter(),
        PersonalAdapter(),
        MemoryAdapter(memory),
        DeveloperAdapter(),
        VisionAdapter(),
        HomeAdapter(),
        RobotAdapter(robot_link),
    ]
    overrides = dict(enabled or {})
    for adapter in adapters:
        flag = overrides.get(adapter.manifest.name)
        registry.register(adapter, enabled=flag)
    return registry
