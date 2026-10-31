"""Preset di provider IA online gratuiti, verificati.

Un preset esiste solo se sono vere tutte queste condizioni:

- si può usare senza carta di credito e senza pagamenti obbligatori;
- il piano gratuito basta per un uso personale, senza crediti acquistabili
  necessari per funzionare;
- esiste un modello con licenza verificabile e adatta alla conversazione;
- il servizio è compatibile con l'API OpenAI, quindi riusa l'adattatore del
  progetto senza nuove dipendenze.

Il provider online non è mai il default del repository: si attiva solo con una
scelta esplicita nella configurazione personale (``ai.provider``) e con
``ai.online.consent = true``. Il fallback resta locale e gratuito.

Ogni preset dichiara limiti e condizioni verificate alla data indicata: se il
servizio cambia, vanno riverificate prima di aggiornare questo file.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from ..core.errors import ConfigError


@dataclass(frozen=True)
class FreePreset:
    """Descrizione di un servizio IA online gratuito."""

    id: str
    label: str
    base_url: str
    model: str
    alternate_models: Tuple[str, ...]
    api_key_env: str
    signup_url: str
    free_terms: str
    limits: str
    model_license: str
    privacy: str
    verified_on: str

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["alternate_models"] = list(self.alternate_models)
        return data


GROQ = FreePreset(
    id="groq",
    label="GroqCloud (piano Free)",
    base_url="https://api.groq.com/openai/v1",
    model="openai/gpt-oss-120b",
    alternate_models=("openai/gpt-oss-20b",),
    api_key_env="GROQ_API_KEY",
    signup_url="https://console.groq.com/keys",
    free_terms=(
        "Piano Free senza carta di credito: la registrazione non richiede un metodo "
        "di pagamento. Il piano Developer a consumo è facoltativo e non serve ad Amy."
    ),
    limits=(
        "gpt-oss-120b: 30 richieste al minuto, 1.000 al giorno, 8.000 token al "
        "minuto, 200.000 token al giorno."
    ),
    model_license="GPT-OSS 120B: Apache-2.0 (pesi aperti).",
    privacy=(
        "I dati non sono conservati per impostazione predefinita; possono essere "
        "registrati fino a 30 giorni per affidabilità e abuso. La conservazione "
        "zero è attivabile nelle impostazioni dell'account. Elaborazione negli USA."
    ),
    verified_on="2026-10-31",
)

PRESETS: Dict[str, FreePreset] = {GROQ.id: GROQ}


def preset_names() -> Tuple[str, ...]:
    return tuple(PRESETS)


def get_preset(name: str) -> Optional[FreePreset]:
    return PRESETS.get(str(name).strip().lower())


def require_preset(name: str) -> FreePreset:
    preset = get_preset(name)
    if preset is None:
        raise ConfigError(
            "Provider IA online gratuito non riconosciuto: %s" % name,
            detail="Preset disponibili: %s" % ", ".join(preset_names()),
        )
    return preset
