# Configurazione

La configurazione di Amy vive **fuori dal repository**, in `~/.amy/config.json`.
I segreti non stanno lì: si leggono da variabili d'ambiente o da
`~/.amy/secrets.json` con permessi `0600`.

Amy accetta solo componenti e servizi gratuiti. Il default è locale e nessuna
funzione richiede pagamenti. Un endpoint IA remoto è bloccato senza consenso esplicito.
Vedi [GRATUITO.md](GRATUITO.md).

## 1. File e cartelle

| Percorso | Contenuto |
| --- | --- |
| `~/.amy/config.json` | configurazione principale, permessi `0600` |
| `~/.amy/secrets.json` | segreti opzionali, permessi `0600` obbligatori |
| `~/.amy/amy.db` | memoria SQLite |
| `~/.amy/audit.jsonl` | audit append-only |
| `~/.amy/amy.log` | log applicativo con rotazione |
| `~/.amy/backups/` | backup creati prima delle sovrascritture |
| `~/.amy/backups/trash/` | cestino recuperabile di Amy |

Variabili che cambiano la posizione dei file:

| Variabile | Effetto |
| --- | --- |
| `AMY_HOME` | sostituisce `~/.amy` come cartella dati |
| `AMY_CONFIG` | percorso alternativo della configurazione |

## 2. Inizializzazione

```bash
python3 -m amy init
python3 -m amy init --force
python3 -m amy init --path /percorso/alternativo.json
```

`init`:

- crea le cartelle dati;
- scrive la configurazione con permessi `0600`;
- **non** sovrascrive un file esistente senza `--force`.

```bash
python3 -m amy config show   # configurazione effettiva, senza segreti
python3 -m amy config path   # percorso del file in uso
```

`config show` non mostra il contenuto di `secrets.json`.

## 3. Schema completo con valori predefiniti

```json
{
  "assistant": {
    "name": "Amy",
    "user_name": "",
    "language": "it-IT"
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
      "require_api_key": false,
      "allow_remote": false
    }
  },
  "memory": {
    "db_path": "~/.amy/amy.db",
    "max_history_messages": 24,
    "max_facts_in_prompt": 40,
    "retention_days": 365
  },
  "security": {
    "auto_approve_levels": ["A"],
    "auto_approve_tools": [],
    "allowed_roots": [
      "~/Progetti",
      "~/Documents",
      "~/Desktop",
      "~/Downloads"
    ],
    "max_file_bytes": 1048576,
    "shell_timeout_s": 20,
    "confirmation_ttl_s": 300,
    "audit_path": "~/.amy/audit.jsonl",
    "backup_dir": "~/.amy/backups"
  },
  "voice": {
    "enabled": false,
    "tts": {
      "engine": "say",
      "voice": "Alice",
      "rate": 185
    },
    "stt": {
      "engine": "whisper-cli",
      "command": "whisper-cli",
      "model": "",
      "language": "it"
    },
    "wake_word": {
      "enabled": false,
      "phrase": "amy",
      "sensitivity": 0.5
    },
    "recorder": {
      "engine": "ffmpeg",
      "device": ":0",
      "seconds": 5
    }
  },
  "robot": {
    "transport": "simulated",
    "host": "amy-pi.local",
    "port": 1883,
    "username": "amy-pi",
    "password_env": "AMY_MQTT_PASSWORD",
    "tls": false,
    "timeout_s": 3.0,
    "simulator": {
      "battery_pct": 87,
      "watchdog_timeout_s": 5.0
    }
  },
  "ui": {
    "host": "127.0.0.1",
    "port": 8765,
    "open_browser": false,
    "allow_remote": false
  },
  "logging": {
    "level": "INFO",
    "file": "~/.amy/amy.log",
    "max_bytes": 2000000,
    "backup_count": 3
  }
}
```

Il file dell'utente viene unito in profondità ai default: basta specificare le chiavi
che si vogliono cambiare.

## 4. Variabili d'ambiente

| Variabile | Chiave | Tipo |
| --- | --- | --- |
| `AMY_AI_PROVIDER` | `ai.provider` | stringa: `ollama`, `openai`, `offline` |
| `AMY_AI_MODEL` | `ai.model` | stringa |
| `AMY_AI_BASE_URL` | `ai.base_url` | stringa |
| `AMY_ROBOT_TRANSPORT` | `robot.transport` | stringa: `simulated`, `mqtt` |
| `AMY_ROBOT_HOST` | `robot.host` | stringa |
| `AMY_ROBOT_PORT` | `robot.port` | intero |
| `AMY_LOG_LEVEL` | `logging.level` | stringa |
| `AMY_UI_PORT` | `ui.port` | intero |

I valori vengono convertiti sul tipo del default. Un intero non valido produce un
errore di configurazione, non un valore silenziosamente sbagliato.

## 5. Segreti

Mai nella configurazione principale, mai nei log, mai nella dashboard.

```bash
chmod 600 ~/.amy/secrets.json
```

```json
{
  "OPENAI_API_KEY": "sk-...",
  "AMY_MQTT_PASSWORD": "..."
}
```

Regole:

- se il file è leggibile da gruppo o altri, Amy si rifiuta di usarlo e chiede
  `chmod 600`;
- le variabili d'ambiente hanno precedenza sul file;
- `get_secret()` non logga mai il valore;
- la configurazione mostrata non contiene segreti.

Provider compatibile OpenAI su un server **locale** (llama.cpp, LM Studio, vLLM,
altro server sulla propria rete):

```json
{
  "ai": {
    "provider": "openai",
    "openai": {
      "base_url": "http://127.0.0.1:8000/v1",
      "model": "local-model",
      "require_api_key": false,
      "allow_remote": false
    }
  }
}
```

L'endpoint predefinito è locale e non richiede chiave. Se il server locale richiede
una chiave fittizia, impostare `require_api_key` e `api_key_env`.

Un endpoint **pubblico** è rifiutato dalla validazione salvo consenso esplicito:

```json
{
  "ai": {
    "provider": "openai",
    "openai": {
      "base_url": "https://esempio.invalid/v1",
      "model": "modello",
      "require_api_key": true,
      "api_key_env": "MY_FREE_API_KEY",
      "allow_remote": true
    }
  }
}
```

`allow_remote=true` non rende il servizio gratuito: significa che l'utente ha
verificato condizioni, limiti e assenza di pagamenti obbligatori. Amy non usa mai un
endpoint remoto come fallback automatico. Dettagli in [GRATUITO.md](GRATUITO.md).

## 6. Sicurezza

### Livelli

```json
{
  "security": {
    "auto_approve_levels": ["A"],
    "auto_approve_tools": []
  }
}
```

- `auto_approve_levels` può contenere solo `A` in pratica: il livello **C non è mai
  auto-approvato**, anche se lo si inserisce qui.
- `auto_approve_tools` è un elenco di nomi esatti per il livello B. Non accetta
  wildcard. Va usato con cautela e solo per azioni che l'utente comprende.

### Radici

```json
{
  "security": {
    "allowed_roots": ["~/Progetti", "~/Documents"]
  }
}
```

Le radici vengono risolte con `resolve()`. Aggiungere `~` allarga molto la
superficie: la deny-list resta, ma è una scelta consapevole.

### Limiti

| Chiave | Effetto |
| --- | --- |
| `max_file_bytes` | dimensione massima di lettura/scrittura |
| `shell_timeout_s` | timeout dei comandi in enum |
| `confirmation_ttl_s` | validità di una richiesta di conferma |

## 7. Provider IA

### Ollama (predefinito)

```json
{
  "ai": {
    "provider": "ollama",
    "model": "qwen2.5-coder:14b",
    "base_url": "http://127.0.0.1:11434"
  }
}
```

```bash
ollama serve
ollama pull qwen2.5-coder:14b
python3 -m amy ask "rispondi solo con: ciao"
```

Se il modello non è installato, `amy doctor` lo segnala. Il fallback non deve
nascondere il problema.

### Offline

```json
{
  "ai": {
    "provider": "offline"
  }
}
```

L'offline è un interprete deterministico di comandi italiani frequenti, non un
modello linguistico. Non va presentato come equivalente a Ollama.

### Fallback

```json
{
  "ai": {
    "fallback_provider": "offline"
  }
}
```

Se il provider primario fallisce, Amy usa il fallback e riporta il motivo nello stato
e nella risposta. Il fallback non deve essere scambiato per il primario.

## 8. Dashboard

```json
{
  "ui": {
    "host": "127.0.0.1",
    "port": 8765,
    "open_browser": false,
    "allow_remote": false
  }
}
```

- `host` deve essere un indirizzo di loopback, salvo `allow_remote=true`.
- `allow_remote=true` permette il bind su altre interfacce ma **non aggiunge
  autenticazione**. È sconsigliato e va usato solo con piena consapevolezza.
- La dashboard non usa CDN, non carica risorse esterne e non contiene `innerHTML`.
- Non esiste un login. Non esporla su Internet.

Avvio:

```bash
python3 -m amy serve
python3 -m amy serve --port 9000
python3 -m amy serve --open-browser
```

## 9. Voce e robot

Configurazione vocale e robotica sono descritte in dettaglio in
[VOCE.md](VOCE.md) e [ROBOTICA.md](ROBOTICA.md). In sintesi:

- `voice.enabled` non apre il microfono: abilita solo il servizio.
- `voice.stt.model` vuoto rende lo STT non disponibile.
- `robot.transport = "simulated"` è il default sicuro.
- `robot.transport = "mqtt"` è sperimentale e non verificato.
- La password MQTT si legge da `robot.password_env`.

## 10. Log

```json
{
  "logging": {
    "level": "INFO",
    "file": "~/.amy/amy.log",
    "max_bytes": 2000000,
    "backup_count": 3
  }
}
```

I log redigono i campi sensibili. La redazione è euristica: non inserire segreti in
campi con nomi innocui.

## 11. Validazione

All'avvio Amy verifica:

- `ai.provider` in `{ollama, openai, offline}`;
- `ai.fallback_provider` in `{ollama, offline}`: il fallback non può essere un
  servizio a pagamento;
- `ai.openai.base_url` è un URL http/https; se non è locale richiede
  `ai.openai.allow_remote=true`;
- `robot.transport` in `{simulated, mqtt}`;
- `ai.timeout_s` numerico e positivo;
- `security.allowed_roots` lista non vuota;
- percorsi di memoria, audit, backup e log non vuoti.

Una configurazione non valida produce un errore esplicito e Amy non parte con valori
casuali.

## 12. Esempi pratici

### Solo locale, senza rete

```json
{
  "ai": {"provider": "ollama", "base_url": "http://127.0.0.1:11434"},
  "robot": {"transport": "simulated"},
  "ui": {"host": "127.0.0.1", "allow_remote": false}
}
```

### Provider compatibile OpenAI locale

```json
{
  "ai": {
    "provider": "openai",
    "openai": {
      "base_url": "http://127.0.0.1:8000/v1",
      "model": "local-model",
      "require_api_key": false,
      "allow_remote": false
    }
  }
}
```

```bash
python3 -m amy ask "rispondi solo con: ciao"
```

Avviare prima il server locale compatibile OpenAI. Amy non scarica né avvia il server
al posto dell'utente.

### Radici più strette

```json
{
  "security": {
    "allowed_roots": ["~/Progetti/amy_brain"]
  }
}
```

Utile per limitare l'accesso a un solo progetto.

### Più conferme, nessuna eccezione

```json
{
  "security": {
    "auto_approve_levels": [],
    "auto_approve_tools": []
  }
}
```

Amy chiederà conferma anche per azioni di livello A. È più sicuro, ma più faticoso.

## 13. Backup e ripristino

Non esiste ancora un comando di backup completo. Copiare i file con Amy ferma:

```bash
cp -R ~/.amy ~/Backup/amy-$(date +%Y%m%d)
```

Il ripristino va fatto a processo fermo. La memoria SQLite non va copiata mentre è in
scrittura senza le dovute precauzioni.

## 14. Cosa non è configurabile

- La policy che impone la conferma per il livello C.
- La precedenza di E-stop e stop.
- L'assenza di `shell=True`.
- Il blocco degli indirizzi privati in `web.fetch`.
- L'assenza di registrazione in background non richiesta.

Queste sono invarianti di sicurezza nel codice, non preferenze.
