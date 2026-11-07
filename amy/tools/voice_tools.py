"""Strumenti di voce."""

from __future__ import annotations

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

def register(registry) -> None:
    registry.register(FunctionTool(SPEAK, _speak))
    registry.register(FunctionTool(STOP_SPEAKING, _stop_speaking))
