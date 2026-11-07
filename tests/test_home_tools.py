"""Test della Smart Home opzionale (Fase 7).

Nessun broker MQTT reale: i test verificano la configurazione, il rifiuto
onesto quando il modulo è spento e i comandi pubblicati tramite un client finto.
"""

from __future__ import annotations

import unittest
from unittest import mock

from amy.home import HomeError, HomeService
from amy.memory.store import MemoryStore
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools import home_tools
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy

DEVICES = [
    {
        "id": "luce_salotto",
        "name": "Luce salotto",
        "type": "luce",
        "room": "salotto",
        "state_topic": "casa/salotto/luce/stato",
        "command_topic": "casa/salotto/luce/set",
    },
    {
        "id": "temperatura",
        "name": "Temperatura",
        "type": "sensore",
        "room": "cucina",
        "state_topic": "casa/cucina/temperatura",
        "unit": "°C",
    },
]


class FakeClient:
    def __init__(self) -> None:
        self.messages = []
        self.subscriptions = []
        self.on_message = None

    def username_pw_set(self, username, password) -> None:  # pragma: no cover - non usato
        self.credentials = (username, password)

    def connect(self, broker, port, keepalive=30) -> None:
        self.connected = (broker, port)

    def loop_start(self) -> None:
        pass

    def loop_stop(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def publish(self, topic, payload):
        self.messages.append((topic, payload))
        return mock.Mock()

    def subscribe(self, topic) -> None:
        self.subscriptions.append(topic)


class HomeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.temp.config.data["home"]["devices"] = DEVICES
        self.memory = MemoryStore(str(self.temp.home / "home.db"))
        self.registry = build_default_registry()
        self.context = ToolContext(
            config=self.temp.config,
            memory=self.memory,
            path_guard=PathGuard([self.temp.files], max_file_bytes=1024),
            audit=NullAudit(),
        )

    def tearDown(self) -> None:
        self.memory.close()
        self.temp.close()

    def test_home_is_disabled_by_default(self) -> None:
        self.assertFalse(self.temp.config.get("home.enabled", True))
        for name, args in (
            ("home.devices", {}),
            ("home.state", {"device": "luce_salotto"}),
            ("home.set", {"device": "luce_salotto", "value": "on"}),
            ("home.scene", {"name": "sera"}),
        ):
            result = self.registry.execute(name, args, self.context)
            self.assertFalse(result.ok, name)
            self.assertEqual(result.error_code, "home_disabled", name)

    def test_devices_are_listed_from_config(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        result = self.registry.execute("home.devices", {}, self.context)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 2)
        self.assertEqual(result.data["devices"][0]["id"], "luce_salotto")

    def test_set_publishes_on_command_topic(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        self.temp.config.data["home"]["broker"] = "127.0.0.1"
        client = FakeClient()
        with mock.patch.object(HomeService, "_client", return_value=client):
            result = self.registry.execute(
                "home.set", {"device": "luce_salotto", "value": "on"}, self.context
            )
        self.assertTrue(result.ok)
        self.assertEqual(client.messages, [("casa/salotto/luce/set", "on")])
        self.assertFalse(result.data["verified"])

    def test_state_reads_from_subscription(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        self.temp.config.data["home"]["broker"] = "127.0.0.1"
        self.temp.config.data["home"]["timeout_s"] = 0.2
        client = FakeClient()

        def subscribe(topic):
            client.subscriptions.append(topic)
            message = mock.Mock()
            message.payload = b"21.5"
            client.on_message(client, None, message)

        client.subscribe = subscribe
        with mock.patch.object(HomeService, "_client", return_value=client):
            result = self.registry.execute("home.state", {"device": "temperatura"}, self.context)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["value"], "21.5")
        self.assertTrue(result.data["verified"])

    def test_scene_is_refused_without_configuration(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        result = self.registry.execute("home.scene", {"name": "sera"}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "home_scene_missing")

    def test_scene_uses_configured_device(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        self.temp.config.data["home"]["broker"] = "127.0.0.1"
        self.temp.config.data["home"]["scenes"] = [
            {"name": "sera", "device": "luce_salotto", "value": "off"}
        ]
        client = FakeClient()
        with mock.patch.object(HomeService, "_client", return_value=client):
            result = self.registry.execute("home.scene", {"name": "sera"}, self.context)
        self.assertTrue(result.ok)
        self.assertEqual(client.messages, [("casa/salotto/luce/set", "off")])

    def test_unknown_device_is_reported(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        result = self.registry.execute("home.set", {"device": "ignoto", "value": "on"}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "internal_error")

    def test_missing_broker_is_reported(self) -> None:
        self.temp.config.data["home"]["enabled"] = True
        service = HomeService(self.temp.config)
        with self.assertRaises(HomeError):
            service.set("luce_salotto", "on")

    def test_risk_levels(self) -> None:
        self.assertEqual(home_tools.HOME_DEVICES.risk, RiskLevel.A)
        self.assertEqual(home_tools.HOME_STATE.risk, RiskLevel.A)
        self.assertEqual(home_tools.HOME_SET.risk, RiskLevel.B)
        self.assertEqual(home_tools.HOME_SCENE.risk, RiskLevel.C)

    def test_home_module_is_degraded_by_default(self) -> None:
        from amy.modules import build_module_registry

        registry = build_module_registry(self.temp.config)
        modules = {item["manifest"]["name"]: item for item in registry.statuses()}
        self.assertFalse(modules["home"]["enabled"])
        self.assertEqual(modules["home"]["status"]["state"], "disabled")
        self.assertFalse(modules["home"]["status"]["available"])


if __name__ == "__main__":
    unittest.main()
