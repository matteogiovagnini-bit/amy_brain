"""Costruzione dei provider IA e fallback."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.errors import AIError
from ..core.logging_setup import get_logger
from .base import AIProvider
from .offline import OfflineProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatibleProvider

_log = get_logger("ai.factory")


class FallbackProvider(AIProvider):
    """Usa il provider secondario solo se il primario fallisce."""

    def __init__(self, primary: AIProvider, fallback: AIProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.model = primary.model
        self.last_fallback_reason = ""

    def chat(self, messages: List[Dict[str, str]], *, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        try:
            result = self.primary.chat(messages, temperature=temperature, max_tokens=max_tokens)
            self.last_fallback_reason = ""
            return result
        except AIError as exc:
            self.last_fallback_reason = exc.message
            _log.warning("Provider %s non disponibile: %s. Uso %s.", self.primary.name, exc.message, self.fallback.name)
            return self.fallback.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def status(self) -> Dict[str, Any]:
        primary_status = self.primary.status()
        return {
            "provider": self.primary.name,
            "model": self.primary.model,
            "available": bool(primary_status.get("available")),
            "model_installed": primary_status.get("model_installed"),
            "primary": primary_status,
            "fallback": self.fallback.status(),
            "last_fallback_reason": self.last_fallback_reason,
        }


def build_provider(config, *, force_offline: bool = False) -> AIProvider:
    if force_offline:
        return OfflineProvider()
    name = str(config.get("ai.provider", "ollama")).lower()
    timeout = float(config.get("ai.timeout_s", 120))
    max_tokens = int(config.get("ai.max_tokens", 1200))
    temperature = float(config.get("ai.temperature", 0.2))

    if name == "offline":
        primary: AIProvider = OfflineProvider()
    elif name == "openai":
        primary = OpenAICompatibleProvider(
            base_url=str(config.get("ai.openai.base_url", "http://127.0.0.1:8000/v1")),
            model=str(config.get("ai.openai.model", "local-model")),
            api_key_env=str(config.get("ai.openai.api_key_env", "OPENAI_API_KEY")),
            timeout_s=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            require_api_key=bool(config.get("ai.openai.require_api_key", False)),
            allow_remote=bool(config.get("ai.openai.allow_remote", False)),
        )
    else:
        primary = OllamaProvider(
            base_url=str(config.get("ai.base_url", "http://127.0.0.1:11434")),
            model=str(config.get("ai.model", "qwen2.5-coder:14b")),
            timeout_s=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    fallback_name = str(config.get("ai.fallback_provider", "offline")).lower()
    if fallback_name == "offline" and primary.name != "offline":
        return FallbackProvider(primary, OfflineProvider())
    if fallback_name == "ollama" and primary.name != "ollama":
        return FallbackProvider(
            primary,
            OllamaProvider(
                base_url=str(config.get("ai.base_url", "http://127.0.0.1:11434")),
                model=str(config.get("ai.model", "qwen2.5-coder:14b")),
                timeout_s=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
    return primary
