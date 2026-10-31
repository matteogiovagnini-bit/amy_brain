"""Servizio vocale: TTS, STT, registrazione e ciclo wake word."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.errors import VoiceError
from ..core.logging_setup import get_logger
from .recorder import Recorder
from .stt import STT, build_stt
from .tts import MacSayTTS, NullTTS, TTS
from .wakeword import WakeWordDetector

_log = get_logger("voice")


class VoiceService:
    def __init__(self, config) -> None:
        self.config = config
        self.enabled = bool(config.get("voice.enabled", False))
        engine = str(config.get("voice.tts.engine", "say")).lower()
        if engine == "say":
            self.tts: TTS = MacSayTTS(
                str(config.get("voice.tts.voice", "Alice")),
                int(config.get("voice.tts.rate", 185)),
            )
        else:
            self.tts = NullTTS()
        self.stt: STT = build_stt(config)
        self.recorder = Recorder(
            str(config.get("voice.recorder.engine", "ffmpeg")),
            str(config.get("voice.recorder.device", ":0")),
        )
        # L'elenco delle voci italiane costa alcuni secondi (`say -v ?`): viene
        # preparato in background così la prima richiesta di stato è immediata.
        threading.Thread(target=self._warm_tts_cache, daemon=True).start()
        self.wake = WakeWordDetector(
            str(config.get("voice.wake_word.phrase", "amy")),
            float(config.get("voice.wake_word.sensitivity", 0.5)),
        )
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ sintesi
    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        return self.tts.speak(text, block=block)

    def stop_speaking(self) -> None:
        self.tts.stop()

    # ------------------------------------------------------------------ ascolto
    def listen_once(self, seconds: Optional[float] = None) -> str:
        if not self.recorder.status().get("available"):
            raise VoiceError("Nessun registratore audio disponibile (serve ffmpeg o sox).")
        if not self.stt.available:
            raise VoiceError("Nessun motore di riconoscimento vocale configurato.")
        duration = seconds if seconds is not None else float(self.config.get("voice.recorder.seconds", 5))
        audio = self.recorder.record(duration)
        try:
            return self.stt.transcribe(audio)
        finally:
            try:
                audio.unlink(missing_ok=True)
            except OSError:
                pass

    def run_wake_loop(
        self,
        on_command: Callable[[str], None],
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Ascolta in modo continuo la wake word.

        Deve essere avviato solo su richiesta esplicita dell'utente: Amy non
        registra in background all'insaputa dell'utente.
        """
        stop = stop_event or self._stop_event
        if not self.recorder.status().get("available"):
            raise VoiceError("Serve ffmpeg o sox per l'ascolto continuo.")
        if not self.stt.available:
            raise VoiceError("Serve un motore STT locale per l'ascolto continuo.")
        _log.info("Ascolto wake word «%s» attivo", self.wake.phrase)
        while not stop.is_set():
            try:
                text = self.listen_once(float(self.config.get("voice.recorder.seconds", 5)))
            except VoiceError as exc:
                _log.warning("Errore di ascolto: %s", exc.message)
                time.sleep(1.0)
                continue
            command = self.wake.extract_command(text)
            if command:
                self.tts.stop()  # barge-in: l'utente interrompe Amy
                _log.info("Wake word rilevata")
                on_command(command)
            elif self.wake.matches(text):
                # Solo "Amy": ascolta il comando successivo.
                self.tts.stop()
                try:
                    follow_up = self.listen_once(float(self.config.get("voice.recorder.seconds", 5)))
                except VoiceError as exc:
                    _log.warning("Errore nel secondo ascolto: %s", exc.message)
                    continue
                if follow_up.strip():
                    on_command(follow_up.strip())

    def start_wake_loop(self, on_command: Callable[[str], None]) -> threading.Thread:
        if self._loop_thread and self._loop_thread.is_alive():
            return self._loop_thread
        self._stop_event.clear()
        self._loop_thread = threading.Thread(
            target=self.run_wake_loop,
            args=(on_command,),
            name="amy-wake-loop",
            daemon=True,
        )
        self._loop_thread.start()
        return self._loop_thread

    def stop_wake_loop(self) -> None:
        self._stop_event.set()
        self.stop_speaking()

    def _warm_tts_cache(self) -> None:
        """Precarica in background l'elenco delle voci (se il motore lo supporta)."""
        warm = getattr(self.tts, "italian_voices", None)
        if not callable(warm):
            return
        try:
            warm()
        except Exception as exc:  # pragma: no cover - difensivo
            _log.debug("Precaricamento voci non riuscito: %s", exc)

    def status(self) -> Dict[str, Any]:
        tts_status = self.tts.status()
        stt_status = self.stt.status()
        recorder_status = self.recorder.status()
        return {
            "enabled": self.enabled,
            "speaking": bool(self.tts.is_speaking()),
            "tts": tts_status,
            "stt": stt_status,
            "recorder": recorder_status,
            "wake_word": {
                "phrase": self.wake.phrase,
                "enabled": bool(self.config.get("voice.wake_word.enabled", False)),
                "running": bool(self._loop_thread and self._loop_thread.is_alive()),
            },
            "ready_for_voice_commands": bool(
                tts_status.get("available")
                and stt_status.get("available")
                and recorder_status.get("available")
            ),
        }
