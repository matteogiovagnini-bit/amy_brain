"""Test della Vision opzionale (Fase 7).

La telecamera è spenta per default e non viene mai aperta nei test: la cattura
reale è sostituita da un mock. La descrizione non è implementata.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from amy.memory.store import MemoryStore
from amy.security.audit import NullAudit
from amy.security.policy import PathGuard
from amy.security.risk import RiskLevel
from amy.tools import screen_tools
from amy.tools.base import ToolContext
from amy.tools.builtin import build_default_registry
from tests.helpers import TempAmy


class VisionCameraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.memory = MemoryStore(str(self.temp.home / "vision.db"))
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

    def test_camera_is_disabled_by_default(self) -> None:
        self.assertFalse(self.temp.config.get("vision.camera", True))
        result = self.registry.execute("vision.capture", {}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "camera_disabled")

    def test_camera_captures_when_enabled(self) -> None:
        self.temp.config.data["vision"]["camera"] = True
        image = self.temp.files / "frame.jpg"
        image.write_bytes(b"\xff\xd8" + b"0" * 2048)
        with mock.patch("amy.tools.screen_tools.capture_camera", return_value=image) as capture:
            result = self.registry.execute("vision.capture", {}, self.context)
        capture.assert_called_once()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["image"], str(image))
        self.assertGreater(result.data["bytes"], 1000)

    def test_camera_errors_are_reported(self) -> None:
        self.temp.config.data["vision"]["camera"] = True
        from amy.macos import CameraError

        with mock.patch(
            "amy.tools.screen_tools.capture_camera",
            side_effect=CameraError("Cattura dalla telecamera non riuscita."),
        ):
            result = self.registry.execute("vision.capture", {}, self.context)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "internal_error")

    def test_vision_capture_is_risk_b(self) -> None:
        self.assertEqual(screen_tools.VISION_CAPTURE.risk, RiskLevel.B)

    def test_vision_module_declares_camera_capability(self) -> None:
        from amy.modules import build_module_registry
        from amy.shared.module import ModuleContext

        registry = build_module_registry(self.temp.config)
        registry.start_all(ModuleContext(config=self.temp.config, events=None))
        modules = {item["manifest"]["name"]: item for item in registry.statuses()}
        self.assertIn("vision.camera", modules["vision"]["manifest"]["capabilities"])
        self.assertIn("vision.capture", modules["vision"]["manifest"]["tools"])
        self.assertFalse(modules["vision"]["status"]["data"]["camera"])
        self.assertFalse(modules["vision"]["status"]["data"]["describe"])


if __name__ == "__main__":
    unittest.main()
