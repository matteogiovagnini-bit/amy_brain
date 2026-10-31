"""Test della voce: wake word e sintesi su file (quando ``say`` è disponibile)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from amy.voice.tts import MacSayTTS
from amy.voice.wakeword import WakeWordDetector, normalize


class WakeWordTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize("Ehi  AMY, che ore sono?"), "ehi amy che ore sono")
        self.assertEqual(normalize("Città perché"), "citta perche")

    def test_matches_and_extracts_command(self) -> None:
        detector = WakeWordDetector("amy", 0.5)
        self.assertTrue(detector.matches("Ehi Amy, che ore sono?"))
        self.assertTrue(detector.matches("Amy"))
        self.assertFalse(detector.matches("Amelia è qui"))
        self.assertEqual(detector.extract_command("Ehi Amy, che ore sono?"), "che ore sono")
        self.assertIsNone(detector.extract_command("Amy"))

    def test_high_sensitivity_variants(self) -> None:
        low = WakeWordDetector("amy", 0.4)
        high = WakeWordDetector("amy", 0.9)
        self.assertFalse(low.matches("Ami che ore sono"))
        self.assertTrue(high.matches("Ami che ore sono"))


@unittest.skipUnless(shutil.which("say"), "comando 'say' di macOS non disponibile")
class MacSayTTSTests(unittest.TestCase):
    def test_status(self) -> None:
        status = MacSayTTS().status()
        self.assertTrue(status["available"])
        self.assertEqual(status["engine"], "say")
        self.assertIn("Alice", status["italian_voices"])

    def test_synthesize_to_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="amy-tts-test-") as tmp:
            target = MacSayTTS().to_file("Verifica della voce di Amy.", Path(tmp) / "voce.aiff")
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
