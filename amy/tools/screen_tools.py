"""Strumenti per catturare lo schermo e leggerne il testo con OCR locale."""

from __future__ import annotations

from typing import Any, Dict

from ..macos import capture, read_screen
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _capture(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    path = capture()
    return ToolResult.success(
        {"image": str(path), "bytes": path.stat().st_size},
        "Screenshot salvato in %s." % path,
    )


def _read(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    image = str(args.get("image_path", "") or "").strip()
    resolved = context.path_guard.resolve(image, must_exist=True) if image else None
    data = read_screen(
        image_path=resolved,
        max_chars=int(args.get("max_chars", 8000)),
    )
    if not data["text"]:
        return ToolResult.success(
            data,
            "Nessun testo riconosciuto sullo schermo (l'immagine resta salvata).",
        )
    return ToolResult.success(
        data,
        "Letti %d caratteri dallo schermo." % data["chars"],
    )


SCREEN_CAPTURE = ToolSpec(
    name="screen.capture",
    description="Salva uno screenshot dello schermo in ~/Downloads/Amy/screenshots.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.B,
    reason="Lo screenshot può contenere dati personali o segreti visibili.",
    consequences="L'immagine viene salvata sul Mac; nessun dato viene inviato in rete.",
    timeout_s=40.0,
    tags=("macos", "schermo", "screenshot"),
)

SCREEN_READ = ToolSpec(
    name="screen.read",
    description=(
        "Cattura lo schermo e ne estrae il testo con OCR locale (Vision), oppure "
        "legge un'immagine già esistente. Per leggere lo schermo chiama questa "
        "funzione senza image_path: cattura e OCR avvengono in un solo passaggio, "
        "non serve screen.capture prima."
    ),
    parameters={
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "maxLength": 1000},
            "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
        },
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason=(
        "Lo schermo può contenere dati sensibili; il testo riconosciuto può essere "
        "inviato al provider IA configurato."
    ),
    consequences=(
        "Amy cattura lo schermo, estrae il testo in locale e lo usa per rispondere. "
        "Con un provider online, quel testo lascia il Mac."
    ),
    undo="Nessuno: l'immagine può essere eliminata da ~/.amy/screenshots.",
    timeout_s=150.0,
    tags=("macos", "schermo", "ocr", "privacy"),
)


def register(registry) -> None:
    registry.register(FunctionTool(SCREEN_CAPTURE, _capture))
    registry.register(FunctionTool(SCREEN_READ, _read))
