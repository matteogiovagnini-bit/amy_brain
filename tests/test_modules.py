"""Test del contratto dei moduli e del registro."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from amy.core.modules import ModuleError, ModuleRegistry
from amy.shared.events import EventBus
from amy.shared.module import (
    ModuleContext,
    ModuleManifest,
    ModuleState,
    ModuleStatus,
)


def dummy_tool(name: str):
    return SimpleNamespace(spec=SimpleNamespace(name=name))


class FakeModule:
    def __init__(self, name: str, *, default_enabled: bool = True, tools=(), fail: bool = False) -> None:
        self.manifest = ModuleManifest(
            name=name,
            title=name.title(),
            default_enabled=default_enabled,
            tools=[tool.spec.name for tool in tools],
        )
        self._tools = list(tools)
        self._fail = fail
        self.started = 0
        self.stopped = 0
        self.state = ModuleState.DISABLED
        self.last_context = None

    def start(self, context: ModuleContext) -> None:
        if self._fail:
            raise RuntimeError("avvio rotto")
        self.started += 1
        self.last_context = context
        self.state = ModuleState.READY

    def stop(self) -> None:
        self.stopped += 1
        self.state = ModuleState.DISABLED

    def status(self) -> ModuleStatus:
        return ModuleStatus(
            name=self.manifest.name,
            state=self.state,
            available=self.state == ModuleState.READY,
        )

    def tools(self):
        return list(self._tools)


def context() -> ModuleContext:
    return ModuleContext(config=None, events=None)


class ModuleRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus(history_size=50)
        self.registry = ModuleRegistry(events=self.bus)

    def tearDown(self) -> None:
        self.registry.stop_all()
        self.bus.close()

    def test_register_and_start(self) -> None:
        module = FakeModule("voice", tools=[dummy_tool("voice.speak")])
        self.registry.register(module)
        self.assertEqual(self.registry.names(), ["voice"])
        self.assertTrue(self.registry.enabled("voice"))
        status = self.registry.start("voice", context())
        self.assertEqual(status.state, ModuleState.READY)
        self.assertEqual(module.started, 1)
        self.assertEqual(len(self.registry.tools()), 1)

    def test_duplicate_module_is_refused(self) -> None:
        self.registry.register(FakeModule("voice"))
        with self.assertRaises(ModuleError):
            self.registry.register(FakeModule("voice"))

    def test_start_failure_sets_error_and_does_not_stop_others(self) -> None:
        broken = FakeModule("broken", fail=True)
        healthy = FakeModule("healthy")
        self.registry.register(broken)
        self.registry.register(healthy)
        result = self.registry.start_all(context())
        self.assertEqual(result["broken"].state, ModuleState.ERROR)
        self.assertEqual(result["healthy"].state, ModuleState.READY)
        self.assertEqual(healthy.started, 1)

    def test_disabled_module_is_not_started_and_exposes_no_tools(self) -> None:
        module = FakeModule("vision", default_enabled=False, tools=[dummy_tool("screen.read")])
        self.registry.register(module)
        self.registry.start_all(context())
        self.assertEqual(module.started, 0)
        self.assertEqual(self.registry.tools(), [])

    def test_enable_and_disable(self) -> None:
        module = FakeModule("home", default_enabled=False, tools=[dummy_tool("home.devices")])
        self.registry.register(module)
        self.registry.enable("home", context())
        self.assertEqual(module.started, 1)
        self.assertEqual(len(self.registry.tools()), 1)
        self.registry.disable("home")
        self.assertEqual(module.stopped, 1)
        self.assertEqual(self.registry.tools(), [])

    def test_duplicate_tool_is_refused(self) -> None:
        self.registry.register(FakeModule("a", tools=[dummy_tool("shared.tool")]))
        self.registry.register(FakeModule("b", tools=[dummy_tool("shared.tool")]))
        self.registry.start_all(context())
        with self.assertRaises(ModuleError):
            self.registry.tools()

    def test_status_change_publishes_an_event(self) -> None:
        self.registry.register(FakeModule("voice"))
        self.registry.start("voice", context())
        self.assertTrue(self.bus.flush())
        topics = [event["topic"] for event in self.bus.history()]
        self.assertIn("module.status", topics)
        self.assertEqual(self.registry.snapshot()["modules"][0]["status"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
