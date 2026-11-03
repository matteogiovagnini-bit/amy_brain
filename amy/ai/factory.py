"""Costruzione dei provider IA e fallback."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.errors import AIError, AIUnavailableError
from ..core.logging_setup import get_logger, redact
from .base import AIProvider
from .offline import OfflineProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatibleProvider
from .presets import get_preset

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
            detail = getattr(exc, "detail", "") or ""
            if detail:
                _log.warning(
                    "Provider %s non disponibile: %s — %s. Uso %s.",
                    self.primary.name,
                    exc.message,
                    redact(detail)[:300],
                    self.fallback.name,
                )
            else:
                _log.warning(
                    "Provider %s non disponibile: %s. Uso %s.",
                    self.primary.name,
                    exc.message,
                    self.fallback.name,
                )
            reply = self.fallback.chat(messages, temperature=temperature, max_tokens=max_tokens)
            # L'interprete offline, quando non capisce, suggerisce Ollama. Se il
            # fallback è scattato per un guasto del provider online, è più utile
            # dire che il servizio non è raggiungibile e invitare a riprovare.
            if isinstance(self.fallback, OfflineProvider) and str(reply).startswith(
                "In modalità offline non ho capito"
            ):
                reply = (
                    "Il provider online non è disponibile in questo momento (%s). "
                    "Posso eseguire comandi semplici su applicazioni, file, web, "
                    "memoria e robot. Riprova tra poco per il dialogo completo."
                    % (exc.message or "servizio non raggiungibile")
                )
            return reply

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


def build_primary(config) -> AIProvider:
    """Costruisce il provider primario scelto nella configurazione.

    I preset online gratuiti richiedono ``ai.online.consent = true``: la
    configurazione viene validata prima, ma il controllo è ripetuto qui perché
    questo modulo può essere usato anche senza passare da ``Config.load``.
    """
    name = str(config.get("ai.provider", "ollama")).lower()
    timeout = float(config.get("ai.timeout_s", 120))
    max_tokens = int(config.get("ai.max_tokens", 1200))
    temperature = float(config.get("ai.temperature", 0.2))

    preset = get_preset(name)
    if preset is not None:
        if not bool(config.get("ai.online.consent", False)):
            raise AIUnavailableError(
                "Provider IA online non autorizzato.",
                detail=(
                    "Imposta ai.online.consent=true dopo aver verificato le condizioni "
                    "gratuite di %s (%s)." % (preset.label, preset.signup_url)
                ),
            )
        model = str(config.get("ai.online.model", "") or preset.model)
        key_env = str(config.get("ai.online.api_key_env", "") or preset.api_key_env)
        return OpenAICompatibleProvider(
            base_url=preset.base_url,
            model=model,
            api_key_env=key_env,
            timeout_s=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            require_api_key=True,
            allow_remote=True,
            name=preset.id,
            preset=preset.as_dict(),
        )

    if name == "offline":
        return OfflineProvider()
    if name == "openai":
        return OpenAICompatibleProvider(
            base_url=str(config.get("ai.openai.base_url", "http://127.0.0.1:8000/v1")),
            model=str(config.get("ai.openai.model", "local-model")),
            api_key_env=str(config.get("ai.openai.api_key_env", "OPENAI_API_KEY")),
            timeout_s=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            require_api_key=bool(config.get("ai.openai.require_api_key", False)),
            allow_remote=bool(config.get("ai.openai.allow_remote", False)),
        )
    return OllamaProvider(
        base_url=str(config.get("ai.base_url", "http://127.0.0.1:11434")),
        model=str(config.get("ai.model", "qwen2.5-coder:14b")),
        timeout_s=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_provider(config, *, force_offline: bool = False) -> AIProvider:
    if force_offline:
        return OfflineProvider()
    primary = build_primary(config)

    fallback_name = str(config.get("ai.fallback_provider", "offline")).lower()
    if fallback_name == "offline" and primary.name != "offline":
        return FallbackProvider(primary, OfflineProvider())
    if fallback_name == "ollama" and primary.name != "ollama":
        return FallbackProvider(
            primary,
            OllamaProvider(
                base_url=str(config.get("ai.base_url", "http://127.0.0.1:11434")),
                model=str(config.get("ai.model", "qwen2.5-coder:14b")),
                timeout_s=float(config.get("ai.timeout_s", 120)),
                temperature=float(config.get("ai.temperature", 0.2)),
                max_tokens=int(config.get("ai.max_tokens", 1200)),
            ),
        )
    return primary
