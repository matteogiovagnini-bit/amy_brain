"""Provider per endpoint compatibili con l'API OpenAI."""

from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .. import __version__
from ..core.config import get_secret, is_local_endpoint
from ..core.errors import AIError, AITimeoutError, AIUnavailableError
from ..core.logging_setup import get_logger
from .base import AIProvider, normalize_messages

_log = get_logger("ai.openai")

# Alcuni servizi online (Cloudflare) rifiutano con HTTP 403 il User-Agent
# predefinito di urllib. Dichiararsi esplicitamente evita il blocco e rende
# riconoscibili le richieste di Amy nei log del servizio.
_USER_AGENT = "AmyBrain/%s" % __version__

# Attesa massima accettata prima di ritentare una richiesta bloccata dal limite
# gratuito. Oltre questa soglia è meglio il fallback locale che una chat ferma.
_MAX_RETRY_WAIT_S = 20.0


class OpenAICompatibleProvider(AIProvider):
    """Endpoint compatibile OpenAI, locale oppure online gratuito.

    Non è un requisito del progetto e non è il provider predefinito. Un endpoint
    pubblico è accettato solo con ``allow_remote=True`` esplicito, perché potrebbe
    richiedere pagamenti obbligatori. Amy non sceglie mai un servizio a pagamento
    come fallback.

    I preset verificati (vedi ``presets.py``) impostano ``allow_remote`` dopo una
    scelta esplicita dell'utente e portano con sé le condizioni del piano gratuito,
    così l'interfaccia può dichiararle senza inventare nulla.
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
        name: Optional[str] = None,
        preset: Optional[Dict[str, Any]] = None,
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
        self.name = name or self.name
        self.preset = dict(preset) if preset else {}
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
        headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
        if key:
            headers["Authorization"] = "Bearer " + key
        body = json.dumps(payload).encode("utf-8")
        # Una risposta vuota è spesso transitoria: un secondo tentativo evita di
        # scivolare nel fallback offline per un singolo pacchetto andato male.
        for attempt in (1, 2):
            request = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=body,
                headers=headers,
                method="POST",
            )
            data = self._post_with_retry(request)
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise AIError("La risposta del provider non contiene testo.", detail=str(exc)) from exc
            if isinstance(content, str) and content.strip():
                return content.strip()
            if attempt == 1:
                _log.info("Risposta vuota dal provider: riprovo una volta.")
                time.sleep(0.5)
        raise AIError("Il provider remoto ha restituito una risposta vuota.")

    @staticmethod
    def _retry_wait_seconds(error: urllib.error.HTTPError, body: str = "") -> float:
        """Legge l'attesa consigliata dal servizio, senza fidarsi di valori enormi.

        Groq indica l'attesa nel corpo JSON («try again in 6.3s»), non sempre
        nell'header ``Retry-After``: ignorarlo faceva scattare il fallback
        offline dopo appena 2 secondi.
        """
        candidates = []
        try:
            raw = error.headers.get("Retry-After", "") if error.headers else ""
        except AttributeError:
            raw = ""
        try:
            candidates.append(float(str(raw).strip()))
        except (TypeError, ValueError):
            pass
        match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s)", body or "", re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if match.group(2).lower() == "ms":
                value /= 1000.0
            candidates.append(value)
        if not candidates:
            return 2.0
        return max(0.0, min(max(candidates), _MAX_RETRY_WAIT_S))

    def _post_with_retry(self, request: urllib.request.Request) -> Dict[str, Any]:
        """Esegue la richiesta, ritentando una volta se il limite è per minuto.

        I piani gratuiti hanno un tetto di token al minuto: due messaggi ravvicinati
        possono superarlo. Un solo tentativo con l'attesa indicata dal servizio evita
        di scivolare subito nel fallback, senza mascherare un limite giornaliero.
        """
        for attempt in (1, 2, 3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in {401, 403}:
                    raise AIUnavailableError(
                        "Il provider remoto ha rifiutato la chiave API.",
                        detail=body,
                    ) from exc
                if exc.code == 429:
                    if attempt < 3:
                        wait = self._retry_wait_seconds(exc, body)
                        _log.info(
                            "Limite del provider raggiunto: attendo %.1f s e riprovo (%d/3).",
                            wait,
                            attempt,
                        )
                        time.sleep(wait)
                        continue
                    raise AIError(
                        "Limite di utilizzo del provider raggiunto. Riprova più tardi.",
                        detail=body,
                    ) from exc
                raise AIError(
                    "Il provider remoto ha risposto con errore HTTP %s." % exc.code,
                    detail=body,
                ) from exc
            except socket.timeout as exc:
                raise AITimeoutError("Il provider remoto non ha risposto in tempo.") from exc
            except urllib.error.URLError as exc:
                raise AIUnavailableError("Provider remoto non raggiungibile.", detail=str(exc.reason)[:300]) from exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AIError("Risposta non valida dal provider remoto.", detail=str(exc)) from exc
        raise AIError("Limite di utilizzo del provider raggiunto. Riprova più tardi.")

    def check_remote(self) -> Dict[str, Any]:
        """Verifica chiave e modello con una richiesta leggera a ``/models``.

        Non consuma token di conversazione. Va usata dal doctor e dai test, non
        dal polling della dashboard, per non sprecare il limite gratuito.
        """
        if is_local_endpoint(self.base_url):
            return {"checked": False, "reason": "endpoint locale"}
        try:
            key = self._key()
        except AIUnavailableError as exc:
            return {"checked": True, "key_valid": False, "detail": exc.message}
        if not key:
            return {"checked": True, "key_valid": False, "detail": "chiave API assente"}
        request = urllib.request.Request(
            self.base_url + "/models",
            headers={"Authorization": "Bearer " + key, "User-Agent": _USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_s, 20.0)) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                return {"checked": True, "key_valid": False, "detail": "chiave rifiutata (HTTP %s)" % exc.code}
            return {"checked": True, "key_valid": False, "detail": "HTTP %s" % exc.code}
        except (socket.timeout, urllib.error.URLError, OSError) as exc:
            return {"checked": True, "key_valid": False, "detail": "non raggiungibile: %s" % str(exc)[:200]}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"checked": True, "key_valid": False, "detail": "risposta non valida: %s" % exc}
        models = []
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            models = [str(item.get("id")) for item in data["data"] if isinstance(item, dict)]
        return {
            "checked": True,
            "key_valid": True,
            "model_available": self.model in models,
            "models_count": len(models),
            "detail": "chiave valida",
        }

    def status(self) -> Dict[str, Any]:
        configured = bool(self.api_key or get_secret(self.api_key_env))
        local = is_local_endpoint(self.base_url)
        if local:
            note = "Endpoint locale: nessun costo previsto dal progetto."
        elif self.preset:
            note = "Servizio online gratuito scelto esplicitamente: %s" % self.preset.get(
                "free_terms", "verifica le condizioni del piano gratuito."
            )
        else:
            note = "Endpoint remoto autorizzato esplicitamente: verifica che sia gratuito."
        if not local and self.require_api_key and not configured:
            note = "Chiave API non configurata: imposta %s." % self.api_key_env
        status: Dict[str, Any] = {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "available": configured or not self.require_api_key,
            "api_key_env": self.api_key_env,
            "api_key_configured": configured,
            "local_endpoint": local,
            "remote_allowed": self.allow_remote,
            "requires_api_key": self.require_api_key,
            "note": note,
        }
        if self.preset:
            status["preset"] = self.preset
            status["free_tier"] = True
            status["data_leaves_device"] = not local
        return status
