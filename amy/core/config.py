"""Caricamento e gestione della configurazione di Amy.

Regole:
- la configurazione vive fuori dal repository (``~/.amy/config.json``);
- i segreti non stanno nella configurazione: si leggono da variabili
  d'ambiente o da ``~/.amy/secrets.json`` con permessi ``0600``;
- i valori predefiniti sono sicuri e funzionano senza dipendenze esterne;
- l'ambiente può sovrascrivere i valori più importanti.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .errors import ConfigError

DEFAULT_CONFIG: Dict[str, Any] = {
    "assistant": {
        "name": "Amy",
        "user_name": "",
        "language": "it-IT",
    },
    "ai": {
        "provider": "ollama",
        "model": "qwen2.5-coder:14b",
        "base_url": "http://127.0.0.1:11434",
        "timeout_s": 120,
        "temperature": 0.2,
        "max_tokens": 1200,
        "fallback_provider": "offline",
        "max_tool_steps": 4,
        "openai": {
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "local-model",
            "api_key_env": "OPENAI_API_KEY",
            "require_api_key": False,
            "allow_remote": False,
        },
        # Provider online gratuiti: spenti per impostazione predefinita.
        # `consent` è la conferma esplicita che la conversazione lascia il Mac.
        "online": {
            "model": "",
            "api_key_env": "",
            "consent": False,
        },
    },
    "memory": {
        "db_path": "~/.amy/amy.db",
        "max_history_messages": 24,
        "max_facts_in_prompt": 40,
        "retention_days": 365,
    },
    "security": {
        "auto_approve_levels": ["A"],
        "auto_approve_tools": [],
        "allowed_roots": [
            "~/Progetti",
            "~/Documents",
            "~/Desktop",
            "~/Downloads",
        ],
        "max_file_bytes": 1048576,
        "shell_timeout_s": 20,
        "confirmation_ttl_s": 300,
        "audit_path": "~/.amy/audit.jsonl",
        "backup_dir": "~/.amy/backups",
    },
    "voice": {
        "enabled": False,
        "startup_greeting": True,
        "startup_greeting_text": "Amy è attiva e operativa.",
        "tts": {
            "engine": "say",
            "voice": "Alice",
            "rate": 185,
        },
        "stt": {
            "engine": "auto",
            "command": "whisper-cli",
            "model": "",
            "language": "it",
            "download_root": "~/.amy/models/whisper",
            # Orienta il decoder verso i comandi italiani. Vuoto = nessun prompt.
            "initial_prompt": "Comandi in italiano per Amy: apri mail, che ore sono, accendi la luce.",
        },
        "wake_word": {
            # L'utente ha richiesto l'avvio automatico dell'ascolto continuo.
            # Resta disattivabile con `enabled = false` o `start_on_launch = false`.
            "enabled": True,
            "start_on_launch": True,
            "phrase": "amy",
            "sensitivity": 0.5,
            "max_minutes": 20,
            # Half-duplex: il microfono resta chiuso mentre Amy parla, così
            # la sua voce non viene scambiata per un comando dell'utente.
            "echo_guard": True,
            "echo_guard_cooldown_s": 0.8,
        },
        "recorder": {
            "engine": "auto",
            "device": "",
            "samplerate": 16000,
            "seconds": 5,
        },
    },
    "robot": {
        "transport": "simulated",
        "host": "amy-pi.local",
        "port": 1883,
        "username": "amy-pi",
        "password_env": "AMY_MQTT_PASSWORD",
        "tls": False,
        "timeout_s": 3.0,
        "simulator": {
            "battery_pct": 87,
            "watchdog_timeout_s": 5.0,
        },
    },
    "ui": {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": False,
        "allow_remote": False,
    },
    "logging": {
        "level": "INFO",
        "file": "~/.amy/amy.log",
        "max_bytes": 2000000,
        "backup_count": 3,
    },
}

# Variabili d'ambiente supportate esplicitamente.
ENV_OVERRIDES = {
    "AMY_AI_PROVIDER": "ai.provider",
    "AMY_AI_MODEL": "ai.model",
    "AMY_AI_BASE_URL": "ai.base_url",
    "AMY_ROBOT_TRANSPORT": "robot.transport",
    "AMY_ROBOT_HOST": "robot.host",
    "AMY_ROBOT_PORT": "robot.port",
    "AMY_LOG_LEVEL": "logging.level",
    "AMY_UI_PORT": "ui.port",
}


def amy_home() -> Path:
    """Cartella dati personale di Amy (non il repository)."""
    return Path(os.environ.get("AMY_HOME", str(Path.home() / ".amy"))).expanduser()


def default_config_path() -> Path:
    return Path(os.environ.get("AMY_CONFIG", str(amy_home() / "config.json"))).expanduser()


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _set_dotted(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _coerce_env_value(raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "si", "sì", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(
                "La variabile d'ambiente deve essere un numero intero.",
                detail=str(exc),
            ) from exc
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(
                "La variabile d'ambiente deve essere un numero.",
                detail=str(exc),
            ) from exc
    return raw


def is_local_endpoint(base_url: str) -> bool:
    """True se l'endpoint è locale o sulla rete privata.

    Il progetto accetta solo servizi gratuiti. Un endpoint compatibile OpenAI su
    loopback, rete privata o dominio ``.local`` è considerato locale; un host
    pubblico richiede un consenso esplicito perché potrebbe essere a pagamento.
    Non viene eseguita alcuna risoluzione DNS qui: un nome pubblico resta pubblico.
    """
    raw = str(base_url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


class Config:
    """Configurazione immutabile per convenzione, ricaricabile esplicitamente."""

    def __init__(self, data: Dict[str, Any], path: Optional[Path] = None) -> None:
        self.data = data
        self.path = path or default_config_path()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        config_path = Path(path).expanduser() if path else default_config_path()
        data = copy.deepcopy(DEFAULT_CONFIG)

        if config_path.exists():
            try:
                with config_path.open("r", encoding="utf-8") as handle:
                    user_data = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError(
                    "Impossibile leggere la configurazione di Amy.",
                    detail="%s: %s" % (config_path, exc),
                ) from exc
            if not isinstance(user_data, dict):
                raise ConfigError(
                    "La configurazione deve essere un oggetto JSON.",
                    detail=str(config_path),
                )
            data = _deep_merge(data, user_data)

        for env_name, dotted in ENV_OVERRIDES.items():
            raw = os.environ.get(env_name)
            if raw is None or raw == "":
                continue
            current = cls.get_from(data, dotted)
            _set_dotted(data, dotted, _coerce_env_value(raw, current))

        config = cls(data, config_path)
        config.validate()
        return config

    @staticmethod
    def get_from(data: Dict[str, Any], dotted: str, default: Any = None) -> Any:
        node: Any = data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def get(self, dotted: str, default: Any = None) -> Any:
        return self.get_from(self.data, dotted, default)

    def require_str(self, dotted: str) -> str:
        value = self.get(dotted)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("Configurazione mancante o non valida: %s" % dotted)
        return value.strip()

    def validate(self) -> None:
        # Import locale: `amy.ai` importa a sua volta la configurazione, quindi un
        # import in testa al modulo creerebbe un ciclo.
        from ..ai.presets import get_preset, preset_names

        provider = self.get("ai.provider")
        allowed_providers = {"ollama", "openai", "offline"} | set(preset_names())
        if provider not in allowed_providers:
            raise ConfigError(
                "Provider IA non supportato: %s" % provider,
                detail="Valori ammessi: %s" % ", ".join(sorted(allowed_providers)),
            )
        fallback = self.get("ai.fallback_provider", "offline")
        if fallback not in {"ollama", "offline"}:
            raise ConfigError(
                "Fallback IA non supportato: %s" % fallback,
                detail=(
                    "Valori ammessi: ollama, offline. Il fallback non può essere un "
                    "servizio online o a pagamento."
                ),
            )
        preset = get_preset(str(provider))
        if preset is not None:
            # Un servizio online si attiva solo con una scelta esplicita e con la
            # conferma che la conversazione lascia il computer.
            if not bool(self.get("ai.online.consent", False)):
                raise ConfigError(
                    "Provider IA online non autorizzato.",
                    detail=(
                        "Hai scelto %s: i messaggi lascerebbero questo computer. "
                        "Verifica le condizioni gratuite (%s) e imposta "
                        "ai.online.consent=true per confermare." % (preset.label, preset.signup_url)
                    ),
                )
            for key in ("ai.online.model", "ai.online.api_key_env"):
                value = self.get(key, "")
                if value is not None and not isinstance(value, str):
                    raise ConfigError("%s deve essere una stringa." % key)
        if provider == "openai":
            base_url = self.get("ai.openai.base_url")
            if not isinstance(base_url, str) or not base_url.strip():
                raise ConfigError("ai.openai.base_url deve essere un URL http/https.")
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ConfigError(
                    "ai.openai.base_url deve essere un URL http/https valido.",
                    detail=base_url,
                )
            if not is_local_endpoint(base_url) and not bool(self.get("ai.openai.allow_remote", False)):
                raise ConfigError(
                    "Endpoint IA remoto non autorizzato.",
                    detail=(
                        "Amy può usare solo servizi gratuiti. %s non è locale: "
                        "imposta ai.openai.allow_remote=true solo dopo aver verificato "
                        "che il servizio è gratuito e non richiede pagamenti obbligatori."
                        % base_url
                    ),
                )
        transport = self.get("robot.transport")
        if transport not in {"simulated", "mqtt"}:
            raise ConfigError(
                "Trasporto robot non supportato: %s" % transport,
                detail="Valori ammessi: simulated, mqtt",
            )
        try:
            timeout = float(self.get("ai.timeout_s", 120))
            if timeout <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ConfigError("ai.timeout_s deve essere un numero positivo.") from exc
        roots = self.get("security.allowed_roots", [])
        if not isinstance(roots, list) or not roots:
            raise ConfigError("security.allowed_roots deve contenere almeno una cartella.")
        for key in ("memory.db_path", "security.audit_path", "security.backup_dir", "logging.file"):
            value = self.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ConfigError("Percorso non valido: %s" % key)

    def path_value(self, dotted: str) -> Path:
        return Path(self.require_str(dotted)).expanduser()

    def allowed_roots(self) -> list:
        return [Path(str(root)).expanduser().resolve() for root in self.get("security.allowed_roots", [])]

    def ensure_dirs(self) -> None:
        """Crea le cartelle dati con permessi prudenti."""
        directories = [
            self.path.parent,
            self.path_value("memory.db_path").parent,
            self.path_value("security.audit_path").parent,
            self.path_value("security.backup_dir"),
            self.path_value("logging.file").parent,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def save(self) -> Path:
        self.ensure_dirs()
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.path)
        return self.path

    def redacted(self) -> Dict[str, Any]:
        """Copia mostrabile in UI/log: nessun segreto, solo nomi di variabili."""
        data = copy.deepcopy(self.data)
        data.pop("secrets", None)
        return data


def load_secrets(path: Optional[Path] = None) -> Dict[str, str]:
    """Legge i segreti opzionali da un file con permessi 0600."""
    secrets_path = Path(path).expanduser() if path else amy_home() / "secrets.json"
    if not secrets_path.exists():
        return {}
    try:
        mode = stat.S_IMODE(secrets_path.stat().st_mode)
        if mode & 0o077:
            raise ConfigError(
                "Il file dei segreti ha permessi troppo aperti.",
                detail="Esegui: chmod 600 %s" % secrets_path,
            )
        with secrets_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            "Impossibile leggere il file dei segreti.",
            detail=str(exc),
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError("Il file dei segreti deve essere un oggetto JSON.")
    return {str(k): str(v) for k, v in data.items()}


def get_secret(name: str, *, required: bool = False, secrets: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Risolve un segreto da ambiente o file, senza mai loggarlo."""
    value = os.environ.get(name)
    if value:
        return value
    if secrets is None:
        secrets = load_secrets()
    value = secrets.get(name)
    if not value and required:
        raise ConfigError(
            "Segreto mancante: %s" % name,
            detail="Imposta la variabile d'ambiente o ~/.amy/secrets.json (chmod 600).",
        )
    return value or None


def init_config(*, force: bool = False, path: Optional[Path] = None) -> Path:
    """Crea la configurazione iniziale senza sovrascrivere quella esistente."""
    config_path = Path(path).expanduser() if path else default_config_path()
    if config_path.exists() and not force:
        return config_path
    config = Config(copy.deepcopy(DEFAULT_CONFIG), config_path)
    config.ensure_dirs()
    return config.save()
