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
    },
    "online": {
      "model": "",
      "api_key_env": "",
      "consent": false
    }
  },
  "memory": {
    "db_path": "~/.amy/amy.db",
    "max_history_messages": 24,
    "max_history_chars": 4000,
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
  "calendar": {
    "default_name": "Calendario"
  },
  "reminders": {
    "default_list": ""
  },
  "opencode": {
    "enabled": false,
    "binary": "opencode2",
    "project_dir": "",
    "timeout_s": 300,
    "max_output_chars": 8000,
    "restart_delay_s": 12
  },
  "mail": {
    "default_account": "",
    "default_mailbox": "INBOX",
    "warm_on_start": true
  },
  "voice": {
    "enabled": false,
    "startup_greeting": true,
    "startup_greeting_text": "Amy è attiva e operativa.",
    "tts": {
      "engine": "say",
      "voice": "Alice",
      "rate": 185
    },
    "stt": {
      "engine": "auto",
      "command": "whisper-cli",
      "model": "",
      "language": "it",
      "download_root": "~/.amy/models/whisper",
      "initial_prompt": "Comandi in italiano per Amy: apri mail, che ore sono, accendi la luce."
    },
    "conversation": {
      "enabled": true,
      "timeout_s": 30,
      "barge_in": true,
      "barge_in_chunk_s": 1.0,
      "barge_in_model": "",
      "listen_seconds": 8.0,
      "vad": true,
      "vad_silence_s": 1.0,
      "vad_start_timeout_s": 6.0,
      "vad_max_seconds": 15.0
    },
    "wake_word": {
      "enabled": true,
      "start_on_launch": true,
      "phrase": "amy",
      "sensitivity": 0.5,
      "max_minutes": 0,
      "echo_guard": true,
      "echo_guard_cooldown_s": 0.8
    },
    "recorder": {
      "engine": "auto",
      "device": "",
      "samplerate": 16000,
      "seconds": 5
    }
  },
  "vision": {
    "enabled": true,
    "camera": false,
    "describe": false,
    "max_chars": 8000
  },
  "dev": {
    "project_dir": "",
    "test_timeout_s": 300,
    "max_output_chars": 6000
  },
  "telegram": {
    "enabled": false,
    "token_env": "AMY_TELEGRAM_TOKEN",
    "allowed_user_ids": [],
    "poll_timeout_s": 25,
    "voice_replies": false,
    "max_voice_seconds": 120,
    "max_voice_bytes": 20971520,
    "max_message_chars": 3000
  },
  "home": {
    "enabled": false,
    "broker": "",
    "port": 1883,
    "username": "",
    "password_env": "AMY_HOME_MQTT_PASSWORD",
    "timeout_s": 5,
    "devices": [],
    "scenes": []
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

Il modo sicuro per scriverli è il comando dedicato, che non li mostra e non li
salva nella cronologia della shell:

```bash
python3 -m amy secret set GROQ_API_KEY   # chiede il valore a schermo spento
python3 -m amy secret list               # mostra solo i nomi
```

Il file resta `~/.amy/secrets.json` con permessi `0600`:

```bash
chmod 600 ~/.amy/secrets.json
```

```json
{
  "GROQ_API_KEY": "...",
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

### Provider online gratuito (Groq)

Quando il modello locale è troppo lento, si può usare un servizio online gratuito
verificato. La conversazione lascia il Mac: serve un consenso esplicito.

```bash
python3 -m amy providers            # preset disponibili, limiti e licenze
python3 -m amy secret set GROQ_API_KEY   # chiede il valore senza mostrarlo
```

```json
{
  "ai": {
    "provider": "groq",
    "fallback_provider": "offline",
    "online": {
      "model": "openai/gpt-oss-120b",
      "api_key_env": "",
      "consent": true
    }
  }
}
```

- `provider`: `groq` sceglie GroqCloud, piano Free (nessuna carta di credito).
- `online.model`: vuoto usa il modello predefinito del preset.
- `online.api_key_env`: vuoto usa `GROQ_API_KEY`.
- `online.consent`: deve essere `true`; senza, la configurazione viene rifiutata.
- Il fallback resta `offline`: il servizio online non può mai essere il fallback.

La chiave vive in `~/.amy/secrets.json` con permessi `600` (oppure in una variabile
d'ambiente). Non va mai scritta nella configurazione, nei log o nel repository.
`python3 -m amy secret list` mostra solo i nomi, mai i valori.

`amy doctor` verifica la chiave con `GET /models` e segnala se il modello non è
nell'elenco del servizio. Per tornare al locale basta rimettere
`"provider": "ollama"` (o `"offline"`) e `"consent": false`.

Il piano Free ha 8.000 token al minuto: bastano per uno o due messaggi ravvicinati,
non per una raffica. Amy riduce il catalogo strumenti a nome, descrizione e parametri,
ritenta una volta un `429` rispettando `Retry-After` e, se il limite resta, risponde
con il fallback locale dichiarandolo. La quota si libera da sola entro un minuto.

Limiti e privacy del piano Free sono documentati in
[GRATUITO.md](GRATUITO.md#provider-ia-online-gratuiti-facoltativi).

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
- `voice.startup_greeting` (default `true`) fa pronunciare il messaggio di avvio
  all'avvio della dashboard; `voice.startup_greeting_text` ne imposta il testo.
  Il saluto usa solo la sintesi locale e non avvia alcuna registrazione.
  La variabile d'ambiente `AMY_STARTUP_GREETING=0` lo disattiva per una sessione.
- `voice.stt.engine = "auto"` sceglie il motore migliore disponibile
  (`faster-whisper`, poi `whisper-cli`); `voice.stt.model` vuoto rende lo STT non
  disponibile con i motori che richiedono un modello esplicito.
- `voice.stt.download_root` è la cartella dei modelli locali (default
  `~/.amy/models/whisper`).
- `voice.recorder.engine = "auto"` preferisce `sounddevice`, poi `ffmpeg`;
  `voice.recorder.device` e `voice.recorder.samplerate` scelgono il microfono.
- `voice.conversation.vad` (default `true`) chiude il turno dopo circa un secondo
  di silenzio: un indirizzo email o una frase lunga non vengono tagliati.
  `vad_max_seconds` (default 15) è il limite massimo di un turno.
- `voice.conversation.listen_seconds` (default 8) è la finestra fissa, usata solo
  se il VAD non è disponibile.
- `voice.conversation.timeout_s` (default 30) è il silenzio massimo prima di
  «Sei ancora lì?»; `barge_in` (default true) ascolta anche durante la sintesi per
  interrompere Amy con «Amy».
- `memory.max_history_chars` (default 4000) limita lo storico inviato al modello:
  evita che una risposta lunga faccia superare il limite gratuito di token.
- `voice.wake_word.max_minutes` (default 0 = nessun limite, massimo 120) limita la
  durata dell'ascolto continuo.
- `voice.wake_word.echo_guard` (default `true`) tiene il microfono chiuso mentre
  Amy parla: i frammenti che contengono la sua voce vengono scartati.
  `voice.wake_word.echo_guard_cooldown_s` (default 0,8) è la pausa attesa dopo
  la fine di una sintesi prima di riaprire il microfono.
- `robot.transport = "simulated"` è il default sicuro.
- `robot.transport = "mqtt"` è sperimentale e non verificato.
- La password MQTT si legge da `robot.password_env`.

### OpenCode 2

- `opencode.enabled` (default `false`) abilita l'affidamento di richieste a
  `opencode2`. È spento per default: un agente esterno può modificare il progetto.
- `opencode.project_dir` (default vuoto = cartella corrente di Amy) è la cartella
  di lavoro; deve stare nelle radici autorizzate.
- `opencode.timeout_s` (default 300) limita l'esecuzione; `opencode.binary`
  permette di indicare un percorso diverso da `opencode2`.
- `opencode.restart_delay_s` (default 12) è l'attesa prima del riavvio quando si
  usa `restart_after`: lascia il tempo ad Amy di pronunciare l'esito.

### Posta

- `mail.default_account` (default vuoto = primo account) è l'account usato da
  `mail.list`, `mail.search` e `mail.read` quando la richiesta non ne indica uno.
  Si può indicare il nome dell'account o l'indirizzo email.
- `mail.default_mailbox` (default `INBOX`) è la cassetta predefinita.
- `mail.warm_on_start` (default `true`) apre Mail in background all'avvio per
  evitare che il primo comando attenda decine di secondi.
- Il corpo di un messaggio è di livello B: richiede conferma e, con un provider
  online, viene inviato a quel servizio.

### Calendario

- `calendar.default_name` (default `"Calendario"`) è il calendario usato da
  `calendar.create` quando la richiesta non ne indica uno.
- Se il nome configurato non esiste, Amy elenca i calendari scrivibili e non
  scrive in quelli di sistema (festività, compleanni, suggerimenti di Siri).
- La creazione di un evento è di livello B, l'eliminazione è di livello C: entrambe
  richiedono la conferma. Il primo uso richiede il permesso Automazione per Calendar.
- Il riquadro «Prossimi appuntamenti» della dashboard non aggiunge impostazioni:
  usa `calendar.default_name` e `calendar.events` in sola lettura. La finestra è
  di 7 giorni (`?days=` è limitato a 1–14) e il polling è ogni 2 minuti. Se
  Calendar non è raggiungibile il pannello dichiara l'errore.
- `reminders.default_list` (default vuoto = prima lista disponibile) sceglie la lista
  usata da `reminders.create`, `reminders.complete` e `reminders.delete`.

### Developer Assistant

- `dev.project_dir` (default vuoto = radice del pacchetto Amy) è il progetto su
  cui operano `dev.status`, `dev.diff`, `dev.analyze` e `dev.test`. Deve stare
  nelle radici autorizzate della policy dei percorsi.
- `dev.test_timeout_s` (default 300, massimo 900) limita l'esecuzione della suite.
- `dev.max_output_chars` (default 6000) limita diff e output dei test.
- Gli strumenti leggono il progetto con comandi Git in lista chiusa e con la
  libreria standard: nessuna shell arbitraria. `dev.test` è livello B; le
  modifiche restano a OpenCode, livello C.

### Telegram

Il collegamento usa **solo Bot API ufficiale in long polling**: nessuna porta
aperta, nessun webhook pubblico, nessun account utente di Amy.

1. Su Telegram apri `@BotFather`, esegui `/newbot` e scegli un username.
2. Salva il token senza scriverlo in chat o nel repository:

```bash
python3 -m amy secret set AMY_TELEGRAM_TOKEN
```

3. Scopri il tuo **ID numerico** (per esempio con `@userinfobot`) e inseriscilo
   in `telegram.allowed_user_ids`.
4. Imposta `telegram.enabled = true` e riavvia Amy.

```json
{
  "telegram": {
    "enabled": true,
    "token_env": "AMY_TELEGRAM_TOKEN",
    "allowed_user_ids": [123456789],
    "voice_replies": false
  }
}
```

- Il bot è raggiungibile all’username scelto, per esempio `@AmyCoreBot`.
- Amy risponde solo a chat **private** con utenti in allowlist; gruppi e canali
  sono ignorati.
- Dopo che hai premuto **Start**, il bot può inviarti messaggi anche senza una tua
  nuova richiesta.
- Le note vocali vengono scaricate, trascritte in locale e trattate come testo.
  Se `faster-whisper` non decodifica il formato OGG/Opus, serve `ffmpeg`.
- `telegram.voice_replies` (default `false`) invia anche una risposta audio M4A
  generata con `say` e `afconvert`; non è una nota vocale OGG/Opus.
- `telegram.max_voice_seconds` e `max_voice_bytes` limitano i file accettati;
  `max_message_chars` limita il testo in ingresso.
- **Le chiamate vocali non sono supportate** dalla Bot API: Amy non può chiamare
  né ricevere chiamate. Sono possibili solo chat e note vocali.
- Il token si legge da `AMY_TELEGRAM_TOKEN` o da `~/.amy/secrets.json`; non
  compare mai in configurazione, log, prompt o dashboard.
- Telegram è un servizio gratuito, ma le chat dei bot non sono end-to-end
  encrypted: non inviare password o dati sensibili.

### Visione e telecamera

- `vision.camera` (default `false`) abilita `vision.capture`, livello B. La cattura
  usa AVFoundation in locale e salva in `~/Downloads/Amy/camera`; il primo uso
  richiede il permesso **Telecamera**.
- `vision.describe` (default `false`) è riservato a un futuro provider visivo
  gratuito: oggi non esiste uno strumento di descrizione.
- `vision.max_chars` limita il testo OCR restituito.

### Smart Home

```json
{
  "home": {
    "enabled": true,
    "broker": "192.168.1.10",
    "port": 1883,
    "username": "amy",
    "password_env": "AMY_HOME_MQTT_PASSWORD",
    "devices": [
      {
        "id": "luce_salotto",
        "name": "Luce salotto",
        "type": "luce",
        "room": "salotto",
        "state_topic": "casa/salotto/luce/stato",
        "command_topic": "casa/salotto/luce/set"
      }
    ],
    "scenes": [
      {"name": "sera", "device": "luce_salotto", "value": "off"}
    ]
  }
}
```

- `home.enabled` (default `false`) tiene spenti tutti gli strumenti della domotica.
- `home.broker` vuoto significa nessun broker: i comandi falliscono con un errore
  dichiarato, non fingono di aver agito.
- La password si legge dalla variabile indicata da `home.password_env`; non va
  scritta nella configurazione, nei log o nel repository.
- `home.set` è livello B, `home.scene` livello C. Lo stato inviato non è una
  conferma: senza una lettura del sensore Amy dichiara `verified: false`.
- `paho-mqtt` è una dipendenza opzionale e serve solo se si usa la domotica.

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

Queste sono invarianti di sicurezza nel codice, non preferenze.
