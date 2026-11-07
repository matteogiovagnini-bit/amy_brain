"""Adapter del modulo Smart Home.

La Fase 2 crea solo lo scheletro: nessun dispositivo, nessun broker, nessuno
strumento. Il modulo è spento per default e non influisce sul resto.
"""

from __future__ import annotations

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import home_tools
from ..base import BaseAdapter, collect_tools, tool_names


class HomeAdapter(BaseAdapter):
    def __init__(self) -> None:
        tools = collect_tools(home_tools.register)
        super().__init__(
            ModuleManifest(
                name="home",
                title="Smart Home",
                version="0.1.0",
                description="Dispositivi MQTT, sensori, luci e scene.",
                default_enabled=False,
                capabilities=("home.read", "home.set"),
                requires=("mqtt",),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        config = getattr(self._context, "config", None) if self._context is not None else None
        enabled = bool(config.get("home.enabled", False)) if config is not None else False
        if not enabled:
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "Smart Home disattivato: configura home.enabled e home.broker"
            return base
        base.state = ModuleState.READY
        base.available = True
        base.detail = "MQTT configurato; comandi non verificati senza sensori"
        base.data = {"broker": config.get("home.broker", ""), "devices": len(config.get("home.devices", []) or [])}
        return base
