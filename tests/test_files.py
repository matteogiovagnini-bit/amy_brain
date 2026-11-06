"""Test degli strumenti file: confinamento, backup e cestino recuperabile."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from amy.core.errors import PermissionDeniedError, ToolValidationError
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy


class FileToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.registry = build_default_registry()
        self.guard = PathGuard([self.temp.files], max_file_bytes=1024)
        self.context = ToolContext(
            config=self.temp.config,
            memory=None,
            path_guard=self.guard,
            audit=NullAudit(),
        )

    def tearDown(self) -> None:
        self.temp.close()

    def test_write_read_list_and_search(self) -> None:
        target = self.temp.files / "nota.txt"
        result = self.registry.execute(
            "files.write",
            {"path": str(target), "content": "prima versione"},
            self.context,
        )
        self.assertTrue(result.ok)
        self.assertEqual(target.read_text(encoding="utf-8"), "prima versione")

        read = self.registry.execute("files.read", {"path": str(target)}, self.context)
        self.assertTrue(read.ok)
        self.assertEqual(read.data["content"], "prima versione")

        listing = self.registry.execute("files.list", {"path": str(self.temp.files)}, self.context)
        self.assertTrue(listing.ok)
        self.assertEqual(listing.data["voci"][0]["name"], "nota.txt")

        found = self.registry.execute("files.search", {"query": "nota"}, self.context)
        self.assertTrue(found.ok)
        self.assertEqual(found.data["risultati"][0]["name"], "nota.txt")

    def test_write_creates_backup(self) -> None:
        target = self.temp.files / "nota.txt"
        target.write_text("vecchio", encoding="utf-8")
        result = self.registry.execute(
            "files.write",
            {"path": str(target), "content": "nuovo"},
            self.context,
        )
        self.assertTrue(result.ok)
        backup = result.data["backup"]
        self.assertIsNotNone(backup)
        self.assertEqual(Path(backup).read_text(encoding="utf-8"), "vecchio")
        self.assertEqual(target.read_text(encoding="utf-8"), "nuovo")

    def test_trash_is_recoverable(self) -> None:
        target = self.temp.files / "da-rimuovere.txt"
        target.write_text("contenuto", encoding="utf-8")
        result = self.registry.execute("files.trash", {"path": str(target)}, self.context)
        self.assertTrue(result.ok)
        self.assertFalse(target.exists())
        trashed = Path(result.data["trash"])
        self.assertTrue(trashed.exists())
        self.assertEqual(trashed.read_text(encoding="utf-8"), "contenuto")
        self.assertTrue(result.data["recuperabile"])

    def test_mkdir_and_diff(self) -> None:
        folder = self.temp.files / "nuova"
        created = self.registry.execute("files.mkdir", {"path": str(folder)}, self.context)
        self.assertTrue(created.ok)
        self.assertTrue(folder.is_dir())

        first = self.temp.files / "a.txt"
        second = self.temp.files / "b.txt"
        first.write_text("uno\n", encoding="utf-8")
        second.write_text("due\n", encoding="utf-8")
        diff = self.registry.execute(
            "files.diff",
            {"path_a": str(first), "path_b": str(second)},
            self.context,
        )
        self.assertTrue(diff.ok)
        self.assertFalse(diff.data["identici"])
        self.assertIn("-uno", diff.data["diff"])

    def test_move_risk_depends_on_destination(self) -> None:
        source = self.temp.files / "sorgente.txt"
        source.write_text("x", encoding="utf-8")
        destination = self.temp.files / "destinazione.txt"
        tool = self.registry.get("files.move")
        self.assertEqual(
            tool.risk_for({"source": str(source), "destination": str(destination)}),
            RiskLevel.B,
        )
        destination.write_text("esiste", encoding="utf-8")
        self.assertEqual(
            tool.risk_for({"source": str(source), "destination": str(destination)}),
            RiskLevel.C,
        )

    def test_write_outside_root_is_denied(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.registry.execute(
                "files.write",
                {"path": str(self.temp.home / "fuori.txt"), "content": "x"},
                self.context,
            )

    def test_sensitive_file_is_denied(self) -> None:
        secret = self.temp.files / ".env"
        secret.write_text("TOKEN=x", encoding="utf-8")
        with self.assertRaises(PermissionDeniedError):
            self.registry.execute("files.read", {"path": str(secret)}, self.context)

    def test_size_limit(self) -> None:
        guard = PathGuard([self.temp.files], max_file_bytes=4)
        context = ToolContext(
            config=self.temp.config,
            memory=None,
            path_guard=guard,
            audit=NullAudit(),
        )
        with self.assertRaises(PermissionDeniedError):
            self.registry.execute(
                "files.write",
                {"path": str(self.temp.files / "grande.txt"), "content": "troppo lungo"},
                context,
            )

    def test_directory_cannot_be_read_as_file(self) -> None:
        with self.assertRaises(ToolValidationError):
            self.registry.execute("files.read", {"path": str(self.temp.files)}, self.context)

    def test_open_file_uses_the_system_open_command(self) -> None:
        target = self.temp.files / "documento.txt"
        target.write_text("contenuto", encoding="utf-8")
        with mock.patch("amy.tools.files.subprocess.run") as runner:
            runner.return_value = mock.Mock(returncode=0, stderr="")
            result = self.registry.execute("files.open", {"path": str(target)}, self.context)
        self.assertTrue(result.ok)
        self.assertEqual(runner.call_args[0][0][0], "open")
        self.assertEqual(runner.call_args[0][0][1], str(target.resolve()))

    def test_grep_finds_text_and_skips_binary_files(self) -> None:
        (self.temp.files / "a.txt").write_text("appuntamenti e promemoria\naltro\n", encoding="utf-8")
        (self.temp.files / "b.txt").write_text("nessuna parola\n", encoding="utf-8")
        (self.temp.files / "bin.dat").write_bytes(b"\x00\x01appuntamenti")
        result = self.registry.execute(
            "files.grep", {"query": "appuntamenti", "path": str(self.temp.files)}, self.context
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data["results"]), 1)
        self.assertEqual(result.data["results"][0]["line"], 1)
        self.assertIn("a.txt", result.data["results"][0]["path"])

    def test_new_tools_have_the_expected_risk(self) -> None:
        self.assertEqual(self.registry.get("files.open").spec.risk, RiskLevel.A)
        self.assertEqual(self.registry.get("files.grep").spec.risk, RiskLevel.A)


if __name__ == "__main__":
    unittest.main()
