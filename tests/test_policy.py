"""Test della policy di autorizzazione e del confinamento dei percorsi."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from amy.core.errors import PermissionDeniedError
from amy.security.policy import PathGuard, PolicyEngine
from amy.security.risk import RiskLevel
from tests.helpers import TempAmy


class PolicyTests(unittest.TestCase):
    def test_a_is_auto_approved(self) -> None:
        decision = PolicyEngine(auto_approve_levels=["A"]).evaluate(
            "time.now", RiskLevel.A, reason="orologio"
        )
        self.assertFalse(decision.requires_confirmation)
        self.assertTrue(decision.auto_approved)

    def test_b_requires_confirmation_by_default(self) -> None:
        decision = PolicyEngine(auto_approve_levels=["A"]).evaluate(
            "files.write", RiskLevel.B, reason="scrittura"
        )
        self.assertTrue(decision.requires_confirmation)

    def test_b_can_be_auto_approved_only_by_name(self) -> None:
        engine = PolicyEngine(auto_approve_levels=["A"], auto_approve_tools=["files.write"])
        self.assertFalse(engine.evaluate("files.write", RiskLevel.B, reason="x").requires_confirmation)
        self.assertTrue(engine.evaluate("files.move", RiskLevel.B, reason="x").requires_confirmation)

    def test_c_is_never_auto_approved(self) -> None:
        engine = PolicyEngine(
            auto_approve_levels=["A", "B", "C"],
            auto_approve_tools=["robot.move", "files.trash"],
        )
        for tool in ("robot.move", "files.trash", "robot.reset_estop"):
            decision = engine.evaluate(tool, RiskLevel.C, reason="sensibile")
            self.assertTrue(decision.requires_confirmation, tool)
            self.assertFalse(decision.auto_approved, tool)

    def test_confirmation_carries_context(self) -> None:
        decision = PolicyEngine().evaluate(
            "files.write",
            RiskLevel.B,
            reason="motivo",
            consequences="conseguenza",
            undo="annullamento",
        )
        self.assertEqual(decision.reason, "motivo")
        self.assertEqual(decision.consequences, "conseguenza")
        self.assertEqual(decision.undo, "annullamento")


class PathGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.guard = PathGuard([self.temp.files], max_file_bytes=16)

    def tearDown(self) -> None:
        self.temp.close()

    def test_inside_root(self) -> None:
        inside = self.temp.files / "nota.txt"
        inside.write_text("ciao", encoding="utf-8")
        self.assertEqual(self.guard.resolve(str(inside), must_exist=True), inside.resolve())

    def test_relative_path_is_resolved_inside_cwd(self) -> None:
        # Il percorso relativo viene ancorato alla cwd: è accettato solo se
        # ricade in una radice autorizzata.
        previous = os.getcwd()
        try:
            os.chdir(self.temp.files)
            resolved = self.guard.resolve("nota.txt")
        finally:
            os.chdir(previous)
        self.assertEqual(resolved, (self.temp.files / "nota.txt").resolve())

    def test_outside_root_is_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.guard.resolve(str(self.temp.home / "config.json"))

    def test_sensitive_paths_are_denied(self) -> None:
        ssh = self.temp.files / ".ssh"
        ssh.mkdir()
        with self.assertRaises(PermissionDeniedError):
            self.guard.resolve(str(ssh / "id_rsa"))
        env = self.temp.files / ".env"
        env.write_text("TOKEN=segreto", encoding="utf-8")
        with self.assertRaises(PermissionDeniedError):
            self.guard.resolve(str(env), must_exist=True)

    def test_symlink_escape_is_denied(self) -> None:
        outside = self.temp.home / "segreto.txt"
        outside.write_text("x", encoding="utf-8")
        link = self.temp.files / "link.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink non disponibili")
        with self.assertRaises(PermissionDeniedError):
            self.guard.resolve(str(link), must_exist=True)

    def test_size_limit(self) -> None:
        self.guard.check_size(16)
        with self.assertRaises(PermissionDeniedError):
            self.guard.check_size(17)

    def test_missing_path_when_required(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.guard.resolve(str(self.temp.files / "manca.txt"), must_exist=True)


if __name__ == "__main__":
    unittest.main()
