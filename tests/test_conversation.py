"""Test della conversazione continua, del timeout e del barge-in.

Non usano il microfono reale: registratore, STT e TTS sono sostituiti da fake.
"""

from __future__ import annotations

import threading
import time
import unittest

from amy.voice.service import VoiceService
from amy.voice.state import VoiceState, VoiceStateMachine
from tests.helpers import TempAmy
from tests.test_voice_wake import FakeRecorder, FakeTTS, SequenceSTT, SilentSTT


class StateMachineTests(unittest.TestCase):
    def test_allowed_transition(self) -> None:
        machine = VoiceStateMachine()
        self.assertTrue(machine.can_transition(VoiceState.LISTENING))
        self.assertTrue(machine.set(VoiceState.LISTENING, "prova"))
        self.assertEqual(machine.state, VoiceState.LISTENING)

    def test_unexpected_transition_is_reported(self) -> None:
        machine = VoiceStateMachine()
        self.assertFalse(machine.can_transition(VoiceState.PROCESSING))
        self.assertFalse(machine.set(VoiceState.PROCESSING, "salto"))
        # Lo stato viene comunque applicato: meglio riprendersi che bloccarsi.
        self.assertEqual(machine.state, VoiceState.PROCESSING)

    def test_listeners_receive_changes(self) -> None:
        seen = []
        machine = VoiceStateMachine()
        machine.subscribe(lambda state, reason: seen.append((state, reason)))
        machine.set(VoiceState.LISTENING, "ascolto")
        self.assertEqual(seen, [(VoiceState.LISTENING, "ascolto")])


class BargeTTS(FakeTTS):
    """TTS finto che espone il testo in pronuncia."""

    def __init__(self, text: str = "", speaking: bool = True) -> None:
        super().__init__(speaking=speaking)
        self.current_text = text
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1
        self.speaking = False


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)
        self.recorder = FakeRecorder()
        self.service.recorder = self.recorder
        self.service.tts = FakeTTS()

    def tearDown(self) -> None:
        self.service.stop_wake_loop()
        self.recorder.close()
        self.temp.close()

    def _wait(self, predicate, timeout: float = 4.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def test_follow_up_does_not_need_the_wake_word(self) -> None:
        seen = []
        self.service.stt = SequenceSTT(["Amy che ore sono", "e domani?", ""])
        thread = self.service.start_wake_loop(seen.append, max_minutes=1)
        self.assertTrue(self._wait(lambda: len(seen) >= 2), seen)
        self.assertEqual(seen[0], "che ore sono")
        self.assertEqual(seen[1], "e domani?")
        self.assertTrue(self.service._conversation_active)
        self.service.stop_wake_loop()
        thread.join(timeout=3)

    def test_stop_phrase_ends_the_conversation(self) -> None:
        seen = []
        self.service.stt = SequenceSTT(["Amy che ore sono", "basta", ""])
        thread = self.service.start_wake_loop(seen.append, max_minutes=1)
        self.assertTrue(self._wait(lambda: not self.service._conversation_active and seen), seen)
        self.assertEqual(seen, ["che ore sono"])
        self.assertEqual(self.service.state.state, VoiceState.IDLE)
        self.assertIn("Va bene.", self.service.tts.spoken)
        self.service.stop_wake_loop()
        thread.join(timeout=3)

    def test_timeout_asks_then_returns_to_standby(self) -> None:
        seen = []
        self.service.config.data["voice"]["conversation"]["timeout_s"] = 5
        self.service.stt = SequenceSTT(["Amy che ore sono", "", "", "", ""])
        thread = self.service.start_wake_loop(seen.append, max_minutes=1)

        # Prima scadenza: Amy chiede se siamo ancora presenti.
        self.assertTrue(self._wait(lambda: bool(seen)), seen)
        self.service._conversation_deadline = time.monotonic() - 1
        self.assertTrue(
            self._wait(lambda: "Sei ancora lì?" in self.service.tts.spoken),
            self.service.tts.spoken,
        )

        # Seconda scadenza: torna in standby.
        self.service._presence_prompted = True
        self.service._conversation_deadline = time.monotonic() - 1
        self.assertTrue(
            self._wait(lambda: "Torno in standby." in self.service.tts.spoken),
            self.service.tts.spoken,
        )
        self.assertFalse(self.service._conversation_active)
        self.assertEqual(self.service.state.state, VoiceState.IDLE)
        self.service.stop_wake_loop()
        thread.join(timeout=3)


class BargeInTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)
        self.recorder = FakeRecorder()
        self.service.recorder = self.recorder
        self.tts = BargeTTS(text="Questa è una risposta lunga")
        self.service.tts = self.tts

    def tearDown(self) -> None:
        self.service.stop_wake_loop()
        self.recorder.close()
        self.temp.close()

    def _wait(self, predicate, timeout: float = 4.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def test_wake_word_during_speech_interrupts(self) -> None:
        self.service.stt = SequenceSTT(["Amy", ""])
        self.service.barge_stt = self.service.stt
        stop = threading.Event()
        thread = threading.Thread(
            target=self.service.run_wake_loop,
            args=(lambda text: None,),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        thread.start()
        self.assertTrue(self._wait(lambda: self.tts.stop_calls >= 1))
        stop.set()
        thread.join(timeout=3)
        self.assertFalse(self.tts.speaking)

    def test_echo_text_is_not_an_interruption(self) -> None:
        """Se Amy pronuncia il proprio nome, l'eco non deve interromperla."""
        self.tts.current_text = "Amy è attiva e operativa"
        self.service.stt = SequenceSTT(["Amy", ""])
        self.service.barge_stt = self.service.stt
        stop = threading.Event()
        thread = threading.Thread(
            target=self.service.run_wake_loop,
            args=(lambda text: None,),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        thread.start()
        time.sleep(0.8)
        stop.set()
        thread.join(timeout=3)
        self.assertEqual(self.tts.stop_calls, 0)

    def test_barge_in_disabled_waits_for_the_end(self) -> None:
        self.service.config.data["voice"]["conversation"]["barge_in"] = False
        self.service.stt = SilentSTT()
        stop = threading.Event()
        thread = threading.Thread(
            target=self.service.run_wake_loop,
            args=(lambda text: None,),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        thread.start()
        time.sleep(0.4)
        stop.set()
        thread.join(timeout=3)
        self.assertEqual(self.recorder.calls, 0)


if __name__ == "__main__":
    unittest.main()
