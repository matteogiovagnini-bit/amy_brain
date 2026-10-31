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

    def _clean(self, text: str) -> str:
        value = " ".join(str(text).split())
        if not value:
            raise VoiceError("Non c'è testo da pronunciare.")
        if len(value) > self.MAX_TEXT:
            value = value[: self.MAX_TEXT] + "…"
        return value

    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        if not self.available():
            raise VoiceError("Il comando 'say' di macOS non è disponibile.")
        value = self._clean(text)
        self.stop()
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
        if block:
            _, stderr = process.communicate()
            with self._lock:
                self._process = None
            if process.returncode not in (0, -15):
                raise VoiceError("La sintesi vocale è terminata con errore.", detail=(stderr or "")[:300])
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

    def is_speaking(self) -> bool:
        with self._lock:
            return bool(self._process and self._process.poll() is None)

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
