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
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.errors import VoiceError

#: Prompt iniziale per faster-whisper: orienta il decoder verso i comandi
#: italiani e riduce gli errori su frasi brevi («apri mail»).
DEFAULT_INITIAL_PROMPT = (
    "Comandi in italiano per Amy: apri mail, che ore sono, accendi la luce."
)


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
        initial_prompt: str = "",
    ) -> None:
        self.model_name = model or "base"
        self.language = language
        self.download_root = download_root
        self.initial_prompt = initial_prompt
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
        options = {
            "language": self.language,
            "vad_filter": True,
            "beam_size": 5,
            # Con frasi brevi il contesto precedente può produrre allucinazioni.
            "condition_on_previous_text": False,
        }
        if self.initial_prompt:
            # Biasa il decoder verso i comandi italiani: senza questo, «apri
            # mail» diventa «apre i mail» e «Amy» può sparire.
            options["initial_prompt"] = self.initial_prompt
        segments, _ = model.transcribe(str(audio_path), **options)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.installed(),
            "engine": "faster-whisper",
            "model": self.model_name,
            "model_present": self.installed(),
            "note": "Trascrizione locale su CPU; il modello viene scaricato la prima volta.",
        }


class VoskSTT(STT):
    """Riconoscimento offline con Vosk, incluso il modo grammar per la wake word."""

    def __init__(self, model_path: str, language: str = "it") -> None:
        self.model_path = str(Path(model_path).expanduser())
        self.language = language
        self._model = None

    def installed(self) -> bool:
        return importlib.util.find_spec("vosk") is not None

    def model_present(self) -> bool:
        return Path(self.model_path).is_dir()

    def _load(self):
        if self._model is None:
            if not self.installed():
                raise VoiceError(
                    "Vosk non è installato.",
                    detail="Installa con: python3 -m pip install --user vosk",
                )
            if not self.model_present():
                raise VoiceError(
                    "Modello Vosk non trovato.",
                    detail=self.model_path,
                )
            import vosk  # type: ignore

            self._model = vosk.Model(self.model_path)
        return self._model

    def warm(self) -> None:
        if self.installed() and self.model_present():
            self._load()

    @staticmethod
    def _pcm_16k(audio_path: Path) -> bytes:
        """Decodifica qualunque formato supportato da PyAV in PCM 16 kHz mono."""
        try:
            import av  # type: ignore
        except Exception:
            av = None
        if av is not None:
            chunks = []
            container = av.open(str(audio_path))
            try:
                stream = container.streams.audio[0]
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in container.decode(stream):
                    for out in resampler.resample(frame):
                        chunks.append(out.to_ndarray().tobytes())
                for out in resampler.resample(None):
                    chunks.append(out.to_ndarray().tobytes())
            finally:
                container.close()
            return b"".join(chunks)
        with wave.open(str(audio_path), "rb") as wav:
            if wav.getframerate() != 16000 or wav.getnchannels() != 1:
                raise VoiceError("Il file audio per Vosk deve essere WAV 16 kHz mono.")
            return wav.readframes(wav.getnframes())

    def _recognize(self, audio_path: Path, grammar: Optional[str] = None) -> str:
        if not self.installed():
            raise VoiceError(
                "Vosk non è installato.",
                detail="Installa con: python3 -m pip install --user vosk",
            )
        import vosk  # type: ignore

        model = self._load()
        recognizer = (
            vosk.KaldiRecognizer(model, 16000, grammar)
            if grammar
            else vosk.KaldiRecognizer(model, 16000)
        )
        pcm = self._pcm_16k(audio_path)
        step = 8000  # 0,5 s
        for index in range(0, len(pcm), step):
            recognizer.AcceptWaveform(pcm[index:index + step])
        try:
            return str(json.loads(recognizer.FinalResult()).get("text", "")).strip()
        except (ValueError, AttributeError):
            return ""

    def transcribe(self, audio_path: Path) -> str:
        return self._recognize(audio_path)

    def transcribe_grammar(self, audio_path: Path, grammar: list) -> str:
        text = self._recognize(audio_path, json.dumps(grammar, ensure_ascii=False))
        # Vosk usa [unk] per l'audio fuori grammatica: non è testo utile.
        return " ".join(text.replace("[unk]", " ").split())

    def status(self) -> Dict[str, Any]:
        installed = self.installed()
        present = self.model_present()
        return {
            "available": bool(installed and present),
            "engine": "vosk",
            "model": self.model_path,
            "model_present": present,
            "installed": installed,
            "note": "Riconoscimento offline Vosk; nessun modello cloud.",
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
    if engine == "vosk":
        return VoskSTT(
            str(config.get("voice.stt.vosk_model", "~/.amy/models/vosk/vosk-model-small-it-0.22")),
            language,
        )
    if engine == "faster-whisper":
        prompt = str(config.get("voice.stt.initial_prompt", DEFAULT_INITIAL_PROMPT) or "")
        return FasterWhisperSTT(
            model or "base",
            language,
            str(Path(download_root).expanduser()),
            initial_prompt=prompt,
        )
    if engine == "whisper":
        return WhisperCliSTT(str(config.get("voice.stt.command", "whisper")), str(config.get("voice.stt.model", "base")), language)
    return WhisperCppSTT(
        str(config.get("voice.stt.command", "whisper-cli")),
        str(config.get("voice.stt.model", "")),
        language,
    )
