"""Test di screenshot e OCR, senza catturare davvero lo schermo."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from amy.macos import screen
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools import screen_tools
from amy.tools.base import ToolContext
from tests.helpers import TempAmy


class ScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()

    def tearDown(self) -> None:
        self.temp.close()

    def test_capture_writes_a_png(self) -> None:
        target = self.temp.files / "shot.png"

        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"x" * 2000)
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch("amy.macos.screen.subprocess.run", side_effect=fake_run):
            path = screen.capture(target)
        self.assertEqual(path, target)
        self.assertGreater(path.stat().st_size, 1000)

    def test_empty_capture_is_refused(self) -> None:
        target = self.temp.files / "vuoto.png"
        with mock.patch(
            "amy.macos.screen.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            with self.assertRaises(screen.ScreenError):
                screen.capture(target)

    def test_ocr_returns_text_and_truncates(self) -> None:
        image = self.temp.files / "img.png"
        image.write_bytes(b"x" * 2000)
        with mock.patch("amy.macos.screen._ocr_binary", return_value=Path("/bin/echo")):
            with mock.patch(
                "amy.macos.screen.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "testo " * 500, ""),
            ):
                text = screen.ocr_image(image, max_chars=500)
        self.assertEqual(len(text), 500)

    def test_read_screen_uses_an_existing_image(self) -> None:
        image = self.temp.files / "img.png"
        image.write_bytes(b"x" * 2000)
        with mock.patch("amy.macos.screen.ocr_image", return_value="Ciao"):
            data = screen.read_screen(image_path=image)
        self.assertFalse(data["captured"])
        self.assertEqual(data["text"], "Ciao")


class ScreenToolTests(unittest.TestCase):
    def test_both_tools_require_confirmation(self) -> None:
        self.assertEqual(screen_tools.SCREEN_CAPTURE.risk, RiskLevel.B)
        self.assertEqual(screen_tools.SCREEN_READ.risk, RiskLevel.B)

    def test_image_path_outside_roots_is_refused(self) -> None:
        temp = TempAmy()
        try:
            guard = PathGuard([temp.files], max_file_bytes=1024)
            context = ToolContext(
                config=temp.config, memory=None, path_guard=guard, audit=NullAudit()
            )
            with self.assertRaises(Exception):
                screen_tools._read({"image_path": "/etc/hosts"}, context)
        finally:
            temp.close()


if __name__ == "__main__":
    unittest.main()
