"""Test dell'orchestratore: validazione, conferme A/B/C e flusso del turno."""

from __future__ import annotations

import json
import unittest

from amy.ai.base import AIProvider
from amy.core.assistant import Assistant
from amy.memory.store import MemoryStore
from amy.robot.links import SimulatedLink
from amy.robot.simulator import RobotSimulator
from amy.security.audit import NullAudit
from tests.helpers import TempAmy


class ScriptedProvider(AIProvider):
    name = "scripted"
    model = "test"

    def __init__(self, replies) -> None:
        self.replies = list(replies)
        self.calls = []
        self.last_fallback_reason = ""

    def chat(self, messages, *, temperature=None, max_tokens=None) -> str:
        self.calls.append(messages)
        if self.replies:
            return self.replies.pop(0)
        return "Fatto."

    def status(self):
        return {"provider": self.name, "model": self.model, "available": True}


class FakeVoice:
    def status(self):
        return {
            "enabled": False,
            "tts": {"available": False, "engine": "none"},
            "stt": {"available": False, "engine": "none"},
            "recorder": {"available": False, "engine": "none"},
            "ready_for_voice_commands": False,
        }

    def speak(self, text, *, block=False):
        return {"spoken": False, "reason": "test"}

    def stop_speaking(self):
        return None


def action(tool: str, args=None) -> str:
    return json.dumps({"say": "Eseguo.", "action": {"tool": tool, "args": args or {}}}, ensure_ascii=False)


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.provider = ScriptedProvider([])
        self.memory = MemoryStore(str(self.temp.home / "orchestrator.db"))
        self.simulator = RobotSimulator()
        self.assistant = Assistant(
            self.temp.config,
            provider=self.provider,
            memory=self.memory,
            audit=NullAudit(),
            robot_link=SimulatedLink(self.simulator),
            voice=FakeVoice(),
        )

    def tearDown(self) -> None:
        self.assistant.close()
        self.temp.close()

    def test_level_a_action_executes_without_confirmation(self) -> None:
        self.provider.replies = [action("time.now"), "Sono le dodici."]
        result = self.assistant.handle("che ore sono?")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reply, "Sono le dodici.")
        self.assertEqual(result.tools_used, ["time.now"])
        self.assertIsNone(result.pending)
        self.assertIn("time.now", [item["tool"] for item in self.memory.list_activities()])

    def test_level_b_requires_confirmation_then_executes(self) -> None:
        target = self.temp.files / "nota.txt"
        self.provider.replies = [
            action("files.write", {"path": str(target), "content": "contenuto"}),
            "File scritto.",
        ]
        result = self.assistant.handle("scrivi una nota")
        self.assertEqual(result.status, "confirmation_required")
        self.assertIsNotNone(result.pending)
        self.assertEqual(result.pending.tool, "files.write")
        self.assertEqual(result.pending.risk.value, "B")
        self.assertFalse(target.exists())
        self.assertEqual(len(self.assistant.pending_confirmations()), 1)

        resolved = self.assistant.resolve_confirmation(result.pending.pending_id, True)
        self.assertEqual(resolved.status, "ok")
        self.assertEqual(resolved.reply, "File scritto.")
        self.assertEqual(target.read_text(encoding="utf-8"), "contenuto")
        self.assertEqual(self.assistant.pending_confirmations(), [])
        statuses = [item["status"] for item in self.memory.list_activities()]
        self.assertIn("ok", statuses)

    def test_denied_confirmation_does_not_execute(self) -> None:
        target = self.temp.files / "negato.txt"
        self.provider.replies = [
            action("files.write", {"path": str(target), "content": "x"}),
            "Operazione annullata.",
        ]
        result = self.assistant.handle("scrivi")
        resolved = self.assistant.resolve_confirmation(result.pending.pending_id, False)
        self.assertFalse(target.exists())
        self.assertEqual(resolved.reply, "Operazione annullata.")
        statuses = [item["status"] for item in self.memory.list_activities()]
        self.assertIn("rifiutato", statuses)

    def test_level_c_never_auto_approved_even_if_configured(self) -> None:
        self.temp.config.data["security"]["auto_approve_levels"] = ["A", "B", "C"]
        self.temp.config.data["security"]["auto_approve_tools"] = ["robot.move"]
        other_memory = MemoryStore(str(self.temp.home / "orchestrator-c.db"))
        assistant = Assistant(
            self.temp.config,
            provider=self.provider,
            memory=other_memory,
            audit=NullAudit(),
            robot_link=SimulatedLink(self.simulator),
            voice=FakeVoice(),
        )
        try:
            self.provider.replies = [
                action(
                    "robot.move",
                    {"joints": [{"joint": "head_pan", "position_deg": 5}], "deadline_ms": 3000, "head": True},
                ),
                "Movimento completato.",
            ]
            result = assistant.handle("muovi la testa")
            self.assertEqual(result.status, "confirmation_required")
            self.assertEqual(result.pending.risk.value, "C")
            resolved = assistant.resolve_confirmation(result.pending.pending_id, True)
            self.assertEqual(resolved.status, "ok")
            self.assertTrue(self.simulator.status()["simulated"])
        finally:
            assistant.close()

    def test_estop_is_never_blocked(self) -> None:
        self.provider.replies = [action("robot.estop", {"reason": "test"}), "E-stop attivato."]
        result = self.assistant.handle("emergenza")
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.pending)
        self.assertTrue(self.simulator.status()["estop_latched"])

    def test_malformed_action_is_not_executed(self) -> None:
        self.provider.replies = ['{"say":"x","action":{"tool":"time.now","args":[]}}']
        result = self.assistant.handle("x")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "invalid_action")
        self.assertEqual(self.memory.list_activities(), [])

    def test_unknown_tool_becomes_tool_result(self) -> None:
        self.provider.replies = [action("strumento.inesistente"), "Non è disponibile."]
        result = self.assistant.handle("prova")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.tools_used, ["strumento.inesistente"])
        activity = self.memory.list_activities()[0]
        self.assertEqual(activity["tool"], "strumento.inesistente")
        self.assertEqual(activity["result"]["error_code"], "tool_not_found")

    def test_invalid_arguments_are_rejected_before_execution(self) -> None:
        self.provider.replies = [action("files.read", {}), "Manca il percorso."]
        result = self.assistant.handle("leggi")
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.pending)
        activity = self.memory.list_activities()[0]
        self.assertEqual(activity["status"], "errore")
        self.assertEqual(activity["result"]["error_code"], "tool_validation")

    def test_tool_step_limit(self) -> None:
        self.temp.config.data["ai"]["max_tool_steps"] = 1
        self.provider.replies = [action("time.now")]
        result = self.assistant.handle("ripeti")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "tool_step_limit")

    def test_confirmation_ttl(self) -> None:
        self.temp.config.data["security"]["confirmation_ttl_s"] = -1.0
        target = self.temp.files / "scaduta.txt"
        self.provider.replies = [action("files.write", {"path": str(target), "content": "x"}), "ok"]
        result = self.assistant.handle("scrivi")
        resolved = self.assistant.resolve_confirmation(result.pending.pending_id, True)
        self.assertEqual(resolved.status, "error")
        self.assertEqual(resolved.error_code, "pending_expired")
        self.assertFalse(target.exists())

    def test_unknown_pending_id(self) -> None:
        result = self.assistant.resolve_confirmation("cfm_inesistente", True)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "pending_not_found")

    def test_status_includes_recent_facts(self) -> None:
        self.memory.set_fact("città", "Roma")
        status = self.assistant.status()
        self.assertEqual(status["facts"][0]["key"], "città")
        self.assertIn("config_path", status["config"])
        self.assertIn("provider", status)
        self.assertIn("system", status)
        self.assertIn("robot", status)
        self.assertIn("voice", status)

    def test_history_is_persisted_without_tool_json(self) -> None:
        self.provider.replies = [action("time.now"), "Sono le nove."]
        result = self.assistant.handle("che ore sono?")
        history = self.memory.history(result.session_id, 10)
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertEqual(history[0]["content"], "che ore sono?")
        self.assertEqual(history[1]["content"], "Sono le nove.")
        self.assertNotIn('"tool"', history[0]["content"])


if __name__ == "__main__":
    unittest.main()
