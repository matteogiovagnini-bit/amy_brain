"""Adapter del modulo Robot Control attorno a protocollo, simulatore e link."""

from __future__ import annotations

from typing import Any, Optional

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import robot_tools
from ..base import BaseAdapter, collect_tools, tool_names


class RobotAdapter(BaseAdapter):
    def __init__(self, link: Optional[Any] = None) -> None:
        tools = collect_tools(robot_tools.register)
        super().__init__(
            ModuleManifest(
                name="robot",
                title="Robot Control",
                version="0.1.0",
                description="Protocollo v1, simulatore, MQTT e sicurezza robotica.",
                default_enabled=True,
                capabilities=("robot.read", "robot.move", "robot.estop"),
                requires=("robot_link",),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )
        self.link = link

    def status(self) -> ModuleStatus:
        base = super().status()
        if self.link is None:
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "strumenti pronti; nessun link robot passato"
            return base
        try:
            data = self.link.status()
        except Exception as exc:  # noqa: BLE001
            base.state = ModuleState.ERROR
            base.available = False
            base.detail = "stato robot non disponibile: %s" % exc
            return base
        mode = str((data or {}).get("mode", "sconosciuta"))
        base.state = ModuleState.READY
        base.available = True
        base.detail = "robot collegato in modalità %s" % mode
        base.data = data if isinstance(data, dict) else {"status": data}
        return base
