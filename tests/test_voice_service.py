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
        self.spoken = []

    def status(self):
        return {"available": self.available, "engine": "fake"}

    def is_speaking(self) -> bool:
        return self.speaking

    def speak(self, text, *, block: bool = False):
        self.spoken.append(text)
        return {"spoken": True, "test": True}

    def stop(self) -> None:
        self.speaking = False

    def to_file(self, text, path):
        raise NotImplementedError


class SilentTTS(FakeTTS):
    """Sintesi che non riesce a concludere: simula un `say` appeso."""

    def speak(self, text, *, block: bool = False):
        self.spoken.append(text)
        return {
            "spoken": False,
            "reason": "La sintesi vocale non si è conclusa entro il tempo previsto.",
        }


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


class VoiceGreetingTests(unittest.TestCase):
    """Il saluto di avvio usa solo la sintesi locale e non registra nulla."""

    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)
        self.tts = FakeTTS()
        self.service.tts = self.tts

    def tearDown(self) -> None:
        self.temp.close()

    def _enable_voice(self) -> None:
        self.service.enabled = True

    def test_greeting_speaks_the_default_text(self) -> None:
        self._enable_voice()
        result = self.service.greet()
        self.assertIs(result["spoken"], True)
        self.assertEqual(self.tts.spoken, ["Amy è attiva e operativa."])

    def test_greeting_uses_the_configured_text(self) -> None:
        self._enable_voice()
        self.service.config.data["voice"]["startup_greeting_text"] = "Amy, tutto pronto."
        result = self.service.greet()
        self.assertIs(result["spoken"], True)
        self.assertEqual(self.tts.spoken, ["Amy, tutto pronto."])

    def test_greeting_is_silent_when_voice_is_disabled(self) -> None:
        result = self.service.greet()
        self.assertIs(result["spoken"], False)
        self.assertEqual(result["reason"], "voce disabilitata")
        self.assertEqual(self.tts.spoken, [])

    def test_greeting_can_be_disabled(self) -> None:
        self._enable_voice()
        self.service.config.data["voice"]["startup_greeting"] = False
        result = self.service.greet()
        self.assertIs(result["spoken"], False)
        self.assertEqual(self.tts.spoken, [])

    def test_greeting_is_silent_without_tts(self) -> None:
        self._enable_voice()
        self.service.tts = FakeTTS(available=False)
        result = self.service.greet()
        self.assertIs(result["spoken"], False)
        self.assertEqual(result["reason"], "sintesi vocale non disponibile")

    def test_status_exposes_the_greeting(self) -> None:
        status = self.service.status()
        self.assertIn("startup_greeting", status)
        self.assertIs(status["startup_greeting"]["enabled"], True)
        self.assertEqual(status["startup_greeting"]["text"], "Amy è attiva e operativa.")

    def test_greeting_reports_a_silent_tts_honestly(self) -> None:
        """Se la sintesi non riesce Amy non deve dire di aver parlato."""
        self._enable_voice()
        self.service.tts = SilentTTS()
        result = self.service.greet()
        self.assertIs(result["spoken"], False)
        self.assertIn("non si è conclusa", result["reason"])


if __name__ == "__main__":
    unittest.main()
