"""Test dello strumento `system.battery`.

Lo stato della batteria deve essere reale e locale: si legge con `pmset`, in sola
lettura. Il test non può dare per scontato che la macchina abbia una batteria,
quindi verifica sempre la struttura dei dati, non un valore preciso.
"""

from __future__ import annotations

import unittest

from amy.ai.offline import OfflineProvider
from amy.macos import battery_status, battery_summary, parse_battery_output
from amy.security.risk import RiskLevel
from amy.tools.builtin import build_default_registry

DISCHARGING = (
    "Now drawing from 'Battery Power'\n"
    " -InternalBattery-0 (id=7143523)\t87%; discharging; 3:56 remaining present: true"
)

CHARGED = (
    "Now drawing from 'AC Power'\n"
    " -InternalBattery-0 (id=7143523)\t100%; charged; 0:00 remaining present: true"
)

NO_BATTERY = "Now drawing from 'AC Power'\n"


class ParseBatteryTests(unittest.TestCase):
    def test_discharging_battery(self) -> None:
        data = parse_battery_output(DISCHARGING)
        self.assertIs(data["presente"], True)
        self.assertEqual(data["percentuale"], 87)
        self.assertEqual(data["stato"], "in scarica")
        self.assertEqual(data["tempo_rimanente"], "3:56")
        self.assertEqual(data["alimentazione"], "batteria")

    def test_charged_battery_on_power(self) -> None:
        data = parse_battery_output(CHARGED)
        self.assertIs(data["presente"], True)
        self.assertEqual(data["percentuale"], 100)
        self.assertEqual(data["stato"], "carica")
        self.assertEqual(data["alimentazione"], "rete")

    def test_machine_without_battery(self) -> None:
        data = parse_battery_output(NO_BATTERY)
        self.assertIs(data["presente"], False)
        self.assertIsNone(data["percentuale"])
        self.assertEqual(data["alimentazione"], "rete")

    def test_unreadable_output_does_not_invent_values(self) -> None:
        data = parse_battery_output("qualcosa dicompletely diverso")
        self.assertIs(data["presente"], False)
        self.assertIsNone(data["percentuale"])
        self.assertIsNone(data["stato"])

    def test_summary_is_italian_and_honest(self) -> None:
        summary = battery_summary(parse_battery_output(DISCHARGING))
        self.assertIn("87%", summary)
        self.assertIn("in scarica", summary)
        self.assertIn("3:56", summary)
        without = battery_summary(parse_battery_output(NO_BATTERY))
        self.assertIn("Nessuna batteria", without)

    def test_charged_battery_omits_useless_remaining_time(self) -> None:
        # Con la batteria carica `pmset` riporta «0:00 remaining»: non è un
        # tempo residuo utile e non va detto all'utente.
        summary = battery_summary(parse_battery_output(CHARGED))
        self.assertIn("100%", summary)
        self.assertIn("carica", summary)
        self.assertNotIn("0:00", summary)
        self.assertNotIn("rimanenti", summary)


class BatteryToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_tool_is_registered_as_read_only(self) -> None:
        tool = self.registry.get("system.battery")
        self.assertEqual(tool.spec.risk, RiskLevel.A)
        self.assertEqual(tool.spec.parameters["type"], "object")
        self.assertEqual(tool.spec.parameters.get("additionalProperties"), False)
        self.assertIn("batteria", tool.spec.description.lower())
        self.assertTrue(tool.spec.reason)

    def test_tool_is_in_the_catalog(self) -> None:
        names = [item["name"] for item in self.registry.catalog()]
        self.assertIn("system.battery", names)

    def test_tool_reads_the_real_battery(self) -> None:
        data = battery_status()
        self.assertIn("presente", data)
        self.assertIn("percentuale", data)
        if data["presente"]:
            self.assertIsInstance(data["percentuale"], int)
            self.assertGreaterEqual(data["percentuale"], 0)
            self.assertLessEqual(data["percentuale"], 100)


class OfflineBatteryIntentTests(unittest.TestCase):
    def _tool_for(self, text: str) -> str:
        import json

        raw = OfflineProvider().chat([{"role": "user", "content": text}])
        return json.loads(raw)["action"]["tool"]

    def test_mac_battery_is_not_the_robot(self) -> None:
        self.assertEqual(self._tool_for("quanto è carica la batteria del Mac?"), "system.battery")
        self.assertEqual(self._tool_for("batteria del portatile"), "system.battery")

    def test_robot_battery_stays_on_the_robot(self) -> None:
        self.assertEqual(self._tool_for("batteria del robot"), "robot.status")
        self.assertEqual(self._tool_for("stato del robot"), "robot.status")


if __name__ == "__main__":
    unittest.main()
