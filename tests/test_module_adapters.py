"""Test degli adapter dei moduli (Fase 2).

Gli adapter devono esporre gli stessi 57 strumenti del registry esistente,
senza modificare `builtin.py` né il comportamento dell'assistente.
"""

from __future__ import annotations

import unittest
from unittest import mock

from amy.modules import build_module_registry
from amy.modules.registry import DEFAULT_MODULES
from amy.shared.module import ModuleContext, ModuleState
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy


class ModuleAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()

    def tearDown(self) -> None:
        self.temp.close()

    def _all_enabled(self):
        return build_module_registry(
            self.temp.config,
            enabled={name: True for name in DEFAULT_MODULES},
        )

    def test_eight_modules_are_registered(self) -> None:
        registry = build_module_registry(self.temp.config)
        self.assertEqual(registry.names(), sorted(DEFAULT_MODULES))

    def test_default_enabled_flags(self) -> None:
        registry = build_module_registry(self.temp.config)
        self.assertTrue(registry.enabled("voice"))
        self.assertTrue(registry.enabled("mac_control"))
        self.assertTrue(registry.enabled("personal"))
        self.assertTrue(registry.enabled("memory"))
        self.assertTrue(registry.enabled("vision"))
        self.assertTrue(registry.enabled("robot"))
        self.assertFalse(registry.enabled("developer"))
        self.assertFalse(registry.enabled("home"))

    def test_tool_union_matches_the_existing_registry(self) -> None:
        registry = self._all_enabled()
        context = ModuleContext(config=self.temp.config, events=None)
        registry.start_all(context)
        module_tools = sorted(tool.spec.name for tool in registry.tools())
        builtin_tools = sorted(build_default_registry().names())
        self.assertEqual(module_tools, builtin_tools)
        self.assertEqual(len(module_tools), 70)

    def test_disabling_a_module_removes_its_tools(self) -> None:
        registry = self._all_enabled()
        context = ModuleContext(config=self.temp.config, events=None)
        registry.start_all(context)
        self.assertIn("screen.read", [tool.spec.name for tool in registry.tools()])
        registry.disable("vision")
        self.assertNotIn("screen.read", [tool.spec.name for tool in registry.tools()])

    def test_manifests_declare_capabilities(self) -> None:
        registry = build_module_registry(self.temp.config)
        modules = {item["manifest"]["name"]: item for item in registry.statuses()}
        self.assertIn("voice.wake", modules["voice"]["manifest"]["capabilities"])
        self.assertIn("personal.calendar", modules["personal"]["manifest"]["capabilities"])
        self.assertIn("robot.estop", modules["robot"]["manifest"]["capabilities"])
        self.assertIn("home.set", modules["home"]["manifest"]["capabilities"])

    def test_status_states_are_valid(self) -> None:
        registry = self._all_enabled()
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        allowed = {state.value for state in ModuleState}
        for item in registry.statuses():
            self.assertIn(item["status"]["state"], allowed)

    def test_developer_is_degraded_when_opencode_is_disabled(self) -> None:
        registry = build_module_registry(
            self.temp.config,
            enabled={"developer": True},
        )
        self.temp.config.data["opencode"]["enabled"] = False
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        status = registry.status_of("developer")
        self.assertEqual(status.state, ModuleState.DEGRADED)
        self.assertFalse(status.available)

    def test_developer_is_offline_when_binary_is_missing(self) -> None:
        registry = build_module_registry(
            self.temp.config,
            enabled={"developer": True},
        )
        self.temp.config.data["opencode"]["enabled"] = True
        self.temp.config.data["opencode"]["binary"] = "definitely-not-installed"
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        status = registry.status_of("developer")
        self.assertEqual(status.state, ModuleState.OFFLINE)

    def test_robot_without_link_is_degraded(self) -> None:
        registry = build_module_registry(
            self.temp.config,
            enabled={"robot": True},
        )
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        status = registry.status_of("robot")
        self.assertEqual(status.state, ModuleState.DEGRADED)
        self.assertFalse(status.available)

    def test_robot_with_a_link_reports_ready(self) -> None:
        class FakeLink:
            def status(self):
                return {"mode": "TEST", "estop_latched": False}

        registry = build_module_registry(
            self.temp.config,
            enabled={"robot": True},
            robot_link=FakeLink(),
        )
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        status = registry.status_of("robot")
        self.assertEqual(status.state, ModuleState.READY)
        self.assertTrue(status.available)


if __name__ == "__main__":
    unittest.main()
