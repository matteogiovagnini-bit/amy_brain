# Architettura target di Amy

**Fase 2 — architettura di riferimento**
Data: **7 novembre 2026**
Stato: **proposta da approvare**. Nessun codice è stato spostato o riscritto.

---

## 1. Principi

1. **Conservare prima di riorganizzare.** Ogni componente funzionante resta; la
   migrazione lo avvolge in un modulo, non lo riscrive.
2. **Contratti espliciti.** Un modulo è un oggetto con nome, versione, stato,
   ciclo di vita, strumenti e capacità dichiarate.
3. **Amy Core orchestra, i moduli eseguono.** Il Core non contiene la logica di
   Mac Control, voce, robot o memoria: la coordina.
4. **Sicurezza nel codice.** Le autorizzazioni non dipendono dal prompt; il
   livello C resta sempre confermato; E-stop e stop restano fuori dalla policy.
5. **Locale e gratuito per default.** Ollama/offline, componenti di sistema,
   nessun servizio obbligatorio a pagamento; l'online gratuito è opt-in.
6. **Stato onesto.** Un modulo offline o disabilitato lo dichiara; nessun dato
   simulato spacciato per reale.
7. **Semplicità.** Processo singolo, SQLite, event bus in memoria, niente
   microservizi o code distribuite finché non servono davvero.
8. **Compatibilità.** CLI, API HTTP, file di configurazione e test esistenti
   continuano a funzionare durante tutta la migrazione.

---

## 2. Vista d'insieme

```text
                              ┌──────────────────────────────┐
                              │          AMY CORE            │
                              │  orchestrazione • contesto   │
                              │  autorizzazioni • stato      │
                              │  eventi • provider routing   │
                              └──────────────┬───────────────┘
                                             │
        ┌──────────────┬──────────────┬──────┴───────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼              ▼
  01 VOICE       02 MAC CONTROL  03 PERSONAL    04 MEMORY      05 DEVELOPER    06 VISION
  wake word      app • file      calendario     fatti         OpenCode        OCR schermo
  STT • TTS      sistema • web   promemoria     progetti      test • diff     immagini
  VAD • barge-in shell • OCR     mail • task    operativa     analisi         telecamera*
        │              │              │              │              │              │
        └──────────────┴──────────────┴──────┬───────┴──────────────┴──────────────┘
                                             │
                                   ┌─────────┴─────────┐
                                   ▼                   ▼
                             07 SMART HOME       08 ROBOT CONTROL
                             MQTT • sensori      protocollo • simulatore
                                   │
                                   ▼
                             09 TELEGRAM
                             chat • note vocali
                             luci • scene        MQTT • sicurezza • E-stop
```

`*` = capacità opzionale, spenta per default.

### 2.1 Flusso di un turno con i moduli

```text
utente
  → Amy Core: classificazione intento + contesto
  → Memory: recupera fatti/progetti rilevanti
  → modulo competente (uno o più)
  → Authorization: rischio A/B/C + capacità del modulo
  → eventuale conferma (due fasi)
  → esecuzione nel modulo
  → evento tool.finished + audit
  → Memory: aggiorna attività/risultato
  → Core: risposta unificata all'utente
```

Il Core può coordinare più moduli nello stesso turno (es. «controlla il Raspberry
e dimmi se il robot è pronto»): raccoglie risultati parziali e dichiara ciò che non
è disponibile, senza inventare.

---

## 3. Amy Core

### 3.1 Responsabilità

- Ricevere richieste da CLI, dashboard, voce e API.
- Costruire il contesto (storia, fatti, stato moduli, capacità).
- Classificare l'intento e scegliere i moduli (il modello propone, il codice
  valida).
- Applicare le autorizzazioni e gestire le conferme in due fasi.
- Coordinare più moduli e comporre la risposta.
- Aggregare lo stato e pubblicare eventi.
- Gestire errori, timeout, correlazione e audit.

### 3.2 Componenti interni proposti

| Componente | File target | Responsabilità |
| --- | --- | --- |
| `Orchestrator` | `amy/core/orchestrator.py` | turno, passi, conferme, risultati |
| `ModuleRegistry` | `amy/core/modules.py` | registrazione, ciclo di vita, stato |
| `EventBus` | `amy/shared/events.py` | pub/sub in-process |
| `StatusAggregator` | `amy/core/status.py` | stato Core + moduli + provider |
| `AuthorizationBroker` | `amy/security/authorization.py` | policy + capacità modulo |
| `PromptBuilder` | `amy/core/prompts.py` | prompt e catalogo dinamico |
| `ConfigStore` | `amy/core/config.py` | default, versione, migrazioni, segreti |
| `RestartService` | `amy/core/restart.py` | riavvio app nativa |
| `SystemService` | `amy/core/system.py` | informazioni di sistema unificate |

`Assistant` resta come **facciata** compatibile: delega a `Orchestrator` e mantiene
i metodi usati da CLI, server e test durante la transizione.

---

## 4. Contratto dei moduli

### 4.1 Interfaccia

```python
# amy/shared/module.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence

class ModuleState(str, Enum):
    DISABLED = "disabled"
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"

@dataclass(frozen=True)
class ModuleManifest:
    name: str                  # es. "voice"
    title: str                 # "Voice Engine"
    version: str
    description: str
    default_enabled: bool
    capabilities: Sequence[str]   # es. ("voice.wake", "voice.tts")
    requires: Sequence[str]       # es. ("microphone", "stt", "network")
    tools: Sequence[str]          # nomi degli strumenti posseduti
    optional: bool = True

@dataclass
class ModuleStatus:
    name: str
    state: ModuleState
    detail: str = ""
    available: bool = False
    data: Dict[str, Any] = field(default_factory=dict)

class AmyModule(Protocol):
    manifest: ModuleManifest
    def start(self, context: "ModuleContext") -> None: ...
    def stop(self) -> None: ...
    def status(self) -> ModuleStatus: ...
    def tools(self) -> Sequence[Any]: ...   # ToolSpec/FunctionTool
```

### 4.2 Ciclo di vita

```text
DISABLED ──enable──► INITIALIZING ──ok──► READY ──uso──► BUSY ──► READY
     ▲                    │                 │                  │
     └──────disable───────┴──errore──► ERROR / DEGRADED / OFFLINE
```

- Un modulo disabilitato non registra strumenti e non viene interrogato.
- Un modulo in errore non blocca gli altri: il Core lo dichiara e continua.
- `DEGRADED`: funziona in parte (es. Voice senza STT, solo TTS).
- `OFFLINE`: dipendenza esterna assente (broker, robot, provider).

### 4.3 ModuleContext

```python
@dataclass
class ModuleContext:
    config: Any
    secrets: Any
    events: EventBus
    logger: Any
    data_dir: Path
    path_guard: Any
    audit: Any
    memory: Any
    providers: Any
```

Ogni modulo riceve solo ciò che gli serve; non accede alle implementazioni interne
degli altri moduli.

---

## 5. I nove moduli

| # | Modulo | Responsabilità | Codice esistente riusato | Stato attuale | Default |
| --- | --- | --- | --- | --- | --- |
| 01 | **Voice Engine** | wake word, microfono, STT, TTS, VAD, conversazione, barge-in, code audio | `amy/voice/*` | funzionante con cuffie; wake word testuale | attivo se configurato |
| 02 | **Mac Control** | app, file, sistema, shell chiusa, web, apertura documenti, OCR schermo | `amy/tools/{apps,files,shell,system,web}.py`, `amy/macos/*`, `screen_*` | funzionante | attivo |
| 03 | **Personal Manager** | calendario, promemoria, mail, task, note, liste, agenda | `calendar_tools`, `reminders_tools`, `mail_tools`, `tasks_tools`, `notes_tools`, `PersonalManager` | completo (Fase 6) | attivo |
| 04 | **Memory** | conversazione, fatti, progetti, operativa, ricerca, verifica | `memory/store.py`, `memory_tools.py` | parziale | attivo |
| 05 | **Developer Assistant** | analisi codice, test, diff, refactoring, OpenCode | `dev/service.py`, `dev_tools.py`, `opencode_tools.py`, `app.restart` | nativo verificato; OpenCode per le modifiche | attivo; OpenCode opzionale |
| 06 | **Vision** | OCR schermo, immagini, telecamera, descrizione scena | `screen.py`, `screen_tools.py`, `macos/camera.py`, `camera.swift` | OCR + telecamera verificata; describe assente | OCR attivo; camera spenta |
| 07 | **Smart Home** | MQTT, dispositivi, sensori, luci, scene | `home/service.py`, `home_tools.py` | config e mock; nessun broker reale | spento |
| 08 | **Robot Control** | protocollo, simulatore, MQTT, sicurezza, telecamera robot | `amy/robot/*`, `robot_tools.py` | simulatore verificato; hardware no | simulatore attivo |
| 09 | **Telegram** | chat, note vocali, sessioni, conferme da smartphone | `amy/telegram/*`, `modules/telegram/adapter.py` | implementato; non verificato con bot reale | spento |

### 5.1 Voice Engine
- File target: `amy/modules/voice/`.
- Mantiene `VoiceService`, `VoiceStateMachine`, registratore VAD, STT, TTS, wake word.
- Pubblica `voice.state`, `voice.transcript`, `voice.error`.
- Dipendenze: microfono, STT, TTS; nessuna obbligatoria per la modalità testuale.
- Miglioramenti futuri: wake word audio-first, AEC nativa, full-duplex.

### 5.2 Mac Control
- File target: `amy/modules/mac_control/`.
- Raggruppa app, file, shell, sistema, web, apertura documenti, OCR schermo.
- Mantiene `PolicyEngine`, `PathGuard`, enum shell.
- Pubblica `system.metrics`, `tool.started/finished`.
- Nessun accesso diretto a GPIO/PWM; nessuna shell arbitraria.

### 5.3 Personal Manager
- File target: `amy/modules/personal/`.
- Calendario, promemoria, mail, task, note, liste.
- `agenda()` unico per dashboard e assistente.
- Storage: SQLite per task/note; Calendar/Reminders/Mail tramite AppleScript.
- Conferme: creazioni B, invio mail C, eliminazioni C.
- Miglioramenti: update eventi, ricorrenze, fusi orari, partecipanti.

### 5.4 Memory
- File target: `amy/modules/memory/`.
- Categorie: `conversation`, `personal`, `project`, `operational`.
- Campi proposti per `memory_items`: `id`, `category`, `key`, `value`, `source`,
  `confidence`, `verified`, `tags`, `created_at`, `updated_at`, `expires_at`.
- Migrazione non distruttiva da `facts`.
- Ricerca per testo/tag; nessun segreto; retention configurabile.

### 5.5 Developer Assistant
- File target: `amy/modules/developer/`.
- `dev.status`, `dev.diff` e `dev.analyze` sono livello A e non modificano file.
- `dev.test` esegue la suite unittest con timeout e output limitato (B).
- Comandi Git in lista chiusa, senza shell; percorso confinato al progetto.
- `opencode.run` resta per le modifiche, con C e cartella autorizzata.
- `app.restart` per caricare le modifiche.
- Nessuna installazione invasiva senza consenso; nessun comando distruttivo.

### 5.6 Vision
- File target: `amy/modules/vision/`.
- `ocr` locale (già pronto), `capture` implementato, `describe` non implementato.
- `vision.capture` usa AVFoundation in locale e richiede il permesso Telecamera;
  è spento per default (`vision.camera = false`).
- `describe` richiederebbe un provider visivo gratuito compatibile con Intel: senza
  di esso lo strumento resta assente e dichiarato non disponibile.
- OCR attivo; camera spenta salvo consenso esplicito in configurazione.

### 5.7 Smart Home
- File target: `amy/modules/home/`.
- Registry dispositivi (id, nome, tipo, stanza, protocollo, stato).
- MQTT configurabile; credenziali da segreti; timeout; online/offline.
- Strumenti: `home.devices`, `home.state`, `home.set`, `home.scene`.
- Livello B per comandi, C per azioni irreversibili; nessun produttore obbligatorio.

### 5.8 Robot Control
- File target: `amy/modules/robot/`.
- Mantiene protocollo v1, simulatore, MQTT, limiti, watchdog, E-stop.
- La sicurezza resta nel robot/Pi/ESP32; Amy invia solo comandi di alto livello.
- Telecamera robot tramite Vision, se disponibile.
- Nessuna modifica alla catena di sicurezza senza hardware e test dedicati.

### 5.9 Telegram
- File target: `amy/telegram/` e `amy/modules/telegram/`.
- Bot API ufficiale in long polling: nessuna porta in ingresso, nessun webhook.
- Solo chat private e utenti in allowlist per ID numerico.
- Sessioni dedicate per chat, conferme con pulsanti inline.
- Note vocali scaricate, trascritte in locale e cancellate dopo l'uso.
- Risposte vocali opzionali con `say` + `afconvert`.
- Le chiamate vocali non sono supportate dalla Bot API.

---

## 6. Event bus

### 6.1 Implementazione

`EventBus` in-process, thread-safe, con:

- `publish(topic, payload)` non bloccante per il chiamante;
- `subscribe(topic, handler)` e `unsubscribe`;
- consegna ai listener in un thread dedicato, con coda limitata;
- isolamento degli errori (un listener rotto non ferma gli altri);
- storico circolare limitato (ultimi N eventi) per la UI;
- logging strutturato con `turn_id`/`module`.

Niente broker esterno: è un bus locale. Se in futuro servirà la dashboard remota,
si potrà esporre in SSE.

### 6.2 Topic proposti

| Topic | Payload | Emesso da |
| --- | --- | --- |
| `core.turn.started` | `turn_id`, `session_id`, `text` | Core |
| `core.turn.finished` | `turn_id`, `status`, `tools` | Core |
| `module.status` | `module`, `state`, `detail` | Registry |
| `tool.started` | `turn_id`, `tool`, `risk` | Registry |
| `tool.finished` | `turn_id`, `tool`, `ok`, `duration_ms` | Registry |
| `confirmation.requested` | `pending_id`, `tool`, `risk` | Core |
| `confirmation.resolved` | `pending_id`, `approved` | Core |
| `voice.state` | `state`, `reason` | Voice |
| `voice.transcript` | `text`, `final` | Voice |
| `robot.event` | `type`, `payload` | Robot |
| `memory.changed` | `category`, `key` | Memory |
| `provider.changed` | `provider`, `model`, `available` | AI |

---

## 7. Autorizzazioni e capacità

### 7.1 Livelli esistenti (invariati)

- **A** ordinario: auto-approvato se configurato.
- **B** impatto significativo: conferma, salvo allow-list per nome.
- **C** sensibile/irreversibile: conferma **sempre**, anche se configurato male.
- E-stop e stop robot non passano dalla conferma.

### 7.2 Capacità per modulo

Ogni modulo dichiara le capacità che possiede, per esempio:

```text
voice:      voice.wake, voice.stt, voice.tts
mac:        mac.app, mac.file.read, mac.file.write, mac.shell.read, mac.screen
personal:   personal.calendar.read/write, personal.reminders, personal.mail.read/send
memory:     memory.read, memory.write, memory.delete
developer:  dev.read, dev.write, dev.test, dev.execute (C)
vision:     vision.ocr, vision.camera (B)
home:       home.read, home.set (B), home.scene (C)
robot:      robot.read, robot.move (C), robot.estop (A)
```

`AuthorizationBroker` verifica **modulo abilitato + capacità + rischio** prima di
eseguire. La policy esistente resta l'ultima parola; il broker non può abbassare
un livello C.

### 7.3 Conferme

- Restano in due fasi, con `pending_id`, TTL e legame all'operazione specifica.
- La UI mostra modulo, strumento, argomenti redatti, conseguenze e undo.
- La voce può confermare sì/no, ma non autorizza operazioni generiche.
- Revoca: disabilitare un modulo o una capacità deve impedire nuove esecuzioni;
  le conferme pendenti del modulo vengono annullate.

---

## 8. Provider IA e routing

### 8.1 Interfaccia

`AIProvider` esistente (`chat`, `status`) resta. Si aggiunge:

```python
@dataclass(frozen=True)
class ProviderCapability:
    text: bool
    vision: bool = False
    streaming: bool = False

class ProviderRegistry:
    def register(self, name, provider, capability): ...
    def select(self, task: str) -> AIProvider: ...
    def status(self) -> Dict[str, Any]: ...
```

### 8.2 Routing

- `text` → provider configurato (Ollama, Groq, OpenAI-compat, offline).
- `vision` → provider visivo gratuito, **solo se configurato e disponibile**;
  altrimenti Vision resta OCR.
- `fallback` → offline, mai un servizio online a pagamento.
- La UI mostra provider configurato, disponibile, modello selezionato e modello
  effettivamente in uso; un provider non disponibile non viene mostrato come attivo.

### 8.3 Gratuità

Nessun provider a pagamento obbligatorio. I preset online restano spenti per
default, con consenso esplicito e limiti documentati. OpenCode usa il modello
configurato dall'utente: Amy non lo impone.

---

## 9. Memoria

### 9.1 Categorie

| Categoria | Contenuto | Esempi |
| --- | --- | --- |
| `conversation` | contesto della sessione | domande in sospeso, argomenti |
| `personal` | preferenze e abitudini | città, stile di risposta |
| `project` | progetti, architetture, decisioni | amy_brain, robot, MQTT |
| `operational` | operazioni e risultati | ultimo test, errori, attività |

### 9.2 Schema proposto

Nuova tabella `memory_items` (senza eliminare `facts`):

```sql
CREATE TABLE memory_items (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL DEFAULT 0.5,
  verified INTEGER DEFAULT 0,
  tags TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT
);
CREATE UNIQUE INDEX memory_items_category_key ON memory_items(category, key);
```

Migrazione: copiare `facts` in `memory_items` con `category='personal'`,
`verified=1` se fornito dall'utente; mantenere `facts` in lettura per compatibilità.

### 9.3 Regole

- Niente password, chiavi o token.
- Distinguere verificato/ipotesi (`verified`, `confidence`).
- Ricerca per testo/tag; scadenza e rotazione configurabili.
- L'utente può consultare, modificare, cancellare ed esportare.

---

## 10. Interfaccia

### 10.1 Identità

Resta la dashboard «Amy Core»: dark, nero/blu navy, ciano, blu elettrico, testi
bianchi, nucleo animato, chat, pannelli. Nessun CDN, nessun `innerHTML`, CSP.

### 10.2 Nuovo pannello moduli

Ogni modulo mostra:

- nome e descrizione breve;
- stato reale (`disabled`, `initializing`, `ready`, `busy`, `degraded`, `offline`,
  `error`);
- disponibilità e dettaglio (es. «STT assente», «broker non configurato»);
- interruttore abilita/disabilita;
- impostazioni specifiche (link al pannello);
- strumenti posseduti e livello di rischio massimo.

API proposta:

| Metodo | Percorso | Funzione |
| --- | --- | --- |
| GET | `/api/modules` | elenco moduli e stato |
| GET | `/api/modules/{name}` | dettaglio e configurazione |
| POST | `/api/modules/{name}/enabled` | abilita/disabilita |
| GET | `/api/events` | eventi recenti (polling) o SSE |
| GET | `/api/logs` | log recenti redatti |
| GET | `/api/permissions` | capacità e allow-list |
| POST | `/api/permissions/revoke` | revoca |

`/api/state` mantiene i campi attuali e aggiunge `modules` per compatibilità.

### 10.3 Stati del nucleo

Gli stati esistenti (idle, listening, processing, speaking, waiting_confirmation,
error, offline, conversation, interrupted) restano. Il pannello moduli è separato
dal nucleo per non confondere stato vocale e stato dei moduli.

---

## 11. Configurazione

### 11.1 Versione e migrazioni

```json
{
  "config_version": 2,
  "modules": {
    "voice": {"enabled": true},
    "mac_control": {"enabled": true},
    "personal": {"enabled": true},
    "memory": {"enabled": true},
    "developer": {"enabled": false},
    "vision": {"enabled": true, "camera": false, "describe": false},
    "home": {"enabled": false},
    "robot": {"enabled": true}
  }
}
```

- Migrazione idempotente da `config_version` assente a 2; backup del file.
- Le chiavi esistenti (`voice`, `robot`, `ai`, `security`, …) restano valide.
- Ogni modulo valida la propria sezione e dichiara i default.

### 11.2 Segreti

Restano in `~/.amy/secrets.json` (`0600`) o variabili d'ambiente. I moduli ricevono
solo il segreto che serve, tramite `ModuleContext`.

---

## 12. Struttura target (incrementale)

```text
amy/
├── core/                 # Amy Core (orchestrator, modules, status, config)
├── shared/               # Module, EventBus, errori, tipi, logging
├── infra/                # storage, secrets, provider registry
├── security/             # policy, authorization, audit, risk
├── modules/
│   ├── voice/
│   ├── mac_control/
│   ├── personal/
│   ├── memory/
│   ├── developer/
│   ├── vision/
│   ├── home/
│   └── robot/
├── ui/                   # server e statici
└── macos/                # integrazioni di sistema (può restare trasversale)
```

**Nota:** questa è la destinazione, non il primo passo. La migrazione iniziale
crea `shared/` e `modules/` come **adapter** che importano il codice esistente;
i file vengono spostati solo dopo che i test sono verdi e gli shim funzionano.

---

## 13. Cosa non fare

- Non riscrivere `Assistant`, `VoiceService`, `MemoryStore`, simulatore o app Swift.
- Non spostare tutti i file in un'unica operazione.
- Non introdurre microservizi, code distribuite, Docker o database esterni.
- Non rendere obbligatorio un provider online o un modello pesante.
- Non dare a un modulo accesso diretto alle implementazioni interne di un altro.
- Non eliminare i livelli A/B/C o l'audit.
- Non modificare la catena di sicurezza robotica senza hardware e test dedicati.

---

## 14. Criteri di successo dell'architettura

1. Ogni modulo ha manifest, stato, ciclo di vita e test di contratto.
2. Un modulo disabilitato non registra strumenti e non blocca gli altri.
3. `/api/state` e la dashboard mostrano lo stato reale dei moduli.
4. Le autorizzazioni sono applicate dal codice, non dal prompt.
5. La memoria supporta categorie e progetti senza perdere i fatti esistenti.
6. Vision e Smart Home possono restare spenti senza degradare il resto.
7. Il robot non collegato non impedisce l'uso del Mac.
8. Tutti i 376 test esistenti continuano a passare; i nuovi test coprono i contratti.
9. Nessuna dipendenza a pagamento e nessun servizio obbligatorio.
10. La documentazione distingue verificato, ipotesi e proposte.
