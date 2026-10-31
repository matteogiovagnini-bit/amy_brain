"""Voce di Amy: sintesi, riconoscimento, wake word e servizio."""

from .tts import MacSayTTS, NullTTS, TTS
from .stt import build_stt, FasterWhisperSTT, WhisperCliSTT, WhisperCppSTT
from .recorder import Recorder
from .wakeword import WakeWordDetector, normalize
from .service import VoiceService

__all__ = [
    "MacSayTTS",
    "NullTTS",
    "TTS",
    "build_stt",
    "FasterWhisperSTT",
    "WhisperCliSTT",
    "WhisperCppSTT",
    "Recorder",
    "WakeWordDetector",
    "normalize",
    "VoiceService",
]
