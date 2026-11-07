"""Servizio Smart Home su MQTT, senza produttore obbligatorio.

I dispositivi sono descritti in `home.devices`; il broker e le credenziali sono
configurabili. Se il broker non è configurato o `paho-mqtt` non è installato, il
servizio lo dichiara e non finge di aver acceso nulla.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from ..core.errors import AmyError


class HomeError(AmyError):
    code = "home_error"


class HomeService:
    def __init__(self, config: Any) -> None:
        self.config = config

    def enabled(self) -> bool:
        return bool(self.config.get("home.enabled", False))

    def devices(self) -> List[Dict[str, Any]]:
        raw = self.config.get("home.devices", []) or []
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            device_id = str(item.get("id", "") or "").strip()
            if not device_id:
                continue
            result.append(
                {
                    "id": device_id,
                    "name": str(item.get("name", device_id)),
                    "type": str(item.get("type", "dispositivo")),
                    "room": str(item.get("room", "")),
                    "state_topic": str(item.get("state_topic", "")),
                    "command_topic": str(item.get("command_topic", "")),
                    "unit": str(item.get("unit", "")),
                }
            )
        return result

    def device(self, device_id: str) -> Dict[str, Any]:
        wanted = str(device_id or "").strip()
        for item in self.devices():
            if item["id"] == wanted:
                return item
        raise HomeError("Dispositivo non configurato: %s" % wanted)

    def _client(self):
        if not self.enabled():
            raise HomeError("Smart Home disattivato nella configurazione.")
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise HomeError(
                "paho-mqtt non è installato: installalo per usare la domotica.",
                detail="pip3 install --user paho-mqtt",
            ) from exc
        broker = str(self.config.get("home.broker", "") or "").strip()
        if not broker:
            raise HomeError("Broker MQTT non configurato (home.broker).")
        client = mqtt.Client()
        username = str(self.config.get("home.username", "") or "").strip()
        if username:
            env = str(self.config.get("home.password_env", "AMY_HOME_MQTT_PASSWORD"))
            password = os.environ.get(env, "")
            if password:
                client.username_pw_set(username, password)
        client.connect(
            broker,
            int(self.config.get("home.port", 1883)),
            keepalive=30,
        )
        client.loop_start()
        return client

    def set(self, device_id: str, value: str) -> Dict[str, Any]:
        device = self.device(device_id)
        topic = device["command_topic"]
        if not topic:
            raise HomeError("Il dispositivo %s non ha un command_topic." % device_id)
        client = self._client()
        try:
            info = client.publish(str(topic), str(value))
            info.wait_for_publish(timeout=5)
        finally:
            client.loop_stop()
            client.disconnect()
        return {
            "device": device_id,
            "topic": topic,
            "payload": str(value),
            "published": True,
            "verified": False,
            "note": "Comando inviato; lo stato non è verificato senza una lettura del sensore.",
        }

    def state(self, device_id: str) -> Dict[str, Any]:
        device = self.device(device_id)
        topic = device["state_topic"]
        if not topic:
            raise HomeError("Il dispositivo %s non ha uno state_topic." % device_id)
        client = self._client()
        received: List[str] = []

        def on_message(_client, _userdata, message):
            received.append(message.payload.decode("utf-8", errors="replace"))

        client.on_message = on_message
        client.subscribe(str(topic))
        deadline = time.monotonic() + float(self.config.get("home.timeout_s", 5))
        while time.monotonic() < deadline and not received:
            time.sleep(0.1)
        client.loop_stop()
        client.disconnect()
        if not received:
            raise HomeError(
                "Nessuno stato ricevuto dal dispositivo %s." % device_id,
                detail="Verifica che il sensore sia online e pubblichi su %s." % topic,
            )
        return {"device": device_id, "topic": topic, "value": received[-1], "verified": True}
