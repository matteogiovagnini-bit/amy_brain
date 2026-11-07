"""Test delle autorizzazioni per modulo e capacità."""

from __future__ import annotations

import unittest

from amy.modules import build_module_registry
from amy.modules.registry import DEFAULT_MODULES
from amy.security.authorization import AuthorizationBroker, AuthorizationError, capability_for_tool
from amy.security.policy import PolicyEngine
from amy.security.risk import RiskLevel
from amy.shared.module import ModuleContext
from tests.helpers import TempAmy


class AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.registry = build_module_registry(
            self.temp.config,
            enabled={name: True for name in DEFAULT_MODULES},
        )
        self.registry.start_all(ModuleContext(config=self.temp.config, events=None))
        self.broker = AuthorizationBroker(self.registry)

    def tearDown(self) -> None:
        self.temp.close()

    def test_tool_is_mapped_to_module_and_capability(self) -> None:
        decision = self.broker.check("time.now")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.module, "mac_control")
        self.assertEqual(decision.capability, "mac.system")

    def test_capability_mapping(self) -> None:
        self.assertEqual(capability_for_tool("files.write"), "mac.file")
        self.assertEqual(capability_for_tool("mail.send"), "personal.mail")
        self.assertEqual(capability_for_tool("opencode.run"), "dev.execute")
        self.assertEqual(capability_for_tool("app.restart"), "dev.restart")
        self.assertEqual(capability_for_tool("screen.read"), "vision.screen")
        self.assertEqual(capability_for_tool("robot.move"), "robot.move")
        self.assertEqual(capability_for_tool("robot.estop"), "robot.estop")
        self.assertEqual(capability_for_tool("voice.speak"), "voice.tts")
        self.assertEqual(capability_for_tool("sconosciuto"), "")

    def test_revoked_capability_blocks_the_tool(self) -> None:
        self.broker.revoke("mac.system")
        decision = self.broker.check("time.now")
        self.assertFalse(decision.allowed)
        self.assertIn("revocata", decision.reason)
        self.broker.restore("mac.system")
        self.assertTrue(self.broker.check("time.now").allowed)

    def test_unknown_capability_is_refused(self) -> None:
        with self.assertRaises(AuthorizationError):
            self.broker.revoke("inesistente")

    def test_disabled_module_blocks_its_tools(self) -> None:
        self.registry.disable("vision")
        decision = self.broker.check("screen.read")
        self.assertFalse(decision.allowed)
        self.assertIn("disabilitato", decision.reason)

    def test_revocation_does_not_change_level_c_policy(self) -> None:
        # Il broker autorizza il modulo; la policy resta l'unica a decidere la
        # conferma, e il livello C non diventa automatico.
        self.assertTrue(self.broker.check("robot.move", RiskLevel.C).allowed)
        decision = PolicyEngine().evaluate(
            "robot.move",
            RiskLevel.C,
            reason="movimento",
        )
        self.assertTrue(decision.requires_confirmation)

    def test_snapshot_lists_capabilities_and_revocations(self) -> None:
        self.broker.revoke("vision.screen")
        snapshot = self.broker.snapshot()
        self.assertIn("vision.screen", snapshot["revoked"])
        capabilities = {item["capability"] for item in snapshot["capabilities"]}
        self.assertIn("vision.screen", capabilities)
        self.assertIn("mac.system", capabilities)

    def test_app_restart_belongs_to_developer(self) -> None:
        self.assertEqual(self.broker.check("app.restart").module, "developer")
        self.broker.revoke("dev.restart")
        self.assertFalse(self.broker.check("app.restart").allowed)


if __name__ == "__main__":
    unittest.main()
