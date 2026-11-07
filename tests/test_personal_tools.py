"""Test degli strumenti per attività e note personali."""

from __future__ import annotations

import unittest

from amy.memory.store import MemoryStore
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from amy.tools import tasks_tools, notes_tools
from tests.helpers import TempAmy


class PersonalToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "personal.db"))
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

    def test_task_lifecycle(self) -> None:
        created = self.registry.execute(
            "tasks.create",
            {"title": "Controllare il Raspberry", "priority": "alta", "due_at": "2026-11-10"},
            self.context,
        )
        self.assertTrue(created.ok)
        task_id = created.data["id"]
        listed = self.registry.execute("tasks.list", {}, self.context)
        self.assertEqual(listed.data["tasks"][0]["title"], "Controllare il Raspberry")
        updated = self.registry.execute(
            "tasks.update", {"id": task_id, "priority": "bassa"}, self.context
        )
        self.assertTrue(updated.data["updated"])
        completed = self.registry.execute("tasks.complete", {"id": task_id}, self.context)
        self.assertTrue(completed.data["completed"])
        self.assertEqual(self.memory.list_tasks()[0]["status"], "completata")
        deleted = self.registry.execute("tasks.delete", {"id": task_id}, self.context)
        self.assertTrue(deleted.data["removed"])
        self.assertEqual(self.memory.list_tasks(), [])

    def test_task_invalid_due_date_is_reported(self) -> None:
        result = self.registry.execute(
            "tasks.create", {"title": "X", "due_at": "domani"}, self.context
        )
        self.assertFalse(result.ok)

    def test_note_lifecycle(self) -> None:
        created = self.registry.execute(
            "notes.create", {"body": "Comprare cavo USB", "title": "Spesa", "tags": "casa"}, self.context
        )
        self.assertTrue(created.ok)
        note_id = created.data["id"]
        listed = self.registry.execute("notes.list", {}, self.context)
        self.assertEqual(listed.data["notes"][0]["body"], "Comprare cavo USB")
        updated = self.registry.execute(
            "notes.update", {"id": note_id, "body": "Comprare due cavi USB"}, self.context
        )
        self.assertTrue(updated.data["updated"])
        deleted = self.registry.execute("notes.delete", {"id": note_id}, self.context)
        self.assertTrue(deleted.data["removed"])
        self.assertEqual(self.memory.list_notes(), [])

    def test_risk_levels(self) -> None:
        self.assertEqual(tasks_tools.TASKS_CREATE.risk, RiskLevel.B)
        self.assertEqual(tasks_tools.TASKS_DELETE.risk, RiskLevel.C)
        self.assertEqual(tasks_tools.TASKS_LIST.risk, RiskLevel.A)
        self.assertEqual(notes_tools.NOTES_CREATE.risk, RiskLevel.B)
        self.assertEqual(notes_tools.NOTES_DELETE.risk, RiskLevel.C)
        self.assertEqual(notes_tools.NOTES_LIST.risk, RiskLevel.A)

    def test_tool_count_includes_personal_tools(self) -> None:
        self.assertEqual(len(self.registry.names()), 70)


if __name__ == "__main__":
    unittest.main()
