"""Strumenti robotici esposti ad Amy.

I comandi di movimento sono di livello C e richiedono sempre conferma esplicita.
L'E-stop e l'interruzione del movimento sono di livello A e non vengono mai
bloccati da una conferma: la sicurezza ha priorità sulla pianificazione.
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.errors import RobotError
from ..robot.protocol import JOINT_NAMES
from ..security.risk import RiskLevel
from .base import FunctionTool, ToolContext, ToolResult, ToolSpec


def _link(context: ToolContext):
    if context.robot_link is None:
        raise RobotError("Collegamento robot non inizializzato.")
    return context.robot_link


def _status(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = _link(context).status()
    if data.get("reachable") is False:
        return ToolResult.failure(
            "Il robot non è raggiungibile.",
            error_code="robot_unreachable",
            data=data,
        )
    return ToolResult.success(data, "Stato del robot letto.")


def _ping(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = _link(context).ping()
    if not data.get("reachable"):
        return ToolResult.failure("Il robot non risponde.", error_code="robot_unreachable", data=data)
    return ToolResult.success(data, "Robot raggiungibile (%.1f ms)." % float(data.get("rtt_ms", 0)))


def _stop(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    data = _link(context).stop(str(args.get("reason", "operator")))
    context.memory.record_robot_event("stop", data)
    return ToolResult.success(data, "Arresto controllato inviato. Safe state HOLD.")


def _estop(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    # Nessuna conferma: l'arresto di emergenza deve essere immediato.
    data = _link(context).estop(str(args.get("reason", "operator")))
    context.memory.record_robot_event("estop", data)
    return ToolResult.success(
        data,
        "E-stop software attivato. L'E-stop fisico resta l'unico arresto garantito.",
    )


def _reset_estop(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    if args.get("operator_ack") is not True:
        return ToolResult.failure(
            "Il reset dell'E-stop richiede operator_ack=true.",
            error_code="operator_ack_required",
        )
    data = _link(context).reset_estop(operator_ack=True)
    context.memory.record_robot_event("estop_reset", data)
    return ToolResult.success(data, "Latch di sicurezza azzerato. Nessun movimento ripreso.")


def _mode(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    mode = str(args["mode"]).upper()
    data = _link(context).set_mode(mode)
    context.memory.record_robot_event("mode", {"mode": mode, "status": data})
    return ToolResult.success(data, "Modalità robot impostata su %s." % mode)


def _move(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    joints = list(args["joints"])
    head = bool(args.get("head", False))
    if not head:
        bad = [item["joint"] for item in joints if item["joint"] not in JOINT_NAMES[:6]]
        if bad:
            return ToolResult.failure(
                "I giunti delle gambe non possono essere comandati con head=false: %s" % ", ".join(bad),
                error_code="invalid_joint",
            )
    else:
        bad = [item["joint"] for item in joints if item["joint"] not in {"head_pan", "head_tilt"}]
        if bad:
            return ToolResult.failure(
                "La testa accetta solo head_pan e head_tilt: %s" % ", ".join(bad),
                error_code="invalid_joint",
            )
    data = _link(context).move(
        joints,
        speed_limit_dps=float(args.get("speed_limit_dps", 15.0)),
        deadline_ms=int(args.get("deadline_ms", 3000)),
        head=head,
    )
    ack = data.get("ack") or data.get("response") or {}
    ack_payload = ack.get("payload", {}) if isinstance(ack, dict) else {}
    if isinstance(ack_payload, dict) and ack_payload.get("outcome") == "rejected":
        context.memory.record_robot_event("move_rejected", data)
        return ToolResult.failure(
            "Comando di movimento rifiutato: %s" % ack_payload.get("detail", "motivo non specificato"),
            error_code=ack_payload.get("code", "rejected"),
            data=data,
        )
    context.memory.record_robot_event("move", data)
    if data.get("simulated"):
        verified = bool(data.get("completion_verified"))
        message = (
            "Movimento simulato completato. Nessun attuatore fisico è stato mosso."
            if verified
            else "Comando simulato accettato; completamento non verificato."
        )
        return ToolResult.success(data, message)
    return ToolResult.success(
        data,
        "Comando accettato dal robot. Il completamento non è ancora verificato: serve motion.result.",
    )


ROBOT_STATUS = ToolSpec(
    name="robot.status",
    description="Legge stato, modalità, batteria, E-stop, heartbeat e posizioni stimate del robot.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Lettura dello stato del robot.",
    tags=("robot",),
)

ROBOT_PING = ToolSpec(
    name="robot.ping",
    description="Verifica se il robot (o il simulatore) è raggiungibile e misura il tempo di risposta.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    risk=RiskLevel.A,
    reason="Verifica di raggiungibilità.",
    tags=("robot",),
)

ROBOT_STOP = ToolSpec(
    name="robot.stop",
    description="Arresta il movimento in corso e porta il robot in HOLD. Non richiede conferma.",
    parameters={
        "type": "object",
        "properties": {"reason": {"type": "string", "maxLength": 100}},
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Arresto controllato, azione di sicurezza sempre consentita.",
    tags=("robot", "sicurezza"),
)

ROBOT_ESTOP = ToolSpec(
    name="robot.estop",
    description="Attiva immediatamente l'E-stop software e blocca ogni movimento. Non richiede conferma.",
    parameters={
        "type": "object",
        "properties": {"reason": {"type": "string", "maxLength": 100}},
        "additionalProperties": False,
    },
    risk=RiskLevel.A,
    reason="Arresto di emergenza: priorità assoluta.",
    consequences="Ogni movimento viene bloccato fino a un reset esplicito. Non sostituisce l'E-stop fisico.",
    tags=("robot", "sicurezza"),
)

ROBOT_RESET_ESTOP = ToolSpec(
    name="robot.reset_estop",
    description="Azzera il latch dell'E-stop software dopo verifica dell'area. Non riprende alcun movimento.",
    parameters={
        "type": "object",
        "properties": {"operator_ack": {"type": "boolean"}},
        "required": ["operator_ack"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Rimozione di un blocco di sicurezza dopo un arresto.",
    consequences="Il robot torna in modalità TEST/IDLE, ma non riprende automaticamente a muoversi.",
    undo="Premi nuovamente E-stop se la situazione non è sicura.",
    tags=("robot", "sicurezza"),
)

ROBOT_MODE = ToolSpec(
    name="robot.mode",
    description="Imposta la modalità operativa: test (nessun movimento fisico), idle o ready (solo se calibrato).",
    parameters={
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["test", "idle", "ready"]}},
        "required": ["mode"],
        "additionalProperties": False,
    },
    risk=RiskLevel.B,
    reason="Cambio della modalità operativa del robot.",
    consequences="In modalità READY gli attuatori possono accettare movimenti; la calibrazione è obbligatoria.",
    undo="Riporta il robot in modalità TEST o IDLE.",
    tags=("robot",),
)

ROBOT_MOVE = ToolSpec(
    name="robot.move",
    description="Invia un obiettivo di posizione per giunti delle gambe o della testa, entro i limiti. Richiede sempre conferma.",
    parameters={
        "type": "object",
        "properties": {
            "joints": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "joint": {"type": "string", "enum": JOINT_NAMES},
                        "position_deg": {"type": "number", "minimum": -180, "maximum": 180},
                    },
                    "required": ["joint", "position_deg"],
                    "additionalProperties": False,
                },
            },
            "speed_limit_dps": {"type": "number", "minimum": 1, "maximum": 60},
            "deadline_ms": {"type": "integer", "minimum": 200, "maximum": 10000},
            "head": {"type": "boolean"},
        },
        "required": ["joints"],
        "additionalProperties": False,
    },
    risk=RiskLevel.C,
    reason="Movimento fisico potenziale degli attuatori.",
    consequences=(
        "I giunti si muovono verso la posizione richiesta. In modalità TEST il movimento è simulato; "
        "con hardware reale possono esserci urti, cadute o danni se l'area non è libera."
    ),
    undo="Usa robot.stop o l'E-stop fisico. Il movimento non è reversibile automaticamente.",
    tags=("robot", "movimento", "sicurezza"),
)


def register(registry) -> None:
    registry.register(FunctionTool(ROBOT_STATUS, _status))
    registry.register(FunctionTool(ROBOT_PING, _ping))
    registry.register(FunctionTool(ROBOT_STOP, _stop))
    registry.register(FunctionTool(ROBOT_ESTOP, _estop))
    registry.register(FunctionTool(ROBOT_RESET_ESTOP, _reset_estop))
    registry.register(FunctionTool(ROBOT_MODE, _mode))
    registry.register(FunctionTool(ROBOT_MOVE, _move))
