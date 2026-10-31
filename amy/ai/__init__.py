"""Motori IA intercambiabili."""

from .base import AIProvider, ChatMessage
from .factory import FallbackProvider, build_provider
from .offline import OfflineProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatibleProvider

__all__ = [
    "AIProvider",
    "ChatMessage",
    "FallbackProvider",
    "build_provider",
    "OfflineProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
]
