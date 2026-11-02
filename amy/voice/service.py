"""Servizio vocale: TTS, STT, registrazione e ciclo wake word."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.errors import VoiceError
from ..core.logging_setup import get_logger
from .recorder import build_recorder
from .stt import STT, build_stt
from .tts import MacSayTTS, NullTTS, TTS
from .wakeword import WakeWordDetector

_log = get_logger("voice")

DEFAULT_GREETING = "Amy è attiva e operativa."


class VoiceService:
    # Attesa massima per la fine della sintesi prima di registrare: se `say`
    # resta appeso, il ciclo non deve bloccarsi per sempre.
    ECHO_MAX_WAIT_S = 20.0

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
        self.recorder = build_recorder(config)

        self.wake = WakeWordDetector(
            str(config.get("voice.wake_word.phrase", "amy")),
            float(config.get("voice.wake_word.sensitivity", 0.5)),
        )
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._wake_deadline: Optional[float] = None
        self._wake_stop_reason = ""

    def warm(self) -> None:
        """Precarica voci e modello STT in background.

        Non registra nulla: serve solo a evitare che il primo comando vocale
        aspetti il caricamento del modello.
        """
        if getattr(self, "_warmed", False):
            return
        self._warmed = True
        threading.Thread(target=self._warm_tts_cache, daemon=True).start()
        threading.Thread(target=self._warm_stt, daemon=True).start()

    def _warm_stt(self) -> None:
        warm = getattr(self.stt, "warm", None)
        if not callable(warm):
            return
        try:
            warm()
            _log.info("Modello STT locale pronto")
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            _log.warning("Precaricamento STT non riuscito: %s", exc)

    # ------------------------------------------------------------------ sintesi
    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        return self.tts.speak(text, block=block)

    def stop_speaking(self) -> None:
        self.tts.stop()

    def greeting_text(self) -> str:
        """Testo del messaggio di avvio, dalla configurazione."""
        value = str(self.config.get("voice.startup_greeting_text", "") or "").strip()
        return value or DEFAULT_GREETING

    def greet(self, text: Optional[str] = None) -> Dict[str, Any]:
        """Pronuncia il messaggio di avvio di Amy.

        Usa solo la sintesi locale: non registra e non avvia alcun ascolto.
        Se la voce è disabilitata o la sintesi non è disponibile, non dice
        nulla e restituisce il motivo.
        """
        if not self.enabled:
            return {"spoken": False, "reason": "voce disabilitata"}
        if not bool(self.config.get("voice.startup_greeting", True)):
            return {"spoken": False, "reason": "messaggio di avvio disattivato"}
        if not bool(self.tts.status().get("available")):
            return {"spoken": False, "reason": "sintesi vocale non disponibile"}
        message = (text or self.greeting_text()).strip()
        if not message:
            return {"spoken": False, "reason": "messaggio di avvio vuoto"}
        result = self.tts.speak(message, block=True)
        if result.get("spoken"):
            _log.info("Messaggio di avvio pronunciato: %s", message)
        else:
            _log.warning(
                "Messaggio di avvio non pronunciato: %s",
                result.get("reason") or "sintesi non riuscita",
            )
        return dict(result, text=message)

    # ------------------------------------------------------------------ ascolto
    def listen_once(self, seconds: Optional[float] = None) -> str:
        if not self.recorder.status().get("available"):
            raise VoiceError("Nessun registratore audio disponibile (serve ffmpeg o sox).")
        if not self.stt.available:
            raise VoiceError("Nessun motore di riconoscimento vocale configurato.")
        duration = seconds if seconds is not None else float(self.config.get("voice.recorder.seconds", 5))
        # Half-duplex: non registrare mentre Amy parla, altrimenti si cattura
        # la sua voce invece di quella dell'utente.
        if self._echo_guard_enabled() and self.tts.is_speaking():
            self._wait_quiet(self._stop_event, force_cooldown=True)
        audio = self.recorder.record(duration)
        try:
            return self.stt.transcribe(audio)
        finally:
            try:
                audio.unlink(missing_ok=True)
            except OSError:
                pass

    # --------------------------------------------------------- protezione eco
    def _echo_guard_enabled(self) -> bool:
        return bool(self.config.get("voice.wake_word.echo_guard", True))

    def _echo_cooldown(self) -> float:
        try:
            value = float(self.config.get("voice.wake_word.echo_guard_cooldown_s", 0.8))
        except (TypeError, ValueError):
            value = 0.8
        return max(0.0, min(value, 5.0))

    def _wait_quiet(self, stop: threading.Event, *, force_cooldown: bool = False) -> bool:
        """Half-duplex: non registra mentre Amy sta parlando.

        Restituisce ``False`` se il ciclo è stato fermato durante l'attesa.
        """
        if not self._echo_guard_enabled():
            return not stop.is_set()
        deadline = time.monotonic() + self.ECHO_MAX_WAIT_S
        waited = False
        while not stop.is_set() and self.tts.is_speaking():
            if time.monotonic() >= deadline:
                _log.warning(
                    "Echo guard: la sintesi non è finita entro %.0f secondi, proseguo.",
                    self.ECHO_MAX_WAIT_S,
                )
                break
            if self._wake_deadline is not None and time.monotonic() >= self._wake_deadline:
                return False
            waited = True
            time.sleep(0.1)
        if stop.is_set():
            return False
        if waited or force_cooldown:
            cooldown = self._echo_cooldown()
            if cooldown > 0:
                _log.debug("Echo guard: attesa di %.1f s dopo la sintesi", cooldown)
                time.sleep(cooldown)
        return True

    def _echo_overlapped(self, started: float, ended: float) -> bool:
        """Vero se nella finestra registrata Amy stava parlando."""
        if not self._echo_guard_enabled():
            return False
        try:
            return bool(self.tts.speech_overlaps(started, ended))
        except Exception:  # noqa: BLE001 - la protezione non deve bloccare il ciclo
            return False

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
        if self.recorder.status().get("stuck"):
            raise VoiceError(
                "Il microfono non risponde: riavvia il servizio audio di macOS o il Mac, poi riprova."
            )
        if not self.stt.available:
            raise VoiceError("Serve un motore STT locale per l'ascolto continuo.")
        _log.info("Ascolto wake word «%s» attivo", self.wake.phrase)
        seconds = float(self.config.get("voice.recorder.seconds", 5))
        while not stop.is_set():
            if self._wake_deadline is not None and time.monotonic() >= self._wake_deadline:
                self._wake_stop_reason = "limite di durata raggiunto"
                _log.info("Ascolto wake word terminato: %s", self._wake_stop_reason)
                stop.set()
                break
            # Half-duplex: se Amy sta parlando non si registra.
            if not self._wait_quiet(stop):
                break
            started = time.monotonic()
            try:
                text = self.listen_once(seconds)
            except VoiceError as exc:
                _log.warning("Errore di ascolto: %s", exc.message)
                if self.recorder.status().get("stuck"):
                    # Il dispositivo è bloccato nel HAL: continuare produrrebbe
                    # solo errori e thread fermi. Mi fermo e lo dico alla UI.
                    self._wake_stop_reason = "microfono non rispondente"
                    _log.warning("Ascolto wake word terminato: %s", self._wake_stop_reason)
                    stop.set()
                    break
                time.sleep(1.0)
                continue
            ended = time.monotonic()
            if self._echo_overlapped(started, ended):
                # Il frammento contiene la voce di Amy: non è un comando.
                _log.info("Frammento scartato: Amy stava parlando (protezione dall'eco).")
                continue
            command = self.wake.extract_command(text)
            if command:
                self.tts.stop()  # barge-in: l'utente interrompe Amy
                _log.info("Wake word rilevata")
                on_command(command)
            elif self.wake.matches(text):
                # Solo "Amy": ascolta il comando successivo.
                self.tts.stop()
                if not self._wait_quiet(stop, force_cooldown=True):
                    break
                started = time.monotonic()
                try:
                    follow_up = self.listen_once(seconds)
                except VoiceError as exc:
                    _log.warning("Errore nel secondo ascolto: %s", exc.message)
                    if self.recorder.status().get("stuck"):
                        self._wake_stop_reason = "microfono non rispondente"
                        _log.warning("Ascolto wake word terminato: %s", self._wake_stop_reason)
                        stop.set()
                        break
                    continue
                ended = time.monotonic()
                if self._echo_overlapped(started, ended):
                    _log.info("Secondo ascolto scartato: Amy stava parlando (protezione dall'eco).")
                    continue
                if follow_up.strip():
                    on_command(follow_up.strip())

    def start_wake_loop(
        self,
        on_command: Callable[[str], None],
        *,
        max_minutes: Optional[float] = None,
    ) -> threading.Thread:
        """Avvia il ciclo di ascolto solo su richiesta esplicita.

        Dopo ``voice.wake_word.max_minutes`` minuti (20 di default) il ciclo si
        ferma da solo: nessuna registrazione indefinita in background.
        """
        if self._loop_thread and self._loop_thread.is_alive():
            return self._loop_thread
        recorder_status = self.recorder.status()
        if not recorder_status.get("available"):
            raise VoiceError("Serve ffmpeg o sox per l'ascolto continuo.")
        if recorder_status.get("stuck"):
            raise VoiceError(
                "Il microfono non risponde: riavvia il servizio audio di macOS o il Mac, poi riprova.",
                detail=str(recorder_status.get("problem") or ""),
            )
        minutes = max_minutes
        if minutes is None:
            try:
                minutes = float(self.config.get("voice.wake_word.max_minutes", 20))
            except (TypeError, ValueError):
                minutes = 20.0
        minutes = max(1.0, min(float(minutes), 120.0))
        self._wake_deadline = time.monotonic() + minutes * 60.0
        self._wake_stop_reason = ""
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
        self._wake_deadline = None
        self.stop_speaking()

    @property
    def wake_running(self) -> bool:
        """Vero finché il ciclo ascolta davvero.

        Dopo ``stop_wake_loop()`` il thread può essere ancora dentro l'ultima
        registrazione: per la UI l'ascolto è già fermo, così il pulsante non
        resta bloccato per qualche secondo.
        """
        if not (self._loop_thread and self._loop_thread.is_alive()):
            return False
        return not self._stop_event.is_set()

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
            "startup_greeting": {
                "enabled": bool(self.config.get("voice.startup_greeting", True)),
                "text": self.greeting_text(),
            },
            "wake_word": {
                "phrase": self.wake.phrase,
                "enabled": bool(self.config.get("voice.wake_word.enabled", False)),
                "running": self.wake_running,
                "available": bool(
                    stt_status.get("available")
                    and recorder_status.get("available")
                    and not recorder_status.get("stuck")
                ),
                "max_minutes": float(self.config.get("voice.wake_word.max_minutes", 20) or 20),
                "echo_guard": self._echo_guard_enabled(),
                "echo_guard_cooldown_s": self._echo_cooldown(),
                "stop_reason": self._wake_stop_reason,
            },
            "ready_for_voice_commands": bool(
                tts_status.get("available")
                and stt_status.get("available")
                and recorder_status.get("available")
                and not recorder_status.get("stuck")
            ),
        }
