"""Protocollo robotico Amy v1: envelope, topic, validazione e limiti.

La specifica canonica è ``../amy/docs/06_protocollo_mqtt.md``. Questo modulo
implementa il sottoinsieme usato dal cervello Mac e dal simulatore:
- envelope JSON a 8 campi;
- validazione rigorosa;
- comandi di alto livello (mai GPIO/PWM);
- limiti per giunto e rifiuto esplicito fuori limite;
- nessuna dichiarazione di completamento senza un esito.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..core.errors import RobotProtocolError

PROTOCOL_VERSION = 1
PI_ID = "amy-pi"
ESP32_L = "amy-esp32-l"
ESP32_T = "amy-esp32-t"
VALID_SOURCES = {PI_ID, ESP32_L, ESP32_T}
VALID_TYPES = {
    "system.heartbeat",
    "system.version",
    "system.capabilities",
    "status.snapshot",
    "status.limits",
    "telemetry.joints",
    "sensors.imu",
    "sensors.distance",
    "motion.target",
    "motion.sequence",
    "motion.head",
    "motion.stop",
    "motion.result",
    "motion.state",
    "command.ack",
    "command.nack",
    "command.request",
    "command.safe_reset",
    "command.limits",
    "command.params",
    "command.ping",
    "event.safety",
    "event.fault",
    "event.link",
    "diagnostics.log",
    "diagnostics.metrics",
}
ENVELOPE_KEYS = {"v", "type", "req_id", "seq", "ts", "src", "dst", "payload"}
TYPE_RE = re.compile(r"^[a-z0-9._-]{1,64}$")
MAX_PACKET = 3072

# Nomi canonici dei giunti (protocollo v1).
JOINT_NAMES = [
    "left_ankle_pitch",
    "left_knee_pitch",
    "left_hip_pitch",
    "right_ankle_pitch",
    "right_knee_pitch",
    "right_hip_pitch",
    "head_pan",
    "head_tilt",
]
LEG_JOINTS = JOINT_NAMES[:6]


@dataclass
class JointLimit:
    joint: str
    min_deg: float
    max_deg: float
    max_speed_dps: float = 30.0
    max_accel_dps2: float = 60.0
    zero_offset_deg: Optional[float] = None
    soft_limit_deg: Optional[float] = None

    @property
    def calibrated(self) -> bool:
        return self.zero_offset_deg is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "joint": self.joint,
            "min_deg": self.min_deg,
            "max_deg": self.max_deg,
            "max_speed_dps": self.max_speed_dps,
            "max_accel_dps2": self.max_accel_dps2,
            "zero_offset_deg": self.zero_offset_deg,
            "soft_limit_deg": self.soft_limit_deg,
        }


def default_limits() -> List[JointLimit]:
    """Limiti **dimostrativi** del simulatore.

    Non sono la geometria reale del robot: ``zero_offset_deg`` è ``None``, quindi
    il simulatore dichiara la calibrazione meccanica come non eseguita.
    """
    return [
        JointLimit("left_ankle_pitch", -25, 25),
        JointLimit("left_knee_pitch", 0, 90),
        JointLimit("left_hip_pitch", -35, 35),
        JointLimit("right_ankle_pitch", -25, 25),
        JointLimit("right_knee_pitch", 0, 90),
        JointLimit("right_hip_pitch", -35, 35),
        JointLimit("head_pan", -60, 60),
        JointLimit("head_tilt", -20, 40),
    ]


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_req_id(now_ms: Optional[int] = None) -> str:
    """Identificatore ULID-like di 26 caratteri, ordinabile per tempo."""
    timestamp = int(now_ms if now_ms is not None else time.time() * 1000)
    chars = []
    value = timestamp
    for _ in range(10):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    prefix = "".join(reversed(chars))
    suffix = "".join(secrets.choice(_CROCKFORD) for _ in range(16))
    return prefix + suffix


def make_envelope(
    msg_type: str,
    *,
    src: str,
    dst: str,
    payload: Dict[str, Any],
    req_id: Optional[str] = None,
    seq: int = 0,
    ts: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": msg_type,
        "req_id": req_id,
        "seq": int(seq),
        "ts": int(ts if ts is not None else time.time() * 1000),
        "src": src,
        "dst": dst,
        "payload": payload,
    }


def validate_envelope(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise RobotProtocolError("L'envelope deve essere un oggetto JSON.")
    keys = set(data)
    if keys != ENVELOPE_KEYS:
        missing = ENVELOPE_KEYS - keys
        extra = keys - ENVELOPE_KEYS
        detail = []
        if missing:
            detail.append("mancanti: %s" % ", ".join(sorted(missing)))
        if extra:
            detail.append("non ammessi: %s" % ", ".join(sorted(extra)))
        raise RobotProtocolError("Envelope non valido.", detail="; ".join(detail))
    if data["v"] != PROTOCOL_VERSION:
        raise RobotProtocolError(
            "Versione del protocollo non supportata.",
            detail="ricevuta %r, attesa %d" % (data["v"], PROTOCOL_VERSION),
        )
    msg_type = data["type"]
    if not isinstance(msg_type, str) or not TYPE_RE.match(msg_type):
        raise RobotProtocolError("Campo 'type' non valido.")
    if msg_type not in VALID_TYPES:
        raise RobotProtocolError("Tipo di messaggio sconosciuto.", detail=msg_type)
    if data["src"] not in VALID_SOURCES:
        raise RobotProtocolError("Campo 'src' non valido.", detail=str(data["src"]))
    if data["dst"] not in VALID_SOURCES:
        raise RobotProtocolError("Campo 'dst' non valido.", detail=str(data["dst"]))
    if data["src"] == data["dst"]:
        raise RobotProtocolError("Mittente e destinatario non possono coincidere.")
    if data["src"] != PI_ID and msg_type.startswith(("motion.", "command.")):
        # I dispositivi non comandano il Pi né altri dispositivi in v1.
        if not msg_type.startswith(("command.ack", "command.nack", "motion.result", "motion.state")):
            raise RobotProtocolError("Un dispositivo non può inviare comandi di movimento o supervisione.")
    if not isinstance(data["seq"], int) or isinstance(data["seq"], bool) or data["seq"] < 0 or data["seq"] > 0xFFFFFFFF:
        raise RobotProtocolError("Campo 'seq' non valido.")
    if not isinstance(data["ts"], int) or isinstance(data["ts"], bool) or data["ts"] < 0:
        raise RobotProtocolError("Campo 'ts' non valido.")
    if data["req_id"] is not None:
        if not isinstance(data["req_id"], str) or len(data["req_id"]) != 26:
            raise RobotProtocolError("Campo 'req_id' non valido.")
        if any(char not in _CROCKFORD for char in data["req_id"]):
            raise RobotProtocolError("Campo 'req_id' non valido.")
    if not isinstance(data["payload"], dict):
        raise RobotProtocolError("Il campo 'payload' deve essere un oggetto.")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PACKET:
        raise RobotProtocolError("Pacchetto troppo grande.", detail="%d byte" % len(encoded))
    return data


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RobotProtocolError("Valore numerico non valido: %s" % field_name)
    return float(value)


def validate_motion_target(payload: Dict[str, Any], limits: Dict[str, JointLimit]) -> List[Dict[str, Any]]:
    """Valida un comando di movimento. Non taglia mai la posizione: rifiuta."""
    joints = payload.get("joints")
    if not isinstance(joints, list) or not joints:
        raise RobotProtocolError("Il comando non contiene giunti.")
    if len(joints) > 8:
        raise RobotProtocolError("Troppi giunti nel comando.")
    seen = set()
    validated = []
    for item in joints:
        if not isinstance(item, dict):
            raise RobotProtocolError("Voce giunto non valida.")
        name = item.get("joint")
        if name not in limits:
            raise RobotProtocolError("Giunto sconosciuto.", detail=str(name))
        if name in seen:
            raise RobotProtocolError("Giunto duplicato nel comando.", detail=name)
        seen.add(name)
        position = _finite_number(item.get("position_deg"), "position_deg")
        limit = limits[name]
        if position < limit.min_deg or position > limit.max_deg:
            raise RobotProtocolError(
                "Posizione fuori dai limiti.",
                detail="%s=%.2f, ammesso [%.2f, %.2f]" % (name, position, limit.min_deg, limit.max_deg),
            )
        speed = _finite_number(item.get("speed_limit_dps", limit.max_speed_dps), "speed_limit_dps")
        accel = _finite_number(item.get("accel_limit_dps2", limit.max_accel_dps2), "accel_limit_dps2")
        clamped = []
        if speed <= 0 or speed > limit.max_speed_dps:
            speed = limit.max_speed_dps
            clamped.append("speed_limit_dps")
        if accel <= 0 or accel > limit.max_accel_dps2:
            accel = limit.max_accel_dps2
            clamped.append("accel_limit_dps2")
        validated.append(
            {
                "joint": name,
                "position_deg": position,
                "speed_limit_dps": speed,
                "accel_limit_dps2": accel,
                "clamped": clamped,
            }
        )
    deadline = payload.get("deadline_ms", 2000)
    if isinstance(deadline, bool) or not isinstance(deadline, int) or not (1 <= deadline <= 10000):
        raise RobotProtocolError("deadline_ms non valido (1..10000).")
    limits_version = payload.get("limits_version", 1)
    if isinstance(limits_version, bool) or not isinstance(limits_version, int) or limits_version < 1:
        raise RobotProtocolError("limits_version non valida.")
    return validated


def limits_to_dict(limits: Iterable[JointLimit], version: int = 1) -> Dict[str, Any]:
    return {
        "limits_version": version,
        "joints": [limit.to_dict() for limit in limits],
    }


def command_topic(msg_type: str, dst: str) -> Optional[str]:
    """Topic MQTT per un comando di alto livello."""
    if msg_type == "motion.target" and dst == ESP32_L:
        return "amy/motion/esp32-l/target"
    if msg_type == "motion.sequence" and dst == ESP32_L:
        return "amy/motion/esp32-l/sequence"
    if msg_type == "motion.head" and dst == ESP32_T:
        return "amy/motion/esp32-t/head"
    if msg_type == "motion.stop":
        return "amy/motion/all/stop"
    if msg_type == "command.request" and dst in {ESP32_L, ESP32_T}:
        return "amy/commands/%s/request" % dst.replace("amy-", "")
    if msg_type == "command.safe_reset" and dst in {ESP32_L, ESP32_T}:
        return "amy/commands/%s/safe-reset" % dst.replace("amy-", "")
    if msg_type == "command.ping" and dst in {ESP32_L, ESP32_T}:
        return "amy/commands/%s/ping" % dst.replace("amy-", "")
    return None
