"""Test del servizio vocale: lo stato esposto alla dashboard deve essere reale.

In particolare ``speaking`` deve riflettere la sintesi effettivamente in
corso e mai una semplice richiesta del frontend.
"""

from __future__ import annotations

import unittest

from amy.voice.service import VoiceService
from tests.helpers import TempAmy


class FakeTTS:
    """Sintesi finta: dice solo se sta parlando."""

    def __init__(self, speaking: bool = False, available: bool = True) -> None:
        self.speaking = speaking
        self.available = available

    def status(self):
        return {"available": self.available, "engine": "fake"}

    def is_speaking(self) -> bool:
        return self.speaking

    def speak(self, text, *, block: bool = False):
        return {"spoken": True, "test": True}

    def stop(self) -> None:
        self.speaking = False

    def to_file(self, text, path):
        raise NotImplementedError


class VoiceServiceStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)

    def tearDown(self) -> None:
        self.temp.close()

    def test_status_exposes_speaking_flag(self) -> None:
        status = self.service.status()
        self.assertIn("speaking", status)
        self.assertIs(status["speaking"], False)
        self.assertIn("wake_word", status)
        self.assertIn("ready_for_voice_commands", status)

    def test_speaking_reflects_the_real_tts(self) -> None:
        self.service.tts = FakeTTS(speaking=True)
        self.assertIs(self.service.status()["speaking"], True)
        self.service.tts = FakeTTS(speaking=False)
        self.assertIs(self.service.status()["speaking"], False)

    def test_stop_speaking_clears_the_flag(self) -> None:
        self.service.tts = FakeTTS(speaking=True)
        self.service.stop_speaking()
        self.assertIs(self.service.status()["speaking"], False)


if __name__ == "__main__":
    unittest.main()
