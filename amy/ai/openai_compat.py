"""Provider per endpoint compatibili con l'API OpenAI."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..core.config import get_secret, is_local_endpoint
from ..core.errors import AIError, AITimeoutError, AIUnavailableError
from .base import AIProvider, normalize_messages


class OpenAICompatibleProvider(AIProvider):
    """Endpoint compatibile OpenAI, pensato per server locali gratuiti.

    Non è un requisito del progetto e non è il provider predefinito. Un endpoint
    pubblico è accettato solo con ``allow_remote=True`` esplicito, perché potrebbe
    richiedere pagamenti obbligatori. Amy non sceglie mai un servizio a pagamento
    come fallback.
    """

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000/v1",
        model: str = "local-model",
        api_key_env: str = "OPENAI_API_KEY",
        api_key: Optional[str] = None,
        timeout_s: float = 90.0,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        require_api_key: bool = False,
        allow_remote: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.require_api_key = bool(require_api_key)
        self.allow_remote = bool(allow_remote)
        if not self.allow_remote and not is_local_endpoint(self.base_url):
            raise AIUnavailableError(
                "Endpoint IA remoto non autorizzato.",
                detail=(
                    "Amy accetta solo servizi gratuiti. %s non è locale: verifica le "
                    "condizioni economiche e imposta ai.openai.allow_remote=true solo "
                    "se il servizio è realmente gratuito." % self.base_url
                ),
            )

    def _key(self) -> Optional[str]:
        key = self.api_key or get_secret(self.api_key_env)
        if not key and self.require_api_key:
            raise AIUnavailableError(
                "Chiave API non configurata per il provider OpenAI-compatibile.",
                detail="Imposta la variabile d'ambiente %s oppure ~/.amy/secrets.json (chmod 600)." % self.api_key_env,
            )
        return key

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
            "temperature": self.temperature if temperature is None else float(temperature),
            "max_tokens": self.max_tokens if max_tokens is None else int(max_tokens),
            "stream": False,
        }
        key = self._key()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code in {401, 403}:
                raise AIUnavailableError(
                    "Il provider remoto ha rifiutato la chiave API.",
                    detail=body,
                ) from exc
            if exc.code == 429:
                raise AIError("Limite di utilizzo del provider raggiunto. Riprova più tardi.", detail=body) from exc
            raise AIError("Il provider remoto ha risposto con errore HTTP %s." % exc.code, detail=body) from exc
        except socket.timeout as exc:
            raise AITimeoutError("Il provider remoto non ha risposto in tempo.") from exc
        except urllib.error.URLError as exc:
            raise AIUnavailableError("Provider remoto non raggiungibile.", detail=str(exc.reason)[:300]) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIError("Risposta non valida dal provider remoto.", detail=str(exc)) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("La risposta del provider non contiene testo.", detail=str(exc)) from exc
        if not isinstance(content, str) or not content.strip():
            raise AIError("Il provider remoto ha restituito una risposta vuota.")
        return content.strip()

    def status(self) -> Dict[str, Any]:
        configured = bool(self.api_key or get_secret(self.api_key_env))
        local = is_local_endpoint(self.base_url)
        return {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "available": configured or not self.require_api_key,
            "api_key_env": self.api_key_env,
            "api_key_configured": configured,
            "local_endpoint": local,
            "remote_allowed": self.allow_remote,
            "note": (
                "Endpoint locale: nessun costo previsto dal progetto."
                if local
                else "Endpoint remoto autorizzato esplicitamente: verifica che sia gratuito."
            ),
        }
