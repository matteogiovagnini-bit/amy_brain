"""Riconoscimento vocale locale (opzionale).

Amy non impone un motore STT. Sono supportati:
- ``faster-whisper`` (Python, locale) se installato;
- CLI OpenAI Whisper (``whisper``);
- CLI whisper.cpp (``whisper-cli``) con modello GGML.

Se nessun motore è disponibile, la modalità testuale resta pienamente
funzionante e il comando ``amy doctor`` spiega cosa installare.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.errors import VoiceError


class STT:
    def transcribe(self, audio_path: Path) -> str:  # pragma: no cover - interfaccia
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        return {"available": False, "engine": "none"}

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))

    def warm(self) -> None:
        """Precarica il modello in memoria. Le implementazioni possono ignorarlo."""
        return None


class FasterWhisperSTT(STT):
    def __init__(
        self,
        model: str = "base",
        language: str = "it",
        download_root: Optional[str] = None,
    ) -> None:
        self.model_name = model or "base"
        self.language = language
        self.download_root = download_root
        self._model = None

    def installed(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore

            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
                download_root=self.download_root,
            )
        return self._model

    def warm(self) -> None:
        if self.installed():
            self._load()

    def transcribe(self, audio_path: Path) -> str:
        if not self.installed():
            raise VoiceError(
                "faster-whisper non è installato.",
                detail="Installa con: pip3 install --user faster-whisper",
            )
        model = self._load()
        segments, _ = model.transcribe(str(audio_path), language=self.language, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.installed(),
            "engine": "faster-whisper",
            "model": self.model_name,
            "model_present": self.installed(),
            "note": "Trascrizione locale su CPU; il modello viene scaricato la prima volta.",
        }


class WhisperCliSTT(STT):
    def __init__(self, command: str = "whisper", model: str = "base", language: str = "it") -> None:
        self.command = command
        self.model = model or "base"
        self.language = language

    def status(self) -> Dict[str, Any]:
        path = shutil.which(self.command)
        return {
            "available": bool(path),
            "engine": self.command,
            "path": path,
            "model": self.model,
        }

    def transcribe(self, audio_path: Path) -> str:
        if not shutil.which(self.command):
            raise VoiceError("Il comando STT non è installato: %s" % self.command)
        with tempfile.TemporaryDirectory(prefix="amy-stt-") as tmp:
            process = subprocess.run(
                [
                    self.command,
                    str(audio_path),
                    "--model",
                    self.model,
                    "--language",
                    self.language,
                    "--output_format",
                    "txt",
                    "--output_dir",
                    tmp,
                    "--fp16",
                    "False",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if process.returncode != 0:
                raise VoiceError(
                    "Trascrizione non riuscita.",
                    detail=process.stderr[-500:],
                )
            output = Path(tmp) / (Path(audio_path).stem + ".txt")
            if not output.exists():
                raise VoiceError("Il motore STT non ha prodotto il file di trascrizione.")
            return output.read_text(encoding="utf-8", errors="replace").strip()


class WhisperCppSTT(STT):
    def __init__(self, command: str = "whisper-cli", model: str = "", language: str = "it") -> None:
        self.command = command
        self.model = model
        self.language = language

    def status(self) -> Dict[str, Any]:
        path = shutil.which(self.command)
        model_ok = bool(self.model and Path(self.model).expanduser().exists())
        return {
            "available": bool(path and model_ok),
            "engine": "whisper.cpp",
            "path": path,
            "model": self.model,
            "model_present": model_ok,
        }

    def transcribe(self, audio_path: Path) -> str:
        status = self.status()
        if not status["available"]:
            raise VoiceError(
                "whisper.cpp non è configurato (comando o modello mancante).",
                detail="Configura voice.stt.command e voice.stt.model in ~/.amy/config.json",
            )
        with tempfile.TemporaryDirectory(prefix="amy-stt-") as tmp:
            base = Path(tmp) / "trascrizione"
            process = subprocess.run(
                [
                    self.command,
                    "-m",
                    str(Path(self.model).expanduser()),
                    "-f",
                    str(audio_path),
                    "-l",
                    self.language,
                    "-nt",
                    "-otxt",
                    "-of",
                    str(base),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if process.returncode != 0:
                raise VoiceError("Trascrizione non riuscita.", detail=process.stderr[-500:])
            output = base.with_suffix(".txt")
            if not output.exists():
                raise VoiceError("Il motore STT non ha prodotto il file di trascrizione.")
            return output.read_text(encoding="utf-8", errors="replace").strip()


def build_stt(config) -> STT:
    engine = str(config.get("voice.stt.engine", "auto") or "auto").lower()
    language = str(config.get("voice.stt.language", "it"))
    model = str(config.get("voice.stt.model", "") or "")
    download_root = str(config.get("voice.stt.download_root", "~/.amy/models/whisper"))
    if engine == "whisper-cli":
        command = str(config.get("voice.stt.command", "whisper-cli"))
        model_ok = bool(model and Path(model).expanduser().exists())
        if not (shutil.which(command) and model_ok) and importlib.util.find_spec("faster_whisper"):
            engine = "faster-whisper"  # ripiego locale, stesso vincolo di gratuità
    if engine == "auto":
        engine = "faster-whisper" if importlib.util.find_spec("faster_whisper") else "whisper-cli"
    if engine == "faster-whisper":
        return FasterWhisperSTT(model or "base", language, str(Path(download_root).expanduser()))
    if engine == "whisper":
        return WhisperCliSTT(str(config.get("voice.stt.command", "whisper")), str(config.get("voice.stt.model", "base")), language)
    return WhisperCppSTT(
        str(config.get("voice.stt.command", "whisper-cli")),
        str(config.get("voice.stt.model", "")),
        language,
    )
