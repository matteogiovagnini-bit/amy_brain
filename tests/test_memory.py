"""Test della memoria SQLite locale."""

from __future__ import annotations

import unittest

from amy.memory.store import MemoryStore
from tests.helpers import TempAmy


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "memory.db"))

    def tearDown(self) -> None:
        self.memory.close()
        self.temp.close()

    def test_sessions_and_messages(self) -> None:
        session = self.memory.create_session("Prova")
        self.assertTrue(session.startswith("ses_"))
        self.assertEqual(self.memory.get_session(session)["title"], "Prova")
        self.memory.add_message(session, "user", "ciao")
        self.memory.add_message(session, "assistant", "salve")
        self.assertEqual(self.memory.message_count(session), 2)
        history = self.memory.history(session, 10)
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertEqual(self.memory.latest_session()["id"], session)
        self.assertEqual(self.memory.list_sessions(10)[0]["id"], session)
        self.memory.clear_history(session)
        self.assertEqual(self.memory.history(session), [])
        self.assertEqual(self.memory.message_count(session), 0)

    def test_facts_upsert_and_delete(self) -> None:
        self.memory.set_fact("città", "Roma")
        self.memory.set_fact("città", "Milano")
        self.assertEqual(self.memory.get_fact("città")["value"], "Milano")
        self.assertEqual(len(self.memory.list_facts()), 1)
        self.assertTrue(self.memory.delete_fact("città"))
        self.assertFalse(self.memory.delete_fact("città"))
        with self.assertRaises(ValueError):
            self.memory.set_fact("   ", "vuoto")

    def test_activities_and_robot_events(self) -> None:
        session = self.memory.create_session()
        activity = self.memory.start_activity(
            session_id=session,
            tool="time.now",
            args={},
            risk="A",
        )
        self.memory.finish_activity(activity, status="ok", result={"ok": True, "message": "fatto"})
        activities = self.memory.list_activities(10)
        self.assertEqual(activities[0]["tool"], "time.now")
        self.assertEqual(activities[0]["status"], "ok")
        self.assertEqual(activities[0]["result"]["message"], "fatto")

        self.memory.record_robot_event("estop", {"reason": "test"})
        events = self.memory.list_robot_events(10)
        self.assertEqual(events[0]["type"], "estop")
        self.assertEqual(events[0]["payload"]["reason"], "test")

    def test_stats_and_export(self) -> None:
        session = self.memory.create_session()
        self.memory.add_message(session, "user", "x")
        self.memory.set_fact("k", "v")
        self.memory.record_robot_event("stop", {})
        stats = self.memory.stats()
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["messages"], 1)
        self.assertEqual(stats["facts"], 1)
        exported = self.memory.export_all()
        self.assertEqual(exported["stats"]["sessions"], 1)
        self.assertEqual(exported["facts"][0]["key"], "k")

    def test_secrets_are_redacted_before_storage(self) -> None:
        session = self.memory.create_session()
        self.memory.add_message(session, "user", "x", {"api_key": "sk-1234567890"})
        raw = self.memory.history(session)[0]
        self.assertNotIn("sk-1234567890", raw["meta"])
        self.assertIn("[REDATTO]", raw["meta"])


if __name__ == "__main__":
    unittest.main()
