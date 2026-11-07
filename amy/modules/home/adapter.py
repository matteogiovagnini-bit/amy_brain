"""Adapter del modulo Smart Home.

La Fase 2 crea solo lo scheletro: nessun dispositivo, nessun broker, nessuno
strumento. Il modulo è spento per default e non influisce sul resto.
"""

from __future__ import annotations

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ..base import BaseAdapter


class HomeAdapter(BaseAdapter):
    def __init__(self) -> None:
        super().__init__(
            ModuleManifest(
                name="home",
                title="Smart Home",
                version="0.1.0",
                description="Dispositivi MQTT, sensori, luci e scene.",
                default_enabled=False,
                capabilities=("home.read", "home.set"),
                requires=("mqtt",),
                tools=(),
                optional=True,
            ),
            [],
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        if base.state == ModuleState.READY:
            base.detail = "nessun dispositivo configurato"
        else:
            base.detail = "non configurato"
        base.available = False
        return base
