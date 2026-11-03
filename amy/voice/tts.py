"""Sintesi vocale tramite il comando nativo ``say`` di macOS."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.errors import VoiceError


class TTS:
    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:  # pragma: no cover - interfaccia
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interfaccia
        raise NotImplementedError

    def is_speaking(self) -> bool:
        return False

    def speech_overlaps(self, start: float, end: float) -> bool:
        """Vero se una sintesi è in corso o è avvenuta nella finestra data.

        Serve al ciclo di wake word per non scambiare la voce di Amy per un
        comando dell'utente (protezione dall'eco).
        """
        return False

    def status(self) -> Dict[str, Any]:
        return {"available": False, "engine": "none"}


class MacSayTTS(TTS):
    """Voce di sistema macOS. Non richiede rete né servizi cloud."""

    MAX_TEXT = 4000

    def __init__(self, voice: str = "Alice", rate: int = 185) -> None:
        self.voice = voice
        self.rate = max(80, min(int(rate), 350))
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        # Intervalli di sintesi: servono a sapere se una registrazione ha
        # catturato la voce di Amy (eco) invece della voce dell'utente.
        self._speech_lock = threading.Lock()
        self._speech_start: Optional[float] = None
        self._speech_end: Optional[float] = None
        # Testo in pronuncia: serve al barge-in per distinguere la voce
        # dell'utente dall'eco della sintesi.
        self._current_text = ""
        # L'elenco delle voci non cambia durante la sessione: `say -v ?` costa
        # alcuni secondi e non va rieseguito a ogni richiesta di stato.
        self._italian_voices: Optional[List[str]] = None

    @staticmethod
    def available() -> bool:
        return shutil.which("say") is not None

    @staticmethod
    def voices() -> List[Dict[str, str]]:
        if not shutil.which("say"):
            return []
        try:
            output = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []
        voices: List[Dict[str, str]] = []
        pattern = re.compile(r"^(?P<name>.+?)\s{2,}(?P<locale>[a-z]{2}_[A-Z]{2})\s+#\s*(?P<sample>.*)$")
        for line in output.splitlines():
            match = pattern.match(line.strip())
            if match:
                voices.append(
                    {
                        "name": match.group("name").strip(),
                        "locale": match.group("locale"),
                        "sample": match.group("sample")[:80],
                    }
                )
        return voices

    @staticmethod
    def block_timeout(text: str) -> float:
        """Tempo massimo di attesa per una sintesi bloccante.

        `say` di norma termina in fretta, ma può restare appeso se il
        dispositivo audio non è disponibile. Il limite è generoso (almeno
        20 secondi e proporzionale al testo) ma finito: nessun chiamante deve
        attendere per sempre.
        """
        return max(20.0, len(text) / 4.0)

    def _clean(self, text: str) -> str:
        value = " ".join(str(text).split())
        if not value:
            raise VoiceError("Non c'è testo da pronunciare.")
        if len(value) > self.MAX_TEXT:
            value = value[: self.MAX_TEXT] + "…"
        return value

    # ------------------------------------------------------- tracciamento eco
    def _mark_speech_start(self) -> None:
        with self._speech_lock:
            self._speech_start = time.monotonic()
            self._speech_end = None

    def _mark_speech_end(self) -> None:
        with self._speech_lock:
            if self._speech_start is not None and self._speech_end is None:
                self._speech_end = time.monotonic()
            self._current_text = ""

    def _watch_speech(self, process: subprocess.Popen) -> None:
        """Segue il processo `say` e chiude l'intervallo di sintesi."""
        try:
            process.wait()
        except Exception:  # pragma: no cover - difensivo
            pass
        finally:
            self._mark_speech_end()

    @property
    def current_text(self) -> str:
        with self._speech_lock:
            return self._current_text if self.is_speaking() else ""

    def speech_overlaps(self, start: float, end: float) -> bool:
        if self.is_speaking():
            return True
        with self._speech_lock:
            first = self._speech_start
            last = self._speech_end
        if first is None or last is None:
            return False
        return first < end and last > start

    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        if not self.available():
            raise VoiceError("Il comando 'say' di macOS non è disponibile.")
        value = self._clean(text)
        self.stop()
        with self._speech_lock:
            self._current_text = value
        with self._lock:
            try:
                process = subprocess.Popen(
                    ["say", "-v", self.voice, "-r", str(self.rate), value],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except OSError as exc:
                raise VoiceError("Impossibile avviare la sintesi vocale.", detail=str(exc)) from exc
            self._process = process
        self._mark_speech_start()
        if block:
            try:
                _, stderr = process.communicate(timeout=self.block_timeout(value))
            except subprocess.TimeoutExpired:
                # `say` può restare appeso se il dispositivo audio non è
                # disponibile. Non deve bloccare il chiamante all'infinito:
                # il saluto di avvio e l'endpoint HTTP usano `block=True`.
                process.kill()
                try:
                    _, _ = process.communicate(timeout=5)
                except Exception:  # pragma: no cover - difensivo
                    pass
                with self._lock:
                    self._process = None
                self._mark_speech_end()
                return {
                    "spoken": False,
                    "reason": "La sintesi vocale non si è conclusa entro il tempo previsto.",
                    "voice": self.voice,
                    "chars": len(value),
                }
            with self._lock:
                self._process = None
            self._mark_speech_end()
            if process.returncode not in (0, -15):
                raise VoiceError("La sintesi vocale è terminata con errore.", detail=(stderr or "")[:300])
        else:
            # La sintesi non bloccante viene seguita in background: il ciclo di
            # wake word deve sapere quando Amy smette di parlare.
            threading.Thread(
                target=self._watch_speech,
                args=(process,),
                name="amy-tts-watch",
                daemon=True,
            ).start()
        return {
            "spoken": True,
            "voice": self.voice,
            "rate": self.rate,
            "chars": len(value),
            "pid": process.pid,
        }

    def to_file(self, text: str, path: Path) -> Path:
        """Sintesi su file AIFF, utile per test senza altoparlanti."""
        if not self.available():
            raise VoiceError("Il comando 'say' di macOS non è disponibile.")
        value = self._clean(text)
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.run(
            ["say", "-v", self.voice, "-r", str(self.rate), "-o", str(path), value],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if process.returncode != 0:
            raise VoiceError("Impossibile generare l'audio.", detail=process.stderr[:300])
        return path

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        self._mark_speech_end()

    def is_speaking(self) -> bool:
        with self._lock:
            alive = bool(self._process and self._process.poll() is None)
        if not alive:
            # Il processo è finito: chiudi l'intervallo di sintesi anche se il
            # thread di sorveglianza non ha ancora ruotato.
            self._mark_speech_end()
        return alive

    def italian_voices(self) -> List[str]:
        """Voci italiane disponibili, calcolate una sola volta per processo."""
        if self._italian_voices is None:
            self._italian_voices = [v["name"] for v in self.voices() if v["locale"] == "it_IT"]
        return self._italian_voices

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available(),
            "engine": "say",
            "voice": self.voice,
            "rate": self.rate,
            "italian_voices": self.italian_voices(),
        }


class NullTTS(TTS):
    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        return {"spoken": False, "engine": "none", "reason": "sintesi vocale disabilitata"}

    def stop(self) -> None:
        return None
