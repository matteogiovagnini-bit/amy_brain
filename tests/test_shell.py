"""Test della shell controllata: solo comandi chiusi e sola lettura."""

from __future__ import annotations

import unittest

from amy.core.errors import PermissionDeniedError, ToolValidationError
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy


class ShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.registry = build_default_registry()
        self.context = ToolContext(
            config=self.temp.config,
            memory=None,
            path_guard=PathGuard([self.temp.files]),
            audit=NullAudit(),
        )

    def tearDown(self) -> None:
        self.temp.close()

    def test_allowed_read_only_command(self) -> None:
        result = self.registry.execute("shell.run", {"command": "date"}, self.context)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["command"], "date")
        self.assertTrue(result.data["stdout"].strip())

    def test_list_directory(self) -> None:
        (self.temp.files / "file.txt").write_text("x", encoding="utf-8")
        result = self.registry.execute(
            "shell.run",
            {"command": "list_directory", "path": str(self.temp.files)},
            self.context,
        )
        self.assertTrue(result.ok)
        self.assertIn("file.txt", result.data["stdout"])

    def test_arbitrary_command_is_rejected_by_schema(self) -> None:
        with self.assertRaises(ToolValidationError):
            self.registry.execute("shell.run", {"command": "rm -rf /"}, self.context)
        with self.assertRaises(ToolValidationError):
            self.registry.execute("shell.run", {"command": "date; whoami"}, self.context)

    def test_git_requires_repository_path(self) -> None:
        with self.assertRaises(ToolValidationError):
            self.registry.execute("shell.run", {"command": "git_status"}, self.context)

    def test_path_outside_roots_is_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.registry.execute(
                "shell.run",
                {"command": "list_directory", "path": str(self.temp.home)},
                self.context,
            )


if __name__ == "__main__":
    unittest.main()
