"""Registrazione audio locale per lo STT."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from ..core.errors import VoiceError


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
