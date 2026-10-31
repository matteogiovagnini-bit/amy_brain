"""Simulatore del robot Amy.

Riproduce il comportamento *verificabile* del protocollo lato dispositivo:
- validazione dell'envelope e dei limiti;
- ACK/NACK con `req_id` e deduplicazione;
- watchdog su heartbeat;
- arresto di emergenza con priorità assoluta;
- modalità TEST senza movimento fisico.

Non è un firmware e non dimostra nulla sull'hardware reale: tutti i movimenti
sono simulati e il campo ``simulated`` è sempre esplicito.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable, Dict, List, Optional

from ..core.errors import RobotProtocolError
from .protocol import (
    ESP32_L,
    ESP32_T,
    PI_ID,
    JointLimit,
    default_limits,
    make_envelope,
    validate_envelope,
    validate_motion_target,
)

DEDUP_WINDOW_S = 30.0
DEDUP_SIZE = 64


class RobotSimulator:
    def __init__(
        self,
        *,
        battery_pct: float = 87.0,
        watchdog_timeout_s: float = 5.0,
        limits: Optional[List[JointLimit]] = None,
        clock: Optional[Callable[[], float]] = None,
        auto_complete: bool = False,
    ) -> None:
        self._clock = clock or time.monotonic
        self.limits = {limit.joint: limit for limit in (limits or default_limits())}
        self.limits_version = 1
        self.battery_pct = float(battery_pct)
        self.watchdog_timeout_s = float(watchdog_timeout_s)
        self.auto_complete = auto_complete

        self.connected = True
        self.mode = "TEST"  # TEST | IDLE | READY | SAFE | ESTOP
        self.motion_phase = "IDLE"  # IDLE | MOVING | HOLD | DECEL
        self.estop_latched = False
        self.fault_latched = False
        self.fault_code = ""
        self.joints: Dict[str, Dict[str, Any]] = {
            name: {
                "joint": name,
                "current_deg": 0.0,
                "target_deg": 0.0,
                "estimated": True,
                "calibrated": limit.calibrated,
            }
            for name, limit in self.limits.items()
        }
        self.active_trajectory_id: Optional[str] = None
        self.active_req_id: Optional[str] = None
        self.active_node: Optional[str] = None
        self.active_deadline_ms = 0
        self.motion_started_at = 0.0
        self.last_result: Optional[Dict[str, Any]] = None

        self.last_pi_heartbeat = self._clock()
        self.last_pi_seq: Dict[str, int] = {}
        self._out_seq: Dict[tuple, int] = {}
        self._dedup: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, Any]] = []
        self.command_log: List[Dict[str, Any]] = []

    # --------------------------------------------------------------- utilità
    def _node_for(self, dst: str) -> str:
        if dst not in {ESP32_L, ESP32_T}:
            raise RobotProtocolError("Destinatario non valido per il simulatore.", detail=dst)
        return dst

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def _next_seq(self, src: str, channel: str) -> int:
        key = (src, channel)
        value = self._out_seq.get(key, 0) + 1
        self._out_seq[key] = value
        return value

    def _ack(self, *, node: str, req_id: str, command: str, outcome: str = "accepted", **payload: Any) -> Dict[str, Any]:
        body = {"outcome": outcome, "command": command, "req_id": req_id}
        body.update(payload)
        envelope = make_envelope(
            "command.ack",
            src=node,
            dst=PI_ID,
            payload=body,
            req_id=req_id,
            seq=self._next_seq(node, "command.ack"),
            ts=self._timestamp(),
        )
        self.messages.append(envelope)
        return envelope

    def _nack(
        self,
        *,
        node: str,
        req_id: str,
        command: str,
        code: str,
        detail: str = "",
        remediation: str = "",
        retryable: bool = False,
    ) -> Dict[str, Any]:
        body = {
            "outcome": "rejected",
            "command": command,
            "req_id": req_id,
            "code": code,
            "detail": detail,
            "remediation": remediation,
            "retryable": retryable,
        }
        envelope = make_envelope(
            "command.nack",
            src=node,
            dst=PI_ID,
            payload=body,
            req_id=req_id,
            seq=self._next_seq(node, "command.nack"),
            ts=self._timestamp(),
        )
        self.messages.append(envelope)
        return envelope

    def _event(self, *, node: str, code: str, severity: str, detail: str, **payload: Any) -> Dict[str, Any]:
        body = {
            "code": code,
            "severity": severity,
            "safe_state": "HOLD",
            "detail": detail,
            "replayed": False,
            "clock_synced": True,
            "simulated": True,
        }
        body.update(payload)
        envelope = make_envelope(
            "event.safety",
            src=node,
            dst=PI_ID,
            payload=body,
            req_id=None,
            seq=self._next_seq(node, "event.safety"),
            ts=self._timestamp(),
        )
        self.events.append(envelope)
        self.messages.append(envelope)
        return envelope

    def status(self) -> Dict[str, Any]:
        now = self._clock()
        return {
            "connected": self.connected,
            "simulated": True,
            "physical_motion": False,
            "mode": self.mode,
            "motion_phase": self.motion_phase,
            "estop_latched": self.estop_latched,
            "fault_latched": self.fault_latched,
            "fault_code": self.fault_code,
            "battery_pct": round(self.battery_pct, 1),
            "battery_estimated": True,
            "watchdog_timeout_s": self.watchdog_timeout_s,
            "last_heartbeat_age_ms": int((now - self.last_pi_heartbeat) * 1000),
            "limits_version": self.limits_version,
            "calibrated": all(limit.calibrated for limit in self.limits.values()),
            "active_trajectory_id": self.active_trajectory_id,
            "joints": [dict(joint) for joint in self.joints.values()],
            "limits": [limit.to_dict() for limit in self.limits.values()],
        }

    # --------------------------------------------------------------- comandi
    def handle(self, envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            validate_envelope(envelope)
        except RobotProtocolError as exc:
            # Non possiamo rispondere senza un req_id valido: registriamo l'errore.
            self.events.append({"invalid": True, "error": exc.to_dict()})
            raise
        if envelope["src"] != PI_ID:
            raise RobotProtocolError("Solo il Pi può inviare comandi al simulatore.")
        node = self._node_for(envelope["dst"])
        msg_type = envelope["type"]
        req_id = envelope["req_id"]
        payload = envelope["payload"]

        if msg_type == "system.heartbeat":
            self.last_pi_heartbeat = self._clock()
            return None

        if req_id is None:
            # Senza req_id non esiste correlazione: il comando non è eseguibile
            # e non si può produrre un ACK/NACK valido.
            self.events.append(
                {
                    "invalid": True,
                    "error": "req_id obbligatorio per i comandi",
                    "type": msg_type,
                }
            )
            return None

        # Deduplicazione prima della sequenza: una ritrasmissione non è un nuovo comando.
        existing = self._dedup.get(req_id)
        payload_hash = hashlib.sha1(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        now = self._clock()
        if existing and now - existing["at"] <= DEDUP_WINDOW_S:
            if existing["hash"] != payload_hash:
                return self._nack(
                    node=node,
                    req_id=req_id,
                    command=msg_type,
                    code="duplicate_conflict",
                    detail="Lo stesso req_id è già stato usato con un payload diverso.",
                )
            return self._ack(
                node=node,
                req_id=req_id,
                command=msg_type,
                outcome="already_done",
                original_outcome=existing["outcome"],
            )

        expected = self.last_pi_seq.get(node, 0)
        if envelope["seq"] > expected + 1:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="seq_gap",
                detail="Atteso seq %d, ricevuto %d." % (expected + 1, envelope["seq"]),
                remediation="Ritrasmettere il comando mancante con lo stesso req_id.",
            )
        if envelope["seq"] <= expected:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="stale_seq",
                detail="seq %d non è successivo a %d." % (envelope["seq"], expected),
            )
        self.last_pi_seq[node] = envelope["seq"]

        try:
            if msg_type == "command.ping":
                response = self._ack(node=node, req_id=req_id, command=msg_type, rtt_hint="simulated")
            elif msg_type == "command.request":
                response = self._ack(node=node, req_id=req_id, command=msg_type, status=self.status())
            elif msg_type == "command.safe_reset":
                response = self._safe_reset(node, req_id, payload)
            elif msg_type == "command.limits":
                response = self._update_limits(node, req_id, payload)
            elif msg_type == "command.params":
                response = self._update_params(node, req_id, payload)
            elif msg_type in {"motion.target", "motion.head"}:
                response = self._move(node, req_id, msg_type, payload)
            elif msg_type == "motion.sequence":
                response = self._nack(
                    node=node,
                    req_id=req_id,
                    command=msg_type,
                    code="feature_not_supported",
                    detail="Il simulatore v1 non implementa le sequenze multi-waypoint.",
                )
            elif msg_type == "motion.stop":
                response = self._stop_command(node, req_id, payload)
            else:
                response = self._nack(
                    node=node,
                    req_id=req_id,
                    command=msg_type,
                    code="unknown_type",
                    detail="Tipo non gestito dal simulatore.",
                )
        except RobotProtocolError as exc:
            code = "out_of_limits" if "limiti" in exc.message.lower() else "invalid_payload"
            response = self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code=code,
                detail=("%s %s" % (exc.message, exc.detail)).strip(),
                retryable=False,
            )

        self._dedup[req_id] = {
            "at": now,
            "hash": payload_hash,
            "outcome": response["payload"]["outcome"],
        }
        if len(self._dedup) > DEDUP_SIZE:
            oldest = sorted(self._dedup.items(), key=lambda item: item[1]["at"])[0][0]
            self._dedup.pop(oldest, None)
        self.command_log.append(
            {
                "at": now,
                "type": msg_type,
                "req_id": req_id,
                "outcome": response["payload"]["outcome"],
                "node": node,
            }
        )
        return response

    def _safe_reset(self, node: str, req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("operator_ack") is not True:
            return self._nack(
                node=node,
                req_id=req_id,
                command="command.safe_reset",
                code="invalid_payload",
                detail="Serve operator_ack=true per un reset sicuro.",
            )
        if not self.estop_latched and not self.fault_latched:
            return self._ack(
                node=node,
                req_id=req_id,
                command="command.safe_reset",
                outcome="already_done",
                note="Nessun latch attivo.",
            )
        self.estop_latched = False
        self.fault_latched = False
        self.fault_code = ""
        self.mode = "TEST"
        self.motion_phase = "IDLE"
        self.active_trajectory_id = None
        self.active_req_id = None
        self._event(
            node=node,
            code="safe_reset",
            severity="info",
            detail="Latch di sicurezza azzerato dall'operatore. Nessun movimento ripreso.",
        )
        return self._ack(
            node=node,
            req_id=req_id,
            command="command.safe_reset",
            note="Reset sicuro eseguito; attuatori non riattivati automaticamente.",
        )

    def _update_limits(self, node: str, req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        version = payload.get("limits_version")
        if not isinstance(version, int) or isinstance(version, bool) or version <= self.limits_version:
            return self._nack(
                node=node,
                req_id=req_id,
                command="command.limits",
                code="invalid_payload",
                detail="limits_version deve essere superiore a %d." % self.limits_version,
            )
        entries = payload.get("joints")
        if not isinstance(entries, list) or not entries:
            return self._nack(
                node=node,
                req_id=req_id,
                command="command.limits",
                code="invalid_payload",
                detail="Elenco giunti mancante.",
            )
        updated = dict(self.limits)
        for item in entries:
            if not isinstance(item, dict) or item.get("joint") not in updated:
                return self._nack(
                    node=node,
                    req_id=req_id,
                    command="command.limits",
                    code="invalid_payload",
                    detail="Giunto non valido nei limiti.",
                )
            old = updated[str(item["joint"])]
            try:
                low = float(item["min_deg"])
                high = float(item["max_deg"])
                speed = float(item.get("max_speed_dps", old.max_speed_dps))
                accel = float(item.get("max_accel_dps2", old.max_accel_dps2))
            except (KeyError, TypeError, ValueError):
                return self._nack(
                    node=node,
                    req_id=req_id,
                    command="command.limits",
                    code="invalid_payload",
                    detail="Valori numerici non validi nei limiti.",
                )
            if not all(math.isfinite(value) for value in (low, high, speed, accel)) or low >= high:
                return self._nack(
                    node=node,
                    req_id=req_id,
                    command="command.limits",
                    code="invalid_payload",
                    detail="Intervallo limiti non valido.",
                )
            zero = item.get("zero_offset_deg", old.zero_offset_deg)
            updated[str(item["joint"])] = JointLimit(
                joint=old.joint,
                min_deg=low,
                max_deg=high,
                max_speed_dps=min(max(speed, 1.0), 180.0),
                max_accel_dps2=min(max(accel, 1.0), 360.0),
                zero_offset_deg=None if zero is None else float(zero),
                soft_limit_deg=item.get("soft_limit_deg", old.soft_limit_deg),
            )
        self.limits = updated
        self.limits_version = version
        for name, joint in self.joints.items():
            joint["calibrated"] = self.limits[name].calibrated
        return self._ack(
            node=node,
            req_id=req_id,
            command="command.limits",
            limits_version=version,
            applied=[limit.to_dict() for limit in self.limits.values()],
        )

    def _update_params(self, node: str, req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "watchdog_timeout_ms" in payload:
            value = payload["watchdog_timeout_ms"]
            if not isinstance(value, int) or isinstance(value, bool) or not (1000 <= value <= 10000):
                return self._nack(
                    node=node,
                    req_id=req_id,
                    command="command.params",
                    code="invalid_payload",
                    detail="watchdog_timeout_ms deve essere tra 1000 e 10000.",
                )
            self.watchdog_timeout_s = value / 1000.0
        return self._ack(node=node, req_id=req_id, command="command.params", applied=dict(payload))

    def _move(self, node: str, req_id: str, msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.estop_latched:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="node_safe",
                detail="E-stop attivo: nessun movimento consentito.",
                remediation="Verificare l'area e usare command.safe_reset con operator_ack.",
            )
        if self.fault_latched:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="node_degraded",
                detail="Nodo in guasto latched.",
            )
        if self.mode not in {"TEST", "READY"}:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="not_ready",
                detail="Modalità operativa %s: porta il robot in TEST o READY." % self.mode,
            )
        if self.mode == "READY" and not all(limit.calibrated for limit in self.limits.values()):
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="not_ready",
                detail="Calibrazione meccanica non eseguita: zero_offset_deg assente.",
                remediation="Completa la calibrazione o usa la modalità TEST (nessun movimento fisico).",
            )
        requested_limits_version = payload.get("limits_version")
        if requested_limits_version is not None and requested_limits_version != self.limits_version:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="invalid_payload",
                detail="limits_version=%r diversa da quella in vigore (%d)."
                % (requested_limits_version, self.limits_version),
                remediation="Richiedere lo stato dei limiti e riallineare il comando.",
            )
        if self.motion_phase == "MOVING":
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="node_degraded",
                detail="Movimento già in corso: attendere o inviare motion.stop.",
            )
        if self.battery_pct <= 5.0:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="node_degraded",
                detail="Batteria troppo bassa (%.1f%%)." % self.battery_pct,
            )

        if msg_type == "motion.head":
            subset = {name: self.limits[name] for name in ("head_pan", "head_tilt")}
            payload = dict(payload)
            payload["joints"] = payload.get("joints", [])
            if "pan_deg" in payload:
                payload["joints"] = [{"joint": "head_pan", "position_deg": payload["pan_deg"]}]
                if "tilt_deg" in payload:
                    payload["joints"].append({"joint": "head_tilt", "position_deg": payload["tilt_deg"]})
        else:
            subset = self.limits
        validated = validate_motion_target(payload, subset)

        trajectory_id = str(payload.get("trajectory_id") or req_id)
        duration_s = 0.0
        for item in validated:
            delta = abs(item["position_deg"] - float(self.joints[item["joint"]]["current_deg"]))
            duration_s = max(duration_s, delta / max(item["speed_limit_dps"], 0.1))
        deadline_s = int(payload.get("deadline_ms", 2000)) / 1000.0
        if duration_s > deadline_s + 0.001:
            return self._nack(
                node=node,
                req_id=req_id,
                command=msg_type,
                code="deadline_exceeded",
                detail="La traiettoria richiederebbe %.2fs, oltre la scadenza %.2fs." % (duration_s, deadline_s),
                remediation="Aumentare deadline_ms o ridurre la distanza/velocità.",
            )

        for item in validated:
            self.joints[item["joint"]]["target_deg"] = item["position_deg"]
            self.joints[item["joint"]]["speed_limit_dps"] = item["speed_limit_dps"]
        self.motion_phase = "MOVING"
        self.active_trajectory_id = trajectory_id
        self.active_req_id = req_id
        self.active_node = node
        self.active_deadline_ms = int(payload.get("deadline_ms", 2000))
        self.motion_started_at = self._clock()
        self.last_result = None
        self._event(
            node=node,
            code="motion_accepted",
            severity="info",
            detail="Traiettoria %s accettata in modalità %s." % (trajectory_id, self.mode),
            simulated=self.mode == "TEST",
        )
        ack = self._ack(
            node=node,
            req_id=req_id,
            command=msg_type,
            trajectory_id=trajectory_id,
            limits_version=self.limits_version,
            simulated=self.mode == "TEST",
            physical_motion=False,
            estimated_duration_s=round(duration_s, 2),
        )
        if self.auto_complete:
            self.advance(max(duration_s, 0.01))
        return ack

    def _stop_command(self, node: str, req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        reason = str(payload.get("reason", "operator"))
        self._apply_stop(node, reason)
        return self._ack(
            node=node,
            req_id=req_id,
            command="motion.stop",
            result="aborted",
            reason=reason,
            mode=self.mode,
        )

    def _apply_stop(self, node: str, reason: str) -> None:
        self.motion_phase = "HOLD" if not self.estop_latched else "IDLE"
        for joint in self.joints.values():
            joint["target_deg"] = joint["current_deg"]
        if self.active_trajectory_id and self.active_req_id:
            result = make_envelope(
                "motion.result",
                src=node,
                dst=PI_ID,
                payload={
                    "result": "aborted",
                    "reason": reason,
                    "trajectory_id": self.active_trajectory_id,
                    "simulated": True,
                    "physical_motion": False,
                },
                req_id=self.active_req_id,
                seq=self._next_seq(node, "motion.result"),
                ts=self._timestamp(),
            )
            self.last_result = result
            self.messages.append(result)
        self.active_trajectory_id = None
        self.active_req_id = None
        self._event(
            node=node,
            code="controlled_stop",
            severity="warning" if reason != "operator" else "info",
            detail="Arresto controllato: %s. Safe state HOLD." % reason,
            reason=reason,
        )

    # ------------------------------------------------------------ sicurezza
    def estop(self, reason: str = "operator") -> Dict[str, Any]:
        """Arresto di emergenza software: priorità assoluta, nessuna conferma."""
        self.estop_latched = True
        self.mode = "ESTOP"
        self.motion_phase = "IDLE"
        for joint in self.joints.values():
            joint["target_deg"] = joint["current_deg"]
        self.active_trajectory_id = None
        self.active_req_id = None
        event = self._event(
            node=ESP32_L,
            code="estop_soft",
            severity="critical",
            detail="E-stop software attivato: %s. Il rail fisico richiede l'E-stop hardware." % reason,
            reason=reason,
        )
        return event

    def reset_estop(self, *, operator_ack: bool = False) -> Dict[str, Any]:
        if not operator_ack:
            raise RobotProtocolError("Il reset dell'E-stop richiede una conferma esplicita dell'operatore.")
        if not self.estop_latched and not self.fault_latched:
            return {"reset": False, "reason": "nessun latch attivo"}
        self.estop_latched = False
        self.fault_latched = False
        self.mode = "TEST"
        self.motion_phase = "IDLE"
        self._event(
            node=ESP32_L,
            code="safe_reset",
            severity="info",
            detail="E-stop software azzerato. Il robot non riprende automaticamente.",
        )
        return {"reset": True, "mode": self.mode, "motion_resumed": False}

    def stop(self, reason: str = "operator") -> Dict[str, Any]:
        self._apply_stop(ESP32_L, reason)
        return {
            "stopped": True,
            "mode": self.mode,
            "motion_phase": self.motion_phase,
            "reason": reason,
            "simulated": True,
        }

    def set_mode(self, mode: str) -> Dict[str, Any]:
        mode = mode.upper()
        if mode not in {"TEST", "IDLE", "READY"}:
            raise RobotProtocolError("Modalità non ammessa: %s" % mode)
        if self.estop_latched:
            raise RobotProtocolError("E-stop attivo: azzerare il latch prima di cambiare modalità.")
        if mode == "READY" and not all(limit.calibrated for limit in self.limits.values()):
            raise RobotProtocolError(
                "Modalità READY non disponibile: calibrazione meccanica non eseguita.",
                detail="zero_offset_deg è null per almeno un giunto.",
            )
        self.mode = mode
        self.motion_phase = "IDLE"
        return self.status()

    # ------------------------------------------------------------- tempo
    def heartbeat(self) -> None:
        self.last_pi_heartbeat = self._clock()

    def advance(self, seconds: float) -> Optional[Dict[str, Any]]:
        """Avanza la simulazione e restituisce il risultato se una traiettoria termina."""
        seconds = max(0.0, float(seconds))
        now = self._clock()

        # Watchdog: indipendente dall'IA e dal comando corrente.
        if self.motion_phase == "MOVING" and (now - self.last_pi_heartbeat) > self.watchdog_timeout_s:
            node = self.active_node or ESP32_L
            self._apply_stop(node, "watchdog")
            self.fault_latched = True
            self.fault_code = "watchdog_s2"
            self.mode = "SAFE"
            self._event(
                node=node,
                code="watchdog_s2",
                severity="critical",
                detail="Nessun heartbeat del Pi per %.1fs: arresto controllato e SAFE." % self.watchdog_timeout_s,
                missed_heartbeats=int((now - self.last_pi_heartbeat) / 1.0),
            )
            return self.last_result

        if self.motion_phase != "MOVING":
            return None

        moved_any = False
        for item in self.joints.values():
            current = float(item["current_deg"])
            target = float(item["target_deg"])
            if abs(target - current) < 1e-6:
                continue
            # Velocità conservativa: 30 deg/s nel simulatore, salvo limiti più bassi.
            limit = self.limits[item["joint"]]
            speed = float(item.get("speed_limit_dps", limit.max_speed_dps))
            step = min(speed, limit.max_speed_dps) * seconds
            if abs(target - current) <= step:
                item["current_deg"] = target
            else:
                item["current_deg"] = current + math.copysign(step, target - current)
            moved_any = True
        if moved_any:
            self.battery_pct = max(0.0, self.battery_pct - min(0.05, seconds * 0.01))

        complete = all(
            abs(float(item["target_deg"]) - float(item["current_deg"])) < 1e-6
            for item in self.joints.values()
        )
        if complete:
            node = self.active_node or ESP32_L
            req_id = self.active_req_id
            trajectory = self.active_trajectory_id
            self.motion_phase = "IDLE"
            self.active_trajectory_id = None
            self.active_req_id = None
            self.active_node = None
            if req_id:
                result = make_envelope(
                    "motion.result",
                    src=node,
                    dst=PI_ID,
                    payload={
                        "result": "completed",
                        "reason": "target_reached",
                        "trajectory_id": trajectory,
                        "duration_ms": int((now - self.motion_started_at) * 1000),
                        "simulated": True,
                        "physical_motion": False,
                        "verified": False,
                        "note": "Posizione stimata dal simulatore; nessun feedback fisico disponibile.",
                    },
                    req_id=req_id,
                    seq=self._next_seq(node, "motion.result"),
                    ts=self._timestamp(),
                )
                self.last_result = result
                self.messages.append(result)
                return result
        return None

    def advance_to_completion(self, *, max_steps: int = 1000, dt: float = 0.1) -> Optional[Dict[str, Any]]:
        for _ in range(max_steps):
            result = self.advance(dt)
            if result is not None:
                return result
            if self.motion_phase != "MOVING":
                return self.last_result
        return self.last_result

    def drain_messages(self) -> List[Dict[str, Any]]:
        messages = list(self.messages)
        self.messages.clear()
        return messages

    def simulation_calibrate(self) -> None:
        """Solo per test: imposta zero fittizi. Non è esposto come strumento."""
        self.limits = {
            name: JointLimit(
                joint=limit.joint,
                min_deg=limit.min_deg,
                max_deg=limit.max_deg,
                max_speed_dps=limit.max_speed_dps,
                max_accel_dps2=limit.max_accel_dps2,
                zero_offset_deg=0.0,
                soft_limit_deg=limit.soft_limit_deg,
            )
            for name, limit in self.limits.items()
        }
        for name, joint in self.joints.items():
            joint["calibrated"] = True
