"""Strumento per inviare l'ultima foto di Amy alla chat Telegram corrente."""

from __future__ import annotations

from typing import Any, Dict

from ..security.risk import RiskLevel
from ..telegram.service import TelegramError
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _send_last_photo(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    service = getattr(context, "telegram", None)
    if service is None:
        return ToolResult.failure(
            "Telegram non è disponibile in questo contesto.",
            error_code="telegram_unavailable",
        )
    try:
        data = service.send_last_photo()
    except TelegramError as exc:
        return ToolResult.failure(
            exc.message,
            error_code=exc.code,
            data={"detail": exc.detail} if exc.detail else None,
        )
    return ToolResult.success(
        data,
        "Foto inviata nella chat Telegram.",
    )


TELEGRAM_SEND_LAST_PHOTO = ToolSpec(
    name="telegram.send_last_photo",
    description=(
        "Invia l'ultima foto scattata da Amy alla chat Telegram da cui è arrivata "
        "la richiesta. Funziona solo durante un turno Telegram."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.B,
    reason="L'immagine lascia il Mac e passa dai server Telegram.",
    consequences="La foto viene consegnata alla chat Telegram autorizzata.",
    undo="Non è possibile ritirare un messaggio già consegnato da Telegram.",
    timeout_s=30.0,
    tags=("telegram", "foto", "privacy"),
)


def register(registry) -> None:
    registry.register(FunctionTool(TELEGRAM_SEND_LAST_PHOTO, _send_last_photo))
