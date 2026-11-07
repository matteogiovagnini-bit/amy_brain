"""Adapter del modulo Vision: screenshot e OCR locale."""

from __future__ import annotations

from pathlib import Path

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import screen_tools
from ..base import BaseAdapter, collect_tools, tool_names


class VisionAdapter(BaseAdapter):
    def __init__(self) -> None:
        tools = collect_tools(screen_tools.register)
        super().__init__(
            ModuleManifest(
                name="vision",
                title="Vision",
                version="0.1.0",
                description="Screenshot e OCR locale; telecamera e descrizione sono opzionali.",
                default_enabled=True,
                capabilities=("vision.ocr", "vision.screen", "vision.camera"),
                requires=("screen_recording",),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )

    def status(self) -> ModuleStatus:
        base = super().status()
        if not Path("/usr/sbin/screencapture").exists():
            base.state = ModuleState.OFFLINE
            base.available = False
            base.detail = "screencapture non disponibile"
            return base
        base.detail = "OCR locale con Vision; telecamera e descrizione opzionali"
        base.data = {"ocr": True, "camera": False, "describe": False}
        return base
