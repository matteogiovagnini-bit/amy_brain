"""Provider per modelli locali serviti da Ollama."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..core.errors import AIError, AITimeoutError, AIUnavailableError
from .base import AIProvider, normalize_messages


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5-coder:14b",
        timeout_s: float = 120.0,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = float(timeout_s)
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)

    def _post(self, path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 404:
                raise AIUnavailableError(
                    "Il modello richiesto non è disponibile in Ollama.",
                    detail="%s — %s" % (self.model, body),
                ) from exc
            raise AIError("Ollama ha risposto con errore HTTP %s." % exc.code, detail=body) from exc
        except socket.timeout as exc:
            raise AITimeoutError(
                "Il modello locale non ha risposto entro %.0f secondi." % self.timeout_s
            ) from exc
        except urllib.error.URLError as exc:
            raise AIUnavailableError(
                "Ollama non è raggiungibile su %s." % self.base_url,
                detail="Avvia Ollama con 'ollama serve' e verifica il modello '%s'." % self.model,
            ) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIError("Risposta non valida da Ollama.", detail=str(exc)) from exc

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": normalize_messages(messages),
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else float(temperature),
                "num_predict": self.max_tokens if max_tokens is None else int(max_tokens),
            },
        }
        data = self._post("/api/chat", payload, timeout=self.timeout_s + 5)
        message = data.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIError("Ollama ha restituito una risposta vuota.")
        return content.strip()

    def _models(self) -> List[str]:
        request = urllib.request.Request(self.base_url + "/api/tags")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            return []
        return [str(model.get("name", "")) for model in data.get("models", []) if model.get("name")]

    def status(self) -> Dict[str, Any]:
        models = self._models()
        available = bool(models)
        return {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "available": available,
            "model_installed": any(
                name == self.model or name.startswith(self.model + ":") for name in models
            ),
            "models": models[:20],
        }
