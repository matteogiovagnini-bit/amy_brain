"""Registrazione audio locale per lo STT."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.errors import VoiceError

_log = logging.getLogger("amy.voice")

_SOUNDDEVICE: Optional[Any] = None

#: Attesa massima oltre la durata richiesta per aprire e leggere il flusso.
#: PortAudio può bloccarsi dentro il HAL di CoreAudio: senza un limite il
#: backend resterebbe appeso per sempre (osservato il 2026-11-01).
_GRACE_SECONDS = 6.0

#: Dopo un blocco non si ritenta subito: il dispositivo è in uno stato
#: rotto e ogni tentativo lascerebbe un altro thread fermo nel HAL.
_STUCK_COOLDOWN_SECONDS = 60.0


class Recorder:
    def __init__(self, engine: str = "ffmpeg", device: str = ":0") -> None:
        self.engine = engine
        self.device = device

    def status(self) -> Dict[str, Any]:
        if self.engine == "sox":
            path = shutil.which("sox")
        else:
            path = shutil.which("ffmpeg")
        return {
            "available": bool(path),
            "engine": self.engine,
            "path": path,
            "device": self.device,
            "nota": "La prima registrazione richiede il permesso Microfono in Impostazioni di Sistema.",
        }

    def record(self, seconds: float = 5.0, *, path: Path = None) -> Path:
        seconds = max(1.0, min(float(seconds), 30.0))
        if path is None:
            handle = tempfile.NamedTemporaryFile(prefix="amy-audio-", suffix=".wav", delete=False)
            handle.close()
            path = Path(handle.name)
        if self.engine == "sox":
            if not shutil.which("sox"):
                raise VoiceError("sox non è installato: impossibile registrare.", detail="Installa sox oppure usa ffmpeg.")
            command = ["sox", "-d", "-c", "1", "-r", "16000", str(path), "trim", "0", str(seconds)]
        else:
            if not shutil.which("ffmpeg"):
                raise VoiceError(
                    "ffmpeg non è installato: impossibile registrare dal microfono.",
                    detail="Installa ffmpeg (per esempio con Homebrew) e concedi il permesso Microfono.",
                )
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                self.device,
                "-t",
                str(seconds),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-y",
                str(path),
            ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=seconds + 20)
        except subprocess.TimeoutExpired as exc:
            raise VoiceError("La registrazione non è terminata in tempo.") from exc
        if process.returncode != 0:
            raise VoiceError(
                "Registrazione non riuscita. Verifica microfono e permessi.",
                detail=process.stderr[-500:],
            )
        if not path.exists() or path.stat().st_size == 0:
            raise VoiceError("La registrazione è vuota.")
        return path


class SoundDeviceRecorder:
    """Registrazione dal microfono con ``sounddevice`` (PortAudio), se installato.

    Scrive un WAV PCM 16 bit mono a 16 kHz con il modulo standard ``wave``:
    nessun file temporaneo intermedio e nessun processo esterno.

    L'apertura del flusso può bloccarsi dentro il HAL di CoreAudio senza
    restituire il controllo (osservato su macOS con due flussi rimasti aperti
    e il permesso Microfono da riconcedere). Per questo la cattura avviene in
    un thread separato con un limite di tempo: oltre il limite la chiamata
    fallisce con un ``VoiceError`` onesto e il registratore resta marcato come
    non rispondente, invece di bloccare backend e dashboard all'infinito.
    """

    def __init__(self, device: str = "", samplerate: int = 16000, timeout: Optional[float] = None) -> None:
        self.device = device
        self.samplerate = int(samplerate)
        self.timeout = float(timeout) if timeout and float(timeout) > 0 else None
        self._stuck_until = 0.0
        self._last_error = ""
        self._busy = threading.Lock()

    @staticmethod
    def module():
        """Restituisce il modulo ``sounddevice`` oppure None se non installato."""
        global _SOUNDDEVICE
        if _SOUNDDEVICE is False:
            return None
        if _SOUNDDEVICE is None:
            try:
                import sounddevice  # type: ignore
            except Exception:  # pragma: no cover - dipende dall'ambiente
                _SOUNDDEVICE = False
                return None
            _SOUNDDEVICE = sounddevice
        return _SOUNDDEVICE

    def _device_arg(self):
        value = str(self.device or "").strip()
        if value.isdigit():
            return int(value)
        return None

    def status(self) -> Dict[str, Any]:
        module = self.module()
        available = module is not None
        name = ""
        if available:
            try:
                info = module.query_devices(kind="input")
                name = str(info.get("name", "") or "")
                available = bool(name)
            except Exception:
                available = False
        stuck = self.is_stuck()
        if available and stuck:
            nota = (
                "Il microfono non ha risposto. Riavvia il servizio audio di macOS "
                "(o il Mac) e riprova; nel frattempo Amy non registra."
            )
        else:
            nota = "La prima registrazione richiede il permesso Microfono in Impostazioni di Sistema."
        return {
            "available": available,
            "engine": "sounddevice",
            "path": "sounddevice" if module is not None else None,
            "device": name or (str(self.device) if self.device else "predefinito"),
            "samplerate": self.samplerate,
            "stuck": stuck,
            "problem": self._last_error,
            "nota": nota,
        }

    def is_stuck(self) -> bool:
        """Vero se l'ultima cattura è rimasta bloccata nel HAL audio."""
        return time.monotonic() < self._stuck_until

    def reset(self) -> None:
        """Dimentica un blocco precedente: serve solo dopo un intervento umano."""
        self._stuck_until = 0.0
        self._last_error = ""

    def _mark_stuck(self, detail: str) -> None:
        self._stuck_until = time.monotonic() + _STUCK_COOLDOWN_SECONDS
        self._last_error = detail
        _log.warning(
            "Microfono non rispondente (%s): sospendo le registrazioni per %.0f s",
            detail,
            _STUCK_COOLDOWN_SECONDS,
        )

    def _capture(self, module: Any, seconds: float) -> bytes:
        frames = bytearray()
        with module.RawInputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            device=self._device_arg(),
        ) as stream:
            remaining = int(seconds * self.samplerate)
            while remaining > 0:
                chunk, _overflowed = stream.read(min(4096, remaining))
                data = bytes(chunk)
                frames.extend(data)
                remaining -= len(data) // 2
        return bytes(frames)

    def record(self, seconds: float = 5.0, *, path: Path = None) -> Path:
        module = self.module()
        if module is None:
            raise VoiceError(
                "sounddevice non è installato: impossibile registrare.",
                detail="Installa sounddevice con pip3 install --user sounddevice.",
            )
        if self.is_stuck():
            raise VoiceError(
                "Il microfono non risponde: nessuna registrazione è stata avviata.",
                detail=self._last_error,
            )
        if not self._busy.acquire(blocking=False):
            raise VoiceError("Una registrazione è già in corso.")
        try:
            seconds = max(1.0, min(float(seconds), 30.0))
            if path is None:
                handle = tempfile.NamedTemporaryFile(prefix="amy-audio-", suffix=".wav", delete=False)
                handle.close()
                path = Path(handle.name)
            limit = self.timeout if self.timeout else seconds + _GRACE_SECONDS
            outcome: Dict[str, Any] = {}

            def capture() -> None:
                try:
                    outcome["frames"] = self._capture(module, seconds)
                except BaseException as exc:  # pragma: no cover - dipende dal HAL
                    outcome["error"] = exc

            worker = threading.Thread(target=capture, name="amy-record", daemon=True)
            worker.start()
            worker.join(limit)
            if worker.is_alive():
                detail = (
                    "PortAudio non ha restituito il controllo entro %.1f s. "
                    "Chiudi le altre app che usano il microfono e riavvia il Mac "
                    "se il problema resta." % limit
                )
                self._mark_stuck(detail)
                try:
                    path.unlink()
                except OSError:
                    pass
                raise VoiceError(
                    "Il microfono non risponde: la registrazione è stata interrotta.",
                    detail=detail,
                )
            error = outcome.get("error")
            if isinstance(error, VoiceError):
                raise error
            if error is not None:
                raise VoiceError(
                    "Registrazione non riuscita. Verifica microfono e permessi.",
                    detail=str(error)[:300],
                )
            frames = outcome.get("frames") or b""
            if not frames:
                raise VoiceError("La registrazione è vuota.")
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.samplerate)
                wav.writeframes(frames)
            self.reset()
            return path
        finally:
            self._busy.release()


def build_recorder(config) -> Any:
    """Sceglie il registratore migliore disponibile.

    ``auto`` preferisce ``sounddevice`` (nessun processo esterno), poi ffmpeg e
    sox. Un motore scelto esplicitamente viene rispettato.
    """
    engine = str(config.get("voice.recorder.engine", "auto") or "auto").lower()
    device = str(config.get("voice.recorder.device", "") or "")
    samplerate = int(config.get("voice.recorder.samplerate", 16000) or 16000)
    if engine in {"sounddevice", "portaudio"}:
        return SoundDeviceRecorder(device, samplerate)
    if engine == "auto":
        candidate = SoundDeviceRecorder(device, samplerate)
        if candidate.status().get("available"):
            return candidate
        engine = "ffmpeg"
    return Recorder(engine, device or ":0")
