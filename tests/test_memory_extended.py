"""Test della memoria estesa: categorie, ricerca, scadenza e strumenti."""

from __future__ import annotations

import unittest

from amy.memory.store import MemoryStore
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy


class MemoryStoreExtendedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "memoria.db"))

    def tearDown(self) -> None:
        self.memory.close()
        self.temp.close()

    def test_categories_and_search(self) -> None:
        self.memory.set_memory("project", "amy_brain", "Cervello L2 di Amy", verified=True, tags="python,mac")
        self.memory.set_memory("project", "robot", "Raspberry Pi 4 e ESP32-S3")
        self.memory.set_memory("personal", "città", "Roma", verified=True)
        categories = {item["category"]: item["count"] for item in self.memory.memory_categories()}
        self.assertEqual(categories["project"], 2)
        self.assertEqual(categories["personal"], 1)
        found = self.memory.search_memories("ESP32", category="project")
        self.assertEqual(found[0]["key"], "robot")
        self.assertTrue(found[0]["verified"] in (0, 1))

    def test_update_and_delete(self) -> None:
        self.memory.set_memory("project", "amy_brain", "bozza", confidence=0.4)
        self.assertTrue(self.memory.update_memory("project", "amy_brain", value="definitivo", verified=True))
        item = self.memory.get_memory("project", "amy_brain")
        self.assertEqual(item["value"], "definitivo")
        self.assertEqual(item["verified"], 1)
        self.assertTrue(self.memory.delete_memory("project", "amy_brain"))
        self.assertIsNone(self.memory.get_memory("project", "amy_brain"))

    def test_expired_items_are_hidden_unless_requested(self) -> None:
        self.memory.set_memory("operational", "vecchio", "x", expires_at="2000-01-01T00:00:00Z")
        self.assertEqual(self.memory.list_memories(category="operational"), [])
        self.assertEqual(len(self.memory.list_memories(category="operational", include_expired=True)), 1)

    def test_set_fact_mirrors_into_memory_items(self) -> None:
        self.memory.set_fact("città", "Roma")
        item = self.memory.get_memory("personal", "città")
        self.assertIsNotNone(item)
        self.assertEqual(item["value"], "Roma")
        self.assertEqual(item["verified"], 1)
        self.memory.delete_fact("città")
        self.assertIsNone(self.memory.get_memory("personal", "città"))

    def test_migration_from_old_facts_table(self) -> None:
        self.memory.set_fact("vecchio", "valore")
        with self.memory._lock:
            self.memory._conn.execute("DELETE FROM memory_items")
            self.memory._conn.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
            self.memory._conn.commit()
        # Riapre lo stesso database: la migrazione deve ricopiare il fatto.
        self.memory.close()
        reopened = MemoryStore(str(self.temp.home / "memoria.db"))
        try:
            item = reopened.get_memory("personal", "vecchio")
            self.assertIsNotNone(item)
            self.assertEqual(item["value"], "valore")
        finally:
            reopened.close()
            self.memory = MemoryStore(str(self.temp.home / "memoria.db"))

    def test_stats_include_memory_items(self) -> None:
        self.memory.set_memory("project", "a", "b")
        stats = self.memory.stats()
        self.assertIn("memory_items", stats)
        self.assertIn("memory_categories", stats)
        exported = self.memory.export_all()
        self.assertTrue(any(item["key"] == "a" for item in exported["memory_items"]))


class MemoryToolExtendedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "tool.db"))
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

    def test_remember_search_update_and_categories(self) -> None:
        result = self.registry.execute(
            "memory.remember",
            {"key": "amy_brain", "value": "Cervello L2", "category": "project", "tags": "mac"},
            self.context,
        )
        self.assertTrue(result.ok)
        self.assertEqual(self.memory.get_memory("project", "amy_brain")["value"], "Cervello L2")

        found = self.registry.execute("memory.search", {"query": "L2"}, self.context)
        self.assertTrue(found.ok)
        self.assertEqual(found.data["count"], 1)

        updated = self.registry.execute(
            "memory.update",
            {"category": "project", "key": "amy_brain", "verified": True, "confidence": 0.9},
            self.context,
        )
        self.assertTrue(updated.ok)
        self.assertTrue(updated.data["updated"])

        categories = self.registry.execute("memory.categories", {}, self.context)
        self.assertTrue(categories.ok)
        self.assertIn("project", [item["category"] for item in categories.data["categorie"]])

    def test_forget_with_category(self) -> None:
        self.memory.set_memory("project", "x", "y")
        result = self.registry.execute("memory.forget", {"key": "x", "category": "project"}, self.context)
        self.assertTrue(result.ok)
        self.assertTrue(result.data["removed"])
        self.assertIsNone(self.memory.get_memory("project", "x"))

    def test_new_tools_are_level_a(self) -> None:
        self.assertEqual(self.registry.get("memory.search").spec.risk.value, "A")
        self.assertEqual(self.registry.get("memory.update").spec.risk.value, "A")
        self.assertEqual(self.registry.get("memory.categories").spec.risk.value, "A")


if __name__ == "__main__":
    unittest.main()
