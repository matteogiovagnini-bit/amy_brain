"""Strumenti Smart Home su MQTT."""

from __future__ import annotations

from typing import Any, Dict

from ..home import HomeService
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _service(context: ToolContext) -> HomeService:
    return HomeService(context.config)


def _devices(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    service = _service(context)
    if not service.enabled():
        return ToolResult.failure(
            "Smart Home disattivato nella configurazione.",
            error_code="home_disabled",
        )
    rows = service.devices()
    return ToolResult.success(
        {"devices": rows, "count": len(rows)},
        "Trovati %d dispositivi configurati." % len(rows),
    )


def _state(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    service = _service(context)
    if not service.enabled():
        return ToolResult.failure(
            "Smart Home disattivato nella configurazione.",
            error_code="home_disabled",
        )
    data = service.state(str(args["device"]))
    return ToolResult.success(data, "Stato letto da %s." % data["device"])


def _set(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    service = _service(context)
    if not service.enabled():
        return ToolResult.failure(
            "Smart Home disattivato nella configurazione.",
            error_code="home_disabled",
        )
    data = service.set(str(args["device"]), str(args["value"]))
    return ToolResult.success(data, "Comando inviato a %s." % data["device"])


def _scene(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    service = _service(context)
    if not service.enabled():
        return ToolResult.failure(
            "Smart Home disattivato nella configurazione.",
            error_code="home_disabled",
        )
    name = str(args["name"]).strip()
    scenes = context.config.get("home.scenes", []) or []
    for scene in scenes:
        if isinstance(scene, dict) and str(scene.get("name", "")).strip().lower() == name.lower():
            device = str(scene.get("device", "")).strip()
            value = str(scene.get("value", ""))
            data = service.set(device, value)
            return ToolResult.success(data, "Scena «%s» inviata." % name)
    return ToolResult.failure(
        "Scena non configurata: %s" % name,
        error_code="home_scene_missing",
    )


HOME_DEVICES = ToolSpec(
    name="home.devices",
    description="Elenca i dispositivi Smart Home configurati, senza credenziali.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura della configurazione dei dispositivi.",
    tags=("casa", "mqtt"),
)

HOME_STATE = ToolSpec(
    name="home.state",
    description="Legge lo stato di un dispositivo MQTT dal suo state_topic.",
    parameters={
        "type": "object",
        "properties": {"device": {"type": "string", "minLength": 1, "maxLength": 100}},
        "required": ["device"],
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Lettura di un sensore o stato domestico.",
    timeout_s=20.0,
    tags=("casa", "mqtt", "sensori"),
)

HOME_SET = ToolSpec(
    name="home.set",
    description="Invia un comando a un dispositivo MQTT (luce, presa, scena).",
    parameters={
        "type": "object",
        "properties": {
            "device": {"type": "string", "minLength": 1, "maxLength": 100},
            "value": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["device", "value"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Comando che cambia lo stato di un dispositivo domestico.",
    consequences="Il dispositivo riceve il comando; lo stato non è verificabile senza una lettura.",
    undo="Invia il comando opposto, se il dispositivo lo supporta.",
    timeout_s=20.0,
    tags=("casa", "mqtt", "attuatori"),
)

HOME_SCENE = ToolSpec(
    name="home.scene",
    description="Esegue una scena configurata in home.scenes.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 100}},
        "required": ["name"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Una scena può cambiare più dispositivi contemporaneamente.",
    consequences="Più dispositivi possono cambiare stato; la verifica dipende dai sensori.",
    undo="Esegui la scena opposta o ripristina i singoli dispositivi.",
    timeout_s=25.0,
    tags=("casa", "mqtt", "scene"),
)


def register(registry) -> None:
    registry.register(FunctionTool(HOME_DEVICES, _devices))
    registry.register(FunctionTool(HOME_STATE, _state))
    registry.register(FunctionTool(HOME_SET, _set))
    registry.register(FunctionTool(HOME_SCENE, _scene))
