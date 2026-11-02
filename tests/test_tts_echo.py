"""Test del tracciamento degli intervalli di sintesi (protezione dall'eco).

Il ciclo di wake word deve sapere quando Amy sta parlando e quando ha finito,
senza emettere audio reale: il processo `say` viene sostituito con un falso.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

from amy.voice.tts import MacSayTTS, NullTTS


class FakeProcess:
    """Processo `say` finto: non produce audio e si chiude su comando."""

    def __init__(self) -> None:
        self.pid = 4242
        self.returncode = 0
        self._done = threading.Event()

    def poll(self):
        return 0 if self._done.is_set() else None

    def wait(self, timeout=None):
        self._done.wait(timeout if timeout is not None else 5)
        return 0

    def communicate(self, timeout=None):
        # La sintesi finisce subito: il falso processo non emette audio.
        self._done.set()
        return ("", "")

    def terminate(self) -> None:
        self._done.set()

    def kill(self) -> None:
        self._done.set()


class SpeechIntervalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tts = MacSayTTS("Alice", 185)
        self.process = FakeProcess()
        self.patcher = mock.patch("amy.voice.tts.subprocess.Popen", return_value=self.process)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_no_speech_means_no_overlap(self) -> None:
        now = time.monotonic()
        self.assertIs(self.tts.speech_overlaps(now, now + 1), False)

    def test_speaking_means_overlap(self) -> None:
        self.tts.speak("Ciao", block=False)
        now = time.monotonic()
        self.assertIs(self.tts.is_speaking(), True)
        self.assertIs(self.tts.speech_overlaps(now, now + 1), True)

    def test_finished_speech_keeps_its_interval(self) -> None:
        self.tts.speak("Ciao", block=False)
        started = time.monotonic()
        self.process._done.set()
        deadline = time.monotonic() + 3
        while self.tts.is_speaking() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIs(self.tts.is_speaking(), False)
        # La finestra che contiene la sintesi è sovrapposta...
        self.assertIs(self.tts.speech_overlaps(started - 0.1, started + 0.5), True)
        # ...mentre una finestra successiva non lo è.
        self.assertIs(self.tts.speech_overlaps(started + 10, started + 11), False)

    def test_blocking_speech_closes_the_interval(self) -> None:
        self.tts.speak("Ciao", block=True)
        now = time.monotonic()
        self.assertIs(self.tts.is_speaking(), False)
        self.assertIs(self.tts.speech_overlaps(now - 2, now + 1), True)
        self.assertIs(self.tts.speech_overlaps(now + 10, now + 11), False)


class NullTTSTests(unittest.TestCase):
    def test_null_tts_never_overlaps(self) -> None:
        tts = NullTTS()
        now = time.monotonic()
        self.assertIs(tts.speech_overlaps(now, now + 1), False)
        self.assertIs(tts.is_speaking(), False)


if __name__ == "__main__":
    unittest.main()
