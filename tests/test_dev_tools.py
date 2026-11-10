"""Test del Developer Assistant nativo (Fase 8).

Usa un repository Git temporaneo dentro le radici autorizzate. Nessun comando
arbitrario: gli strumenti leggono lo stato, il diff e i file del progetto e
avviano solo la suite unittest.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from amy.memory.store import MemoryStore
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools import dev_tools
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy

GIT = shutil.which("git")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [GIT, *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(GIT, "Git non disponibile")
class DevToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.repo = self.temp.files / "progetto"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "amy@example.invalid")
        _git(self.repo, "config", "user.name", "Amy Test")
        (self.repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (self.repo / "modulo.py").write_text(
            "# TODO: completare il modulo\n\ndef saluta(name):\n    return 'ciao ' + name\n",
            encoding="utf-8",
        )
        tests = self.repo / "tests"
        tests.mkdir()
        (tests / "test_ok.py").write_text(
            "import unittest\n\nclass OkTest(unittest.TestCase):\n"
            "    def test_ok(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "primo commit")

        self.memory = MemoryStore(str(self.temp.home / "dev.db"))
        self.registry = build_default_registry()
        self.context = ToolContext(
            config=self.temp.config,
            memory=self.memory,
            path_guard=PathGuard([self.temp.files], max_file_bytes=1024 * 1024),
            audit=NullAudit(),
        )
        self.temp.config.data["dev"]["project_dir"] = str(self.repo)

    def tearDown(self) -> None:
        self.memory.close()
        self.temp.close()

    def test_status_on_clean_repository(self) -> None:
        result = self.registry.execute("dev.status", {}, self.context)
        self.assertTrue(result.ok)
        self.assertTrue(result.data["clean"])
        self.assertEqual(result.data["modified"], 0)
        self.assertEqual(result.data["untracked"], 0)
        self.assertTrue(result.data["last_commit"]["hash"])
        self.assertTrue(result.data["dependencies"]["pyproject.toml"])

    def test_status_reports_changes(self) -> None:
        (self.repo / "modulo.py").write_text("# cambiato\n", encoding="utf-8")
        (self.repo / "nuovo.txt").write_text("nuovo\n", encoding="utf-8")
        result = self.registry.execute("dev.status", {}, self.context)
        self.assertTrue(result.ok)
        self.assertFalse(result.data["clean"])
        self.assertEqual(result.data["modified"], 1)
        self.assertEqual(result.data["untracked"], 1)

    def test_diff_reads_changes(self) -> None:
        (self.repo / "modulo.py").write_text("# cambiato\n", encoding="utf-8")
        result = self.registry.execute("dev.diff", {"stat_only": True}, self.context)
        self.assertTrue(result.ok)
        self.assertIn("modulo.py", result.data["stat"])
        self.assertEqual(result.data["diff"], "")

    def test_diff_path_cannot_escape_project(self) -> None:
        result = self.registry.execute("dev.diff", {"path": "../segreto"}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "dev_error")

    def test_analyze_finds_todos_and_syntax_errors(self) -> None:
        (self.repo / "rotto.py").write_text("def x(:\n", encoding="utf-8")
        result = self.registry.execute(
            "dev.analyze", {"path": ".", "limit": 100}, self.context
        )
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.data["files"], 3)
        self.assertTrue(any(item["kind"] == "TODO" for item in result.data["todos"]))
        self.assertTrue(
            any(item["path"] == "rotto.py" for item in result.data["syntax_errors"])
        )

    def test_analyze_rejects_outside_path(self) -> None:
        result = self.registry.execute("dev.analyze", {"path": "/etc"}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "dev_error")

    def test_suite_passes(self) -> None:
        result = self.registry.execute("dev.test", {}, self.context)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["tests"], 1)
        self.assertFalse(result.data["timed_out"])

    def test_suite_failure_is_reported(self) -> None:
        (self.repo / "tests" / "test_bad.py").write_text(
            "import unittest\n\nclass BadTest(unittest.TestCase):\n"
            "    def test_bad(self):\n        self.assertTrue(False)\n",
            encoding="utf-8",
        )
        result = self.registry.execute("dev.test", {}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "tests_failed")
        self.assertEqual(result.data["tests"], 2)

    def test_risk_levels(self) -> None:
        self.assertEqual(dev_tools.DEV_STATUS.risk, RiskLevel.A)
        self.assertEqual(dev_tools.DEV_DIFF.risk, RiskLevel.A)
        self.assertEqual(dev_tools.DEV_ANALYZE.risk, RiskLevel.A)
        self.assertEqual(dev_tools.DEV_TEST.risk, RiskLevel.B)

    def test_tool_count_includes_developer_tools(self) -> None:
        self.assertEqual(len(self.registry.names()), 80)


if __name__ == "__main__":
    unittest.main()
