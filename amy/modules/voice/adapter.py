"""Adapter del modulo Voice Engine attorno a `amy/voice`."""

from __future__ import annotations

from typing import Any, Optional

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ...tools import voice_tools
from ..base import BaseAdapter, collect_tools, tool_names


class VoiceAdapter(BaseAdapter):
    def __init__(self, voice: Optional[Any] = None) -> None:
        tools = collect_tools(voice_tools.register)
        super().__init__(
            ModuleManifest(
                name="voice",
                title="Voice Engine",
                version="0.1.0",
                description="Wake word, microfono, STT, TTS, conversazione e barge-in.",
                default_enabled=True,
                capabilities=(
                    "voice.wake",
                    "voice.stt",
                    "voice.tts",
                    "voice.conversation",
                ),
                requires=("microphone", "stt", "tts"),
                tools=tool_names(tools),
                optional=True,
            ),
            tools,
        )
        self.voice = voice

    def status(self) -> ModuleStatus:
        base = super().status()
        if self.voice is None:
            base.detail = "strumenti pronti; servizio vocale non collegato"
            return base
        try:
            data = self.voice.status()
        except Exception as exc:  # noqa: BLE001 - lo stato non deve rompere il Core
            base.state = ModuleState.ERROR
            base.available = False
            base.detail = "stato vocale non disponibile: %s" % exc
            return base
        ready = bool(data.get("ready_for_voice_commands"))
        base.state = ModuleState.READY if ready else ModuleState.DEGRADED
        base.available = ready
        base.detail = (
            "microfono, STT e TTS pronti"
            if ready
            else "voce incompleta: controlla microfono, STT e TTS"
        )
        base.data = {
            "state": data.get("state"),
            "speaking": bool(data.get("speaking")),
            "echo_guard": bool((data.get("wake_word") or {}).get("echo_guard")),
        }
        return base
