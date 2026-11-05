"""Test del registratore locale e della scelta del motore audio."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from amy.cli import _probe_microphone
from amy.core.config import Config
from amy.core.errors import VoiceError
from amy.voice import recorder as recorder_module
from amy.voice.recorder import Recorder, SoundDeviceRecorder, build_recorder


class FakeStream:
    """Stream finto: restituisce silenzio PCM 16 bit."""

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, frames):
        return (b"\x00\x00" * frames, False)


class FakeModule:
    """Sostituto minimo di ``sounddevice``."""

    RawInputStream = FakeStream

    def query_devices(self, kind="input"):
        return {"name": "Microfono di prova"}


class RecorderStatusTests(unittest.TestCase):
    def test_status_queries_the_device_only_once(self) -> None:
        """Il controllo di salute non deve interrogare PortAudio ogni volta.

        Con il microfono aperto `query_devices` può bloccarsi: l'app vedeva
        /api/state lento e riavviava il backend mentre era vivo.
        """

        class CountingModule(FakeModule):
            def __init__(self) -> None:
                self.calls = 0

            def query_devices(self, kind="input"):
                self.calls += 1
                return {"name": "Microfono di prova"}

        module = CountingModule()
        with mock.patch.object(SoundDeviceRecorder, "module", return_value=module):
            recorder = SoundDeviceRecorder()
            for _ in range(5):
                status = recorder.status()
        self.assertEqual(module.calls, 1)
        self.assertEqual(status["device"], "Microfono di prova")


class HangingStream:
    """Stream che resta bloccato nell'apertura, come ``Pa_OpenStream``.

    Riproduce il difetto osservato il 2026-11-01: il HAL di CoreAudio non
    restituisce il controllo e la registrazione non termina mai.
    """

    release = threading.Event()

    def __init__(self, *args, **kwargs) -> None:
        HangingStream.release.wait(10)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, frames):
        return (b"\x00\x00" * frames, False)


class HangingModule:
    RawInputStream = HangingStream

    def query_devices(self, kind="input"):
        return {"name": "Microfono bloccato"}


def voice_config(engine: str = "auto", **extra) -> Config:
    section = {"engine": engine, "device": "", "samplerate": 16000}
    section.update(extra)
    return Config({"voice": {"recorder": section}})


class BuildRecorderTests(unittest.TestCase):
    def test_explicit_sounddevice(self) -> None:
        recorder = build_recorder(voice_config("sounddevice"))
        self.assertIsInstance(recorder, SoundDeviceRecorder)

    def test_explicit_ffmpeg(self) -> None:
        recorder = build_recorder(voice_config("ffmpeg"))
        self.assertIsInstance(recorder, Recorder)

    def test_auto_prefers_sounddevice_when_available(self) -> None:
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", FakeModule()):
            self.assertIsInstance(build_recorder(voice_config("auto")), SoundDeviceRecorder)

    def test_auto_falls_back_to_ffmpeg(self) -> None:
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", False):
            self.assertIsInstance(build_recorder(voice_config("auto")), Recorder)


class SoundDeviceRecorderTests(unittest.TestCase):
    def tearDown(self) -> None:
        recorder_module._SOUNDDEVICE = None
        HangingStream.release.set()

    def test_status_without_module(self) -> None:
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", False):
            status = SoundDeviceRecorder().status()
        self.assertIs(status["available"], False)
        self.assertEqual(status["engine"], "sounddevice")

    def test_status_with_module(self) -> None:
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", FakeModule()):
            status = SoundDeviceRecorder().status()
        self.assertIs(status["available"], True)
        self.assertEqual(status["device"], "Microfono di prova")

    def test_record_without_module_raises(self) -> None:
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", False):
            with self.assertRaises(VoiceError):
                SoundDeviceRecorder().record(1.0)

    def test_record_writes_a_valid_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "prova.wav"
            with mock.patch.object(recorder_module, "_SOUNDDEVICE", FakeModule()):
                produced = SoundDeviceRecorder().record(0.2, path=target)
            self.assertEqual(produced, target)
            with wave.open(str(target), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 16000)
                self.assertGreater(wav.getnframes(), 0)

    def test_record_does_not_hang_when_the_hal_does_not_answer(self) -> None:
        """Un blocco di PortAudio deve diventare un errore, non un'attesa infinita."""
        HangingStream.release.clear()
        recorder = SoundDeviceRecorder(timeout=0.2)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bloccato.wav"
            with mock.patch.object(recorder_module, "_SOUNDDEVICE", HangingModule()):
                started = time.monotonic()
                with self.assertRaises(VoiceError) as caught:
                    recorder.record(5.0, path=target)
                elapsed = time.monotonic() - started
            self.assertLess(elapsed, 3.0)
            self.assertIn("non risponde", caught.exception.message)
            self.assertFalse(target.exists())
        self.assertTrue(recorder.status()["stuck"])
        self.assertIn("PortAudio", recorder.status()["problem"])

    def test_a_stuck_recorder_fails_fast_instead_of_opening_again(self) -> None:
        """Dopo un blocco non si aprono altri flussi: si fallisce subito."""
        HangingStream.release.clear()
        recorder = SoundDeviceRecorder(timeout=0.2)
        with mock.patch.object(recorder_module, "_SOUNDDEVICE", HangingModule()):
            with self.assertRaises(VoiceError):
                recorder.record(1.0)
            started = time.monotonic()
            with self.assertRaises(VoiceError) as caught:
                recorder.record(1.0)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5)
        self.assertIn("microfono non risponde", caught.exception.message.lower())


class MicrophoneProbeTests(unittest.TestCase):
    """Il controllo «Microfono» del doctor deve provare il dispositivo davvero."""

    def test_probe_reads_and_deletes_the_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "mic.wav"
            target.write_bytes(b"\x00\x00" * 16)

            class Recorder:
                def record(self, seconds):
                    return target

            result = _probe_microphone(Recorder())
        self.assertIs(result["ok"], True)
        self.assertFalse(target.exists())

    def test_probe_reports_a_microphone_that_does_not_answer(self) -> None:
        class Recorder:
            def record(self, seconds):
                raise VoiceError("Il microfono non risponde: la registrazione è stata interrotta.")

        result = _probe_microphone(Recorder())
        self.assertIs(result["ok"], False)
        self.assertIn("non risponde", result["detail"])


if __name__ == "__main__":
    unittest.main()

class SequenceStream:
    """Stream finto che restituisce frame predefiniti."""

    def __init__(self, frames) -> None:
        self.frames = list(frames)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, frames):
        if self.frames:
            return (self.frames.pop(0), False)
        return (b"\x00\x00" * frames, False)


class VadModule(FakeModule):
    def __init__(self, frames) -> None:
        self.frames = frames

    def RawInputStream(self, *args, **kwargs):
        return SequenceStream(self.frames)


class VoiceActivityTests(unittest.TestCase):
    def _frames(self, count: int, amplitude: int) -> bytes:
        return (amplitude.to_bytes(2, "little", signed=True) * count * 480)

    def test_stops_after_silence_without_cutting_speech(self) -> None:
        silence = b"\x00\x00" * 480
        speech = self._frames(1, 4000)
        frames = [silence] * 10 + [speech] * 20 + [silence] * 40
        module = VadModule(frames)
        with mock.patch.object(SoundDeviceRecorder, "module", return_value=module):
            recorder = SoundDeviceRecorder()
            with tempfile.TemporaryDirectory(prefix="amy-vad-") as tmp:
                path = recorder.record_until_silence(
                    max_seconds=5.0, silence_s=0.6, start_timeout_s=2.0, path=Path(tmp) / "vad.wav"
                )
                with wave.open(str(path), "rb") as wav:
                    duration = wav.getnframes() / float(wav.getframerate())
        self.assertGreater(duration, 0.5)
        self.assertLess(duration, 5.0)

    def test_no_speech_returns_an_empty_recording(self) -> None:
        module = VadModule([b"\x00\x00" * 480] * 100)
        with mock.patch.object(SoundDeviceRecorder, "module", return_value=module):
            recorder = SoundDeviceRecorder()
            with tempfile.TemporaryDirectory(prefix="amy-vad-") as tmp:
                with self.assertRaises(VoiceError):
                    recorder.record_until_silence(
                        max_seconds=2.0, silence_s=0.5, start_timeout_s=0.2, path=Path(tmp) / "vad.wav"
                    )


if __name__ == "__main__":
    unittest.main()
