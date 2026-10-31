"""Collegamento al robot: simulatore locale o broker MQTT.

Il trasporto predefinito è ``simulated``: nessun hardware viene contattato.
Il trasporto ``mqtt`` è sperimentale e richiede un broker raggiungibile e
credenziali configurate. Non è stato verificato su hardware reale.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from ..core.config import get_secret
from ..core.errors import RobotError, RobotProtocolError
from ..core.logging_setup import get_logger
from .protocol import (
    ESP32_L,
    ESP32_T,
    PI_ID,
    command_topic,
    make_envelope,
    new_req_id,
)

_log = get_logger("robot.link")


class RobotLink:
    name = "base"

    def status(self) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def move(self, joints: List[Dict[str, Any]], *, speed_limit_dps: float = 15.0, deadline_ms: int = 3000, head: bool = False) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def stop(self, reason: str = "operator") -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def estop(self, reason: str = "operator") -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def reset_estop(self, *, operator_ack: bool = False) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def set_mode(self, mode: str) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def ping(self) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        return None


class SimulatedLink(RobotLink):
    name = "simulated"

    def __init__(self, simulator) -> None:
        self.simulator = simulator
        self._seq: Dict[str, int] = {}

    def _send(self, msg_type: str, dst: str, payload: Dict[str, Any], req_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self.simulator.heartbeat()
        seq = self._seq.get(dst, 0) + 1
        self._seq[dst] = seq
        envelope = make_envelope(
            msg_type,
            src=PI_ID,
            dst=dst,
            payload=payload,
            req_id=req_id or new_req_id(),
            seq=seq,
        )
        return self.simulator.handle(envelope)

    def _with_messages(self, result: Dict[str, Any]) -> Dict[str, Any]:
        messages = self.simulator.drain_messages()
        result = dict(result)
        result["messages"] = messages
        result["simulated"] = True
        result["physical_motion"] = False
        return result

    def status(self) -> Dict[str, Any]:
        return self.simulator.status()

    def move(
        self,
        joints: List[Dict[str, Any]],
        *,
        speed_limit_dps: float = 15.0,
        deadline_ms: int = 3000,
        head: bool = False,
    ) -> Dict[str, Any]:
        dst = ESP32_T if head else ESP32_L
        msg_type = "motion.head" if head else "motion.target"
        payload = {
            "joints": joints,
            "speed_limit_dps": speed_limit_dps,
            "deadline_ms": deadline_ms,
            "limits_version": self.simulator.limits_version,
        }
        req_id = new_req_id()
        ack = self._send(msg_type, dst, payload, req_id)
        result = None
        if ack and ack["type"] == "command.ack" and ack["payload"].get("outcome") in {"accepted", "already_done"}:
            result = self.simulator.advance_to_completion()
        self.simulator.drain_messages()
        return {
            "ack": ack,
            "result": result,
            "status": self.simulator.status(),
            "simulated": True,
            "physical_motion": False,
            "completion_verified": bool(
                result and result.get("payload", {}).get("result") == "completed"
            ),
        }

    def stop(self, reason: str = "operator") -> Dict[str, Any]:
        result = self.simulator.stop(reason)
        result = self._with_messages(result)
        result["status"] = self.simulator.status()
        return result

    def estop(self, reason: str = "operator") -> Dict[str, Any]:
        event = self.simulator.estop(reason)
        return {
            "event": event,
            "status": self.simulator.status(),
            "simulated": True,
            "physical_motion": False,
            "nota": "L'E-stop software non sostituisce l'E-stop fisico in serie al bus dei servi.",
        }

    def reset_estop(self, *, operator_ack: bool = False) -> Dict[str, Any]:
        result = self.simulator.reset_estop(operator_ack=operator_ack)
        result["status"] = self.simulator.status()
        return result

    def set_mode(self, mode: str) -> Dict[str, Any]:
        return self.simulator.set_mode(mode)

    def ping(self) -> Dict[str, Any]:
        start = time.monotonic()
        ack = self._send("command.ping", ESP32_L, {}, new_req_id())
        return {
            "reachable": bool(ack and ack.get("type") == "command.ack"),
            "rtt_ms": round((time.monotonic() - start) * 1000, 2),
            "transport": "simulated",
            "status": self.simulator.status(),
        }


class MqttRobotLink(RobotLink):
    """Link MQTT sperimentale verso un broker locale.

    Nota architetturale: nella specifica canonica il Mac parla con il Pi via
    HTTP/JSON e il Pi è l'autorità MQTT. Questo link consente una prova di
    laboratorio diretta e richiede che il broker autorizzi il client ``amy-brain``.
    """

    name = "mqtt"

    def __init__(self, config) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
            raise RobotError(
                "paho-mqtt non è installato: il trasporto MQTT non è disponibile.",
                detail="Installa con: python3 -m pip install paho-mqtt",
            ) from exc

        self._mqtt = mqtt
        self.host = str(config.get("robot.host"))
        self.port = int(config.get("robot.port", 1883))
        self.username = str(config.get("robot.username", "amy-pi"))
        self.password = get_secret(str(config.get("robot.password_env", "AMY_MQTT_PASSWORD")))
        self.timeout_s = float(config.get("robot.timeout_s", 3.0))
        self.tls = bool(config.get("robot.tls", False))
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="amy-brain",
            protocol=mqtt.MQTTv5,
        )
        if self.username:
            self._client.username_pw_set(self.username, self.password or "")
        if self.tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._connected = False
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._latest_status: Dict[str, Any] = {}
        self._seq: Dict[str, int] = {}
        self._last_error = ""

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = int(reason_code) == 0 if str(reason_code).isdigit() else str(reason_code) == "Success"
        if self._connected:
            for topic in (
                "amy/commands/+/ack",
                "amy/commands/+/nack",
                "amy/status/esp32-l",
                "amy/status/esp32-t",
                "amy/events/+/safety",
                "amy/motion/+/result",
            ):
                client.subscribe(topic, qos=1)
            _log.info("Connesso al broker MQTT %s:%s", self.host, self.port)
        else:
            self._last_error = "connessione rifiutata: %s" % reason_code

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = False

    def _on_message(self, client, userdata, message):
        try:
            data = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if "payload" not in data:
            return
        topic = message.topic
        if topic.startswith("amy/status/"):
            self._latest_status[topic.rsplit("/", 1)[-1]] = data
        req_id = data.get("req_id")
        if req_id and topic.startswith("amy/commands/"):
            with self._lock:
                entry = self._pending.get(req_id)
                if entry is not None:
                    entry["response"] = data
                    entry["event"].set()

    def connect(self) -> None:
        if self._connected:
            return
        try:
            self._client.connect(self.host, self.port, keepalive=10)
            self._client.loop_start()
        except OSError as exc:
            raise RobotError(
                "Impossibile connettersi al broker MQTT.",
                detail="%s:%s — %s" % (self.host, self.port, exc),
            ) from exc
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline and not self._connected:
            time.sleep(0.05)
        if not self._connected:
            self._client.loop_stop()
            raise RobotError(
                "Connessione MQTT non stabilita entro il timeout.",
                detail=self._last_error or "verifica host, credenziali e broker",
            )

    def _request(self, msg_type: str, dst: str, payload: Dict[str, Any], *, wait: bool = True) -> Dict[str, Any]:
        self.connect()
        topic = command_topic(msg_type, dst)
        if not topic:
            raise RobotError("Nessun topic MQTT per il comando %s verso %s." % (msg_type, dst))
        req_id = new_req_id()
        with self._lock:
            seq = self._seq.get(dst, 0) + 1
            self._seq[dst] = seq
        envelope = make_envelope(msg_type, src=PI_ID, dst=dst, payload=payload, req_id=req_id, seq=seq)
        entry = {"event": threading.Event(), "response": None}
        with self._lock:
            self._pending[req_id] = entry
        info = self._client.publish(topic, json.dumps(envelope), qos=1)
        if info.rc != 0:
            raise RobotError("Pubblicazione MQTT non riuscita.", detail=str(info.rc))
        if not wait:
            return {"published": True, "req_id": req_id, "topic": topic}
        if not entry["event"].wait(self.timeout_s):
            with self._lock:
                self._pending.pop(req_id, None)
            raise RobotError(
                "Nessun esito dal robot entro %.1f secondi." % self.timeout_s,
                detail="Il comando potrebbe essere stato ricevuto: non assumere che non sia avvenuto.",
            )
        with self._lock:
            self._pending.pop(req_id, None)
        return {"response": entry["response"], "req_id": req_id, "completion_verified": False}

    def status(self) -> Dict[str, Any]:
        try:
            response = self._request("command.request", ESP32_L, {"what": "status"})
            data = response["response"]
            return {
                "reachable": True,
                "transport": "mqtt",
                "response": data,
                "simulated": False,
                "note": "Stato ricevuto dal nodo; nessun movimento è stato verificato.",
            }
        except RobotError as exc:
            return {
                "reachable": False,
                "transport": "mqtt",
                "error": exc.message,
                "simulated": False,
            }

    def move(self, joints, *, speed_limit_dps=15.0, deadline_ms=3000, head=False) -> Dict[str, Any]:
        dst = ESP32_T if head else ESP32_L
        msg_type = "motion.head" if head else "motion.target"
        payload = {
            "joints": joints,
            "speed_limit_dps": speed_limit_dps,
            "deadline_ms": deadline_ms,
        }
        response = self._request(msg_type, dst, payload)
        return {
            "ack": response["response"],
            "result": None,
            "simulated": False,
            "physical_motion": False,
            "completion_verified": False,
            "nota": "ACK di accettazione ricevuto: il completamento richiede motion.result.",
        }

    def stop(self, reason: str = "operator") -> Dict[str, Any]:
        response = self._request("motion.stop", ESP32_L, {"reason": reason})
        return {"response": response["response"], "simulated": False, "physical_motion": False}

    def estop(self, reason: str = "operator") -> Dict[str, Any]:
        # L'E-stop software è un arresto controllato; quello fisico resta esterno.
        try:
            response = self._request("motion.stop", ESP32_L, {"reason": "estop_soft"})
            return {
                "sent": True,
                "response": response["response"],
                "physical_estop": False,
                "nota": "Usa l'E-stop fisico: il software non può garantirlo.",
            }
        except RobotError as exc:
            return {"sent": False, "error": exc.message, "physical_estop": False}

    def reset_estop(self, *, operator_ack: bool = False) -> Dict[str, Any]:
        if not operator_ack:
            raise RobotError("Il reset dell'E-stop richiede operator_ack esplicito.")
        response = self._request("command.safe_reset", ESP32_L, {"operator_ack": True})
        return {"response": response["response"], "simulated": False}

    def set_mode(self, mode: str) -> Dict[str, Any]:
        raise RobotError(
            "Il protocollo v1 non definisce un comando di cambio modalità per il nodo reale.",
            detail="La modalità operativa è gestita dal dispatcher sul Pi.",
        )

    def ping(self) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            response = self._request("command.ping", ESP32_L, {})
        except RobotError as exc:
            return {"reachable": False, "error": exc.message}
        return {
            "reachable": True,
            "rtt_ms": round((time.monotonic() - start) * 1000, 1),
            "response": response["response"],
        }

    def close(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass


def build_robot_link(config) -> RobotLink:
    transport = str(config.get("robot.transport", "simulated")).lower()
    if transport == "mqtt":
        return MqttRobotLink(config)
    from .simulator import RobotSimulator

    simulator = RobotSimulator(
        battery_pct=float(config.get("robot.simulator.battery_pct", 87)),
        watchdog_timeout_s=float(config.get("robot.simulator.watchdog_timeout_s", 5)),
    )
    return SimulatedLink(simulator)
