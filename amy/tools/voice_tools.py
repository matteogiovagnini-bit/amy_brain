"""Strumenti di voce e tempo."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict

from ..core.errors import VoiceError
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _speak(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    if context.voice is None:
        raise VoiceError("Servizio vocale non disponibile.")
    result = context.voice.speak(str(args["text"]), block=False)
    return ToolResult.success(result, "Sto pronunciando il testo.")


def _stop_speaking(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    if context.voice is not None:
        context.voice.stop_speaking()
    return ToolResult.success({"stopped": True}, "Sintesi vocale interrotta.")


def _now(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    now = datetime.now().astimezone()
    return ToolResult.success(
        {
            "iso": now.isoformat(timespec="seconds"),
            "data": now.strftime("%A %d %B %Y"),
            "ora": now.strftime("%H:%M"),
            "timezone": str(now.tzinfo),
            "epoch": int(time.time()),
        },
        "Sono le %s del %s." % (now.strftime("%H:%M"), now.strftime("%d/%m/%Y")),
    )


SPEAK = ToolSpec(
    name="voice.speak",
    description="Pronuncia un testo con la voce italiana di macOS. Non attende la fine dell'audio.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 4000}},
        "required": ["text"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Riproduzione audio locale.",
    tags=("voce",),
)

STOP_SPEAKING = ToolSpec(
    name="voice.stop",
    description="Interrompe immediatamente la sintesi vocale in corso.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Interruzione dell'audio, azione sempre consentita.",
    tags=("voce", "sicurezza"),
)

NOW = ToolSpec(
    name="time.now",
    description="Restituisce data e ora locali correnti.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dell'orologio di sistema.",
    tags=("sistema",),
)


def register(registry) -> None:
    registry.register(FunctionTool(SPEAK, _speak))
    registry.register(FunctionTool(STOP_SPEAKING, _stop_speaking))
    registry.register(FunctionTool(NOW, _now))
