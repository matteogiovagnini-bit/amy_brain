"""Test della wake word «Amy» e del ciclo di ascolto continuo.

Il ciclo deve partire solo su richiesta esplicita, fermarsi da solo dopo il
limite configurato e non registrare nulla quando non è attivo.
"""

from __future__ import annotations

import threading
import time
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from amy.core.errors import VoiceError
from amy.voice.service import VoiceService
from amy.voice.wakeword import WakeWordDetector, edit_distance, normalize
from tests.helpers import TempAmy


class WakeWordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = WakeWordDetector("amy", 0.8)

    def test_exact_phrase(self) -> None:
        self.assertTrue(self.detector.matches("Amy, che ore sono?"))

    def test_phrase_with_prefix(self) -> None:
        self.assertTrue(self.detector.matches("ehi Amy che ore sono"))

    def test_common_transcription_errors(self) -> None:
        # whisper trascrive spesso «Amy» come «Emi», «Ami» o «Emy».
        for phrase in ("Emi che ore sono", "Ami che ore sono", "Emy accendi la luce"):
            self.assertTrue(self.detector.matches(phrase), phrase)

    def test_errors_are_accepted_also_at_default_sensitivity(self) -> None:
        detector = WakeWordDetector("amy", 0.5)
        for phrase in ("Emi, che ore sono?", "Ami accendi la luce", "Emy"):
            self.assertTrue(detector.matches(phrase), phrase)

    def test_fuzzy_match_only_at_the_start(self) -> None:
        detector = WakeWordDetector("amy", 0.5)
        self.assertFalse(detector.matches("non lo faccio mai"))
        self.assertTrue(detector.matches("ehi Emi che ore sono"))

    def test_unrelated_text_is_rejected(self) -> None:
        for phrase in ("che ore sono", "grazie mille", "amaca nuova"):
            self.assertFalse(self.detector.matches(phrase), phrase)

    def test_real_transcription_variants_are_accepted(self) -> None:
        """Con `small` «Amy» può diventare «Remy» o «Remi»."""
        detector = WakeWordDetector("amy", 0.5)
        for phrase in ("Remy, apri mail", "Remi che ore sono", "Emi accendi la luce"):
            self.assertTrue(detector.matches(phrase), phrase)
            self.assertIsNotNone(detector.extract_command(phrase), phrase)

    def test_short_unrelated_words_do_not_trigger_the_wake_word(self) -> None:
        """«ha» dista due caratteri da «amy» ma non è la wake word.

        Osservato il 2 novembre 2026: «ha pret mehilda» ha attivato Amy e
        eseguito un comando mai pronunciato. Il confronto tollerante deve
        accettare «Emi»/«Ami» ma non parole comuni come «ha», «mai», «mia».
        """
        detector = WakeWordDetector("amy", 0.5)
        for phrase in ("ha pret mehilda", "non lo faccio mai", "mia sorella"):
            self.assertFalse(detector.matches(phrase), phrase)

    def test_extract_command_after_phrase(self) -> None:
        self.assertEqual(self.detector.extract_command("Amy che ore sono"), "che ore sono")
        self.assertEqual(self.detector.extract_command("ehi Amy, accendi la luce"), "accendi la luce")

    def test_extract_command_without_phrase(self) -> None:
        self.assertIsNone(self.detector.extract_command("che ore sono"))
        self.assertIsNone(self.detector.extract_command("Amy"))

    def test_edit_distance(self) -> None:
        self.assertEqual(edit_distance("amy", "amy"), 0)
        self.assertEqual(edit_distance("amy", "emi"), 2)
        self.assertEqual(edit_distance("", "abc"), 3)

    def test_normalize_strips_accents_and_punctuation(self) -> None:
        self.assertEqual(normalize("Ehi, Amy! Perché?"), "ehi amy perche")


class FakeRecorder:
    def __init__(self) -> None:
        self.calls = 0
        self.times = []
        self.dir = TemporaryDirectory()

    def status(self):
        return {"available": True, "engine": "fake"}

    def record(self, seconds: float = 5.0, *, path: Path = None) -> Path:
        self.calls += 1
        self.times.append(time.monotonic())
        time.sleep(0.05)
        target = Path(path) if path else Path(self.dir.name) / ("audio-%d.wav" % self.calls)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 160)
        return target

    def close(self) -> None:
        self.dir.cleanup()


class FakeTTS:
    """Sintesi finta: dice solo se sta parlando."""

    def __init__(self, speaking: bool = False) -> None:
        self.speaking = speaking
        self.spoken = []

    def status(self):
        return {"available": True, "engine": "fake"}

    def is_speaking(self) -> bool:
        return self.speaking

    def speech_overlaps(self, start: float, end: float) -> bool:
        return self.speaking

    def speak(self, text, *, block: bool = False):
        self.spoken.append(text)
        return {"spoken": True}

    def stop(self) -> None:
        self.speaking = False


class EchoTTS(FakeTTS):
    """Sintesi che si sovrappone solo ai primi frammenti registrati."""

    def __init__(self, echo_calls: int = 1) -> None:
        super().__init__()
        self.echo_calls = echo_calls
        self.checks = 0

    def speech_overlaps(self, start: float, end: float) -> bool:
        self.checks += 1
        return self.checks <= self.echo_calls


class SilentSTT:
    @property
    def available(self) -> bool:
        return True

    def status(self):
        return {"available": True, "engine": "fake"}

    def transcribe(self, audio_path: Path) -> str:
        return ""


class StuckRecorder:
    """Registratore che resta bloccato nel HAL e poi si dichiara guasto."""

    def __init__(self) -> None:
        self.calls = 0
        self.stuck = False

    def status(self):
        return {"available": True, "engine": "fake", "stuck": self.stuck}

    def record(self, seconds: float = 5.0, *, path: Path = None) -> Path:
        self.calls += 1
        self.stuck = True
        raise VoiceError(
            "Il microfono non risponde: la registrazione è stata interrotta.",
            detail="PortAudio non ha restituito il controllo.",
        )


class VoiceLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)
        self.recorder = FakeRecorder()
        self.service.recorder = self.recorder
        self.service.stt = SilentSTT()

    def tearDown(self) -> None:
        self.service.stop_wake_loop()
        self.recorder.close()
        self.temp.close()

    def test_loop_does_not_start_by_itself(self) -> None:
        self.assertFalse(self.service.wake_running)
        status = self.service.status()
        self.assertIs(status["wake_word"]["running"], False)

    def test_deadline_stops_the_loop_before_recording(self) -> None:
        self.service._wake_deadline = time.monotonic() - 1  # limite già superato
        self.service.run_wake_loop(lambda text: None)
        self.assertEqual(self.recorder.calls, 0)
        self.assertEqual(self.service._wake_stop_reason, "limite di durata raggiunto")

    def test_start_and_stop_set_the_state(self) -> None:
        thread = self.service.start_wake_loop(lambda text: None, max_minutes=1)
        self.assertTrue(thread.is_alive())
        self.assertTrue(self.service.wake_running)
        self.service.stop_wake_loop()
        thread.join(timeout=3)
        self.assertFalse(self.service.wake_running)

    def test_loop_stops_honestly_when_the_microphone_hangs(self) -> None:
        """Se il microfono non risponde il ciclo si ferma e lo dichiara.

        Senza questo, un blocco nel HAL farebbe girare per sempre un ciclo di
        errori, lasciando la UI convinta che l'ascolto sia attivo.
        """
        stuck = StuckRecorder()
        self.service.recorder = stuck
        started = time.monotonic()
        self.service.run_wake_loop(lambda text: None)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0)
        self.assertEqual(stuck.calls, 1)
        self.assertEqual(self.service._wake_stop_reason, "microfono non rispondente")
        self.assertIs(self.service.status()["wake_word"]["available"], False)

    def test_start_refuses_a_stuck_microphone(self) -> None:
        stuck = StuckRecorder()
        stuck.stuck = True
        self.service.recorder = stuck
        with self.assertRaises(VoiceError) as caught:
            self.service.start_wake_loop(lambda text: None)
        self.assertIn("microfono non risponde", caught.exception.message.lower())
        self.assertEqual(stuck.calls, 0)
        self.assertFalse(self.service.wake_running)

    def test_detected_command_is_forwarded(self) -> None:
        seen = []

        class CommandSTT(SilentSTT):
            def __init__(self) -> None:
                self.calls = 0

            def transcribe(self, audio_path: Path) -> str:
                self.calls += 1
                return "Amy che ore sono" if self.calls == 1 else ""

        self.service.stt = CommandSTT()
        thread = self.service.start_wake_loop(seen.append, max_minutes=1)
        deadline = time.monotonic() + 3
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
        self.service.stop_wake_loop()
        thread.join(timeout=3)
        self.assertEqual(seen, ["che ore sono"])


class EchoGuardTests(unittest.TestCase):
    """Half-duplex: senza barge-in il microfono non registra mentre Amy parla."""

    def setUp(self) -> None:
        self.temp = TempAmy()
        self.service = VoiceService(self.temp.config)
        self.service.config.data["voice"]["conversation"]["barge_in"] = False
        self.recorder = FakeRecorder()
        self.service.recorder = self.recorder
        self.service.stt = SilentSTT()

    def tearDown(self) -> None:
        self.service.stop_wake_loop()
        self.recorder.close()
        self.temp.close()

    def _run_loop(self, on_command, stop: threading.Event) -> threading.Thread:
        thread = threading.Thread(
            target=self.service.run_wake_loop,
            args=(on_command,),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        thread.start()
        return thread

    def test_loop_does_not_record_while_amy_speaks(self) -> None:
        """Con Amy in parola il ciclo non apre il microfono."""
        tts = FakeTTS(speaking=True)
        self.service.tts = tts
        stop = threading.Event()
        thread = self._run_loop(lambda text: None, stop)
        time.sleep(0.4)
        stop.set()
        thread.join(timeout=3)
        self.assertEqual(self.recorder.calls, 0)

    def test_fragment_with_amy_voice_is_discarded(self) -> None:
        """Un frammento registrato mentre Amy parlava non è un comando."""

        class CommandSTT(SilentSTT):
            def __init__(self) -> None:
                self.calls = 0

            def transcribe(self, audio_path: Path) -> str:
                self.calls += 1
                # Il primo frammento è contaminato dall'eco, il secondo no.
                return "Amy che ore sono" if self.calls <= 2 else ""

        self.service.stt = CommandSTT()
        self.service.tts = EchoTTS(echo_calls=1)
        seen = []
        stop = threading.Event()
        thread = self._run_loop(seen.append, stop)
        deadline = time.monotonic() + 3
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
        stop.set()
        thread.join(timeout=3)
        # Il primo frammento (con la voce di Amy) è scartato, il secondo no.
        self.assertEqual(seen, ["che ore sono"])

    def test_cooldown_after_speech(self) -> None:
        """Dopo la sintesi il ciclo aspetta qualche istante prima di registrare."""
        self.service.config.data["voice"]["wake_word"]["echo_guard_cooldown_s"] = 0.4
        tts = FakeTTS(speaking=True)
        self.service.tts = tts
        stopped_at = []
        stop = threading.Event()
        thread = self._run_loop(lambda text: None, stop)

        def release() -> None:
            time.sleep(0.2)
            tts.speaking = False
            stopped_at.append(time.monotonic())

        threading.Thread(target=release, daemon=True).start()
        deadline = time.monotonic() + 3
        while not self.recorder.times and time.monotonic() < deadline:
            time.sleep(0.02)
        stop.set()
        thread.join(timeout=3)
        self.assertTrue(self.recorder.times, "il ciclo deve riprendere a registrare")
        self.assertTrue(stopped_at, "la sintesi deve essere terminata")
        # La registrazione deve avvenire almeno 0,35 s dopo la fine della sintesi.
        self.assertGreaterEqual(self.recorder.times[0] - stopped_at[0], 0.35)

    def test_echo_guard_can_be_disabled(self) -> None:
        """Con la protezione disattivata il comportamento resta quello di prima."""
        self.service.config.data["voice"]["wake_word"]["echo_guard"] = False
        self.service.tts = EchoTTS(echo_calls=5)

        class CommandSTT(SilentSTT):
            def __init__(self) -> None:
                self.calls = 0

            def transcribe(self, audio_path: Path) -> str:
                self.calls += 1
                return "Amy che ore sono" if self.calls == 1 else ""

        self.service.stt = CommandSTT()
        seen = []
        stop = threading.Event()
        thread = self._run_loop(seen.append, stop)
        deadline = time.monotonic() + 3
        while not seen and time.monotonic() < deadline:
            time.sleep(0.05)
        stop.set()
        thread.join(timeout=3)
        self.assertEqual(seen, ["che ore sono"])

    def test_status_exposes_the_echo_guard(self) -> None:
        wake = self.service.status()["wake_word"]
        self.assertIs(wake["echo_guard"], True)
        self.assertEqual(wake["echo_guard_cooldown_s"], 0.8)


if __name__ == "__main__":
    unittest.main()

class SequenceSTT(SilentSTT):
    """Restituisce le trascrizioni in ordine, poi stringa vuota."""

    def __init__(self, texts) -> None:
        self.texts = list(texts)
        self.calls = 0

    def transcribe(self, audio_path: Path) -> str:
        self.calls += 1
        return self.texts.pop(0) if self.texts else ""


class VoiceConfirmationTests(unittest.TestCase):
    """La conferma vocale: si risponde sì/no senza ripetere «Amy»."""

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

    def test_answer_is_read_without_the_wake_word(self) -> None:
        answers = []

        def on_command(text: str) -> None:
            self.service.await_confirmation(
                lambda answer: answers.append(answer) or answer.strip().lower() == "si",
                timeout_s=10,
            )

        self.service.stt = SequenceSTT(["Amy elimina l'evento", "si"])
        thread = self.service.start_wake_loop(on_command, max_minutes=1)
        self.assertTrue(self._wait(lambda: answers == ["si"]), answers)
        self.assertFalse(self.service.awaiting_confirmation)
        self.service.stop_wake_loop()
        thread.join(timeout=3)

    def test_unclear_answer_keeps_waiting(self) -> None:
        answers = []

        def on_command(text: str) -> None:
            def callback(answer: str) -> bool:
                answers.append(answer)
                return answer.strip().lower() == "no"
            self.service.await_confirmation(callback, timeout_s=10)

        self.service.stt = SequenceSTT(["Amy elimina l'evento", "boh", "no"])
        thread = self.service.start_wake_loop(on_command, max_minutes=1)
        self.assertTrue(self._wait(lambda: len(answers) >= 2), answers)
        self.assertEqual(answers[:2], ["boh", "no"])
        self.assertFalse(self.service.awaiting_confirmation)
        self.service.stop_wake_loop()
        thread.join(timeout=3)

    def test_expired_confirmation_is_cancelled(self) -> None:
        called = []

        def on_command(text: str) -> None:
            self.service.await_confirmation(lambda answer: called.append(answer) or True, timeout_s=10)
            # Scadenza forzata: il prossimo frammento deve trovare la conferma scaduta.
            self.service._confirmation_deadline = time.monotonic() - 1

        self.service.stt = SequenceSTT(["Amy elimina l'evento", "si"])
        thread = self.service.start_wake_loop(on_command, max_minutes=1)
        self.assertTrue(
            self._wait(lambda: any("Conferma scaduta" in said for said in self.service.tts.spoken))
        )
        self.assertEqual(called, [])
        self.assertFalse(self.service.awaiting_confirmation)
        self.service.stop_wake_loop()
        thread.join(timeout=3)

    def test_stop_cancels_a_pending_confirmation(self) -> None:
        def on_command(text: str) -> None:
            self.service.await_confirmation(lambda answer: True)

        self.service.stt = SequenceSTT(["Amy elimina l'evento"])
        thread = self.service.start_wake_loop(on_command, max_minutes=1)
        self.assertTrue(self._wait(lambda: self.service.awaiting_confirmation))
        self.service.stop_wake_loop()
        thread.join(timeout=3)
        self.assertFalse(self.service.awaiting_confirmation)


if __name__ == "__main__":
    unittest.main()
