# Analisi del progetto esistente

**Fase 1 — audit architetturale**
Data: **7 novembre 2026**
Commit analizzato: `dab07ed` («Screenshot e OCR locale con Vision»)
Metodo: lettura del codice e della documentazione, esecuzione della suite, ispezione
del catalogo strumenti e delle API. Nessuna modifica al codice in questa fase.

---

## 1. Sintesi esecutiva

Amy è oggi un assistente personale funzionante sul Mac, con un nucleo Python
(`Assistant`), 57 strumenti, 8 aree funzionali di fatto già presenti, una dashboard
locale e un'app macOS nativa. La sicurezza è nel codice (livelli A/B/C, path guard,
shell a enum chiuso, audit). La voce locale funziona con wake word testuale,
conversazione continua, barge-in con cuffie e conferma vocale.

Il progetto **non è monolitico**: è già diviso in package con responsabilità chiare
(`core`, `ai`, `tools`, `voice`, `robot`, `memory`, `security`, `ui`, `macos`).
Il problema non è quindi «riscrivere», ma **dare un contratto esplicito** a ciò che
oggi è separato solo per convenzione:

- non esiste un'astrazione `Module` con ciclo di vita, stato e capacità;
- non esiste un bus di eventi interno;
- il registry degli strumenti è piatto e globale;
- `Assistant` è un *god object* (orchestrazione, contesto, conferme, stato,
  provider, robot, calendario);
- la dashboard non conosce lo stato dei moduli e non li può abilitare/disabilitare;
- la memoria è limitata a fatti, sessioni, attività ed eventi robotici;
- Vision è solo OCR di schermo; Smart Home non esiste;
- la documentazione ha derive (numero strumenti, data di verifica, limiti superati).

La priorità è **conservare** ciò che funziona e introdurre un'architettura a moduli
**per passi**, con adapter e shim, senza spostare tutto in una volta.

---

## 2. Stato reale e metriche

| Elemento | Valore osservato |
| --- | --- |
| Commit | `dab07ed` |
| File tracciati | 124 |
| Commit totali | 25 |
| Codice Python | 61 file, **12.770 righe** |
| Codice Swift | **1.219 righe** (`AmyCoreApp.swift` + strumenti) |
| JavaScript dashboard | **1.786 righe** (`amy/ui/static/app.js`) |
| Test | **376 test**, tutti superati, 5.242 righe |
| Documentazione | **4.845 righe** (`docs/` + `AGENTS.md`, `OpenCode.md`, `README.md`) |
| Strumenti registrati | **57** |
| Sistema | macOS 26.7.1, x86_64 (MacBook Pro Intel) |
| Python | 3.9.6 |
| Provider | `groq` / `openai/gpt-oss-120b` (piano Free), fallback `offline` |
| Voce | `faster-whisper` `small`, `sounddevice`, `say` / Alice |
| Robot | solo simulatore; MQTT sperimentale non verificato |
| App | `~/Applications/Amy Core.app`, backend su `127.0.0.1:8765` |

Verifica eseguita: `python3 -m unittest discover -s tests -t .` → **376 OK**;
`python3 -m amy tools` → **57 strumenti**.

---

## 3. Struttura attuale del codice

```text
amy/
├── cli.py                     CLI (init, doctor, providers, secret, tools, config,
│                              chat, ask, memory, robot, voice, serve)
├── core/
│   ├── assistant.py           turno, parse JSON, conferme, stato, calendario
│   ├── config.py              default, merge, segreti, validazione, percorsi
│   ├── prompts.py             prompt di sistema, catalogo testuale, risultati
│   ├── errors.py              errori applicativi con codici
│   ├── logging_setup.py       logging con redazione
│   ├── restart.py             riavvio app nativa con helper staccato
│   └── system_info.py         informazioni locali per la dashboard
├── ai/
│   ├── base.py                interfaccia AIProvider
│   ├── factory.py             provider primario + fallback
│   ├── ollama.py              Ollama locale
│   ├── openai_compat.py       endpoint compatibili OpenAI, retry, preset
│   ├── presets.py             preset gratuiti versionati
│   └── offline.py             interprete deterministico
├── tools/
│   ├── base.py                ToolSpec, ToolContext, ToolResult, timeout
│   ├── registry.py            registro piatto + esecuzione
│   ├── builtin.py             composizione di tutti i gruppi
│   ├── apps.py  files.py  shell.py  system.py  web.py
│   ├── calendar_tools.py  reminders_tools.py  mail_tools.py
│   ├── memory_tools.py  voice_tools.py  robot_tools.py
│   ├── opencode_tools.py  screen_tools.py
│   └── schema.py              validazione JSON
├── voice/
│   ├── service.py             ciclo wake word, conversazione, barge-in, conferme
│   ├── state.py               macchina a stati
│   ├── recorder.py            sounddevice, VAD, timeout HAL
│   ├── stt.py                 faster-whisper / CLI / whisper.cpp
│   ├── tts.py                 `say`, intervalli, testo corrente
│   └── wakeword.py            rilevamento testuale tollerante
├── memory/store.py            SQLite: sessioni, messaggi, fatti, attività, eventi
├── security/
│   ├── policy.py              A/B/C, path guard, conferme, TTL
│   ├── audit.py               JSONL append-only con redazione
│   └── risk.py                RiskLevel
├── robot/
│   ├── protocol.py            envelope v1, limiti, validazione
│   ├── simulator.py           simulatore, ACK/NACK, watchdog, E-stop
│   └── links.py               SimulatedLink, MqttRobotLink
├── macos/
│   ├── applescript.py         app, batteria, osascript, system info, processi
│   ├── calendar.py  reminders.py  mail.py  screen.py
├── ui/
│   ├── server.py              HTTP locale, API, statici, watchdog
│   └── static/                index.html, app.js, style.css
└── apps/AmyCore/              app Swift, build.sh, self-test, OCR helper
```

### 3.1 Come viene composto un turno

```text
utente (CLI o /api/chat)
  → Assistant.handle
  → _build_messages (prompt sistema + catalogo testuale + fatti + storia)
  → provider.chat (Groq / Ollama / offline)
  → parse_response (testo o JSON azione)
  → registry.execute (schema + timeout)
  → policy.evaluate (A/B/C)
  → eventuale pending + resolve_confirmation
  → memoria + audit
  → risultato al modello → risposta finale
```

Il flusso è solido ed è la parte da **non** rompere.

---

## 4. Cosa esiste e funziona (verificato)

### 4.1 Nucleo e orchestrazione
- Turno conversazionale con validazione schema, limite passaggi (4), conferme in
  due fasi, registrazione di azioni fallite.
- Prompt italiano con regole di non invenzione e formato JSON.
- Memoria SQLite, audit JSONL, redazione dei segreti.
- Configurazione con default, merge, override ambiente, segreti `0600`.

### 4.2 Provider IA
- Ollama locale, endpoint OpenAI-compatibile, preset gratuiti (`groq`), offline.
- Fallback `offline`; un preset online non può essere fallback.
- Retry sui limiti gratuiti con attesa suggerita dal servizio.
- Stato provider onesto (`available`, `model_installed`, motivo del fallback).

### 4.3 Mac Control
- 57 strumenti: applicazioni, file, shell in enum chiuso, sistema, web, memoria,
  voce, calendario, promemoria, mail, OpenCode, schermo/OCR.
- File confinati nelle radici, deny-list, backup, cestino recuperabile.
- `files.open`, `files.grep`, `system.info` con carico CPU e RAM, `system.processes`
  corretto (bug `ps -r/-m` e decimali con virgola risolto il 6 novembre 2026).
- `screen.capture` e `screen.read` con OCR locale Vision.

### 4.4 Personal Manager (parziale)
- Calendario: lista, eventi, creazione, eliminazione; riquadro «Prossimi
  appuntamenti» con endpoint aggregato.
- Promemoria: liste, elenco, creazione, completamento, eliminazione.
- Mail: account, cassette, metadati, lettura corpo (B), invio (C).

### 4.5 Voce
- Wake word testuale «Amy», conversazione continua, timeout con «Sei ancora lì?»,
  stop vocale, conferma vocale sì/no, barge-in durante la sintesi.
- VAD adattivo per non tagliare la dettatura.
- Echo guard half-duplex e filtro anti-eco testuale.
- Stato vocale centralizzato (`VoiceStateMachine`) esposto alla UI.

### 4.6 Robot
- Protocollo v1, simulatore con ACK/NACK, deduplicazione, sequenza, limiti,
  watchdog, E-stop, modalità TEST.
- Link MQTT implementato ma **non verificato** su broker/hardware.

### 4.7 Interfaccia
- Dashboard locale con nucleo a stati reali, chat, conferme, pannelli, calendario.
- App macOS nativa con menu, Dock, schermo intero, heartbeat, self-test, watchdog,
  riavvio programmato.
- CSP, nessun CDN, nessun `innerHTML`, bind loopback.

### 4.8 Vincolo gratuito
- Nessuna dipendenza Python obbligatoria; `paho-mqtt` opzionale.
- Test `test_free_only.py`; preset gratuiti versionati con limiti e licenza.
- OpenCode 2 e `opencode2` sono open source; il modello usato è configurato a parte.

---

## 5. Cosa è incompleto o manca

| Area | Stato | Dettaglio |
| --- | --- | --- |
| Moduli come contratto | **Manca** | Nessuna classe `Module`, nessun ciclo di vita, nessuno stato per modulo |
| Eventi interni | **Manca** | La UI interroga lo stato; nessun bus pub/sub |
| Abilitazione moduli | **Manca** | Solo `voice.enabled`; gli altri moduli sono sempre attivi |
| Memoria a lungo termine | **Parziale** | Solo `facts`, sessioni, attività; niente categorie, progetti, note, ricerca, verifica |
| Task manager / note | **Manca** | Nessuna tabella o strumento per attività e note personali |
| Calendario | **Parziale** | Nessun aggiornamento evento, ricorrenze, partecipanti, fusi orari |
| Vision | **Parziale** | Solo OCR di schermo; nessuna telecamera, nessuna descrizione immagine |
| Smart Home | **Manca** | Nessun modulo domotico; solo MQTT robot |
| Developer Assistant | **Parziale** | OpenCode esterno; nessun test runner/diff/analisi nativi |
| Script/automazioni | **Assente per scelta** | Shell a enum chiuso; OpenCode copre con conferma |
| Wake word audio | **Assente** | Rilevamento sul testo trascritto |
| AEC / full-duplex | **Assente** | Barge-in affidabile solo con cuffie |
| UI moduli | **Assente** | Nessun pannello stato/abilitazione per modulo |
| Log e permessi in UI | **Parziale** | Audit su file, non consultabile dalla dashboard |
| Config versionata | **Assente** | Merge dei default, nessuna versione/migrazione |
| Installer / avvio automatico | **Assente** | App installata a mano, permessi TCC manuali |
| Test hardware | **Assente** | Robot fisico e MQTT mai verificati |
| Test end-to-end UI | **Parziale** | Self-test nativo; test UI statici |

---

## 6. Problemi architetturali

### P1 — `Assistant` è un god object (gravità: alta)
`core/assistant.py` contiene orchestrazione, costruzione del contesto, parse,
conferme, stato del provider, stato robot, calendario aggregato, sintesi vocale.
Ogni nuova area aumenta il file e il rischio di regressione.
**Proposta:** separare orchestrazione, stato e servizi; i moduli contribuiscono al
turno e allo stato tramite interfacce.

### P2 — Registry piatto e globale (alta)
`tools/builtin.py` registra 57 strumenti senza un proprietario. Non si sa quale
modulo possiede uno strumento, né si può disabilitare un modulo con i suoi strumenti.
**Proposta:** `ModuleRegistry` + `Module.tools()`; `builtin.py` diventa un adapter
di compatibilità.

### P3 — Nessun bus di eventi (alta)
Voce, robot, conferme, moduli e UI comunicano per polling o per chiamate dirette.
Non c'è un modo uniforme per notificare `voice.state`, `tool.started`,
`confirmation.requested`, `robot.event`.
**Proposta:** `EventBus` in-process, thread-safe, con sottoscrizioni e storico
limitato; la UI può usare polling o SSE.

### P4 — Stato aggregato in un dizionario monolitico (media)
`Assistant.status()` costruisce tutto: provider, sistema, memoria, voce, robot,
strumenti, config. Ogni modulo non può contribuire autonomamente.
**Proposta:** `StatusAggregator` con `module.status()`; `/api/state` mantiene la
compatibilità e aggiunge `modules`.

### P5 — Doppia implementazione delle informazioni di sistema (media)
`core/system_info.py` (dashboard) e `macos/applescript.system_info` (strumento)
espongono campi diversi. La dashboard non mostra RAM libera; lo strumento non
mostra il carico.
**Proposta:** un solo `SystemService` con schema unico; entrambi lo usano.

### P6 — Duplicazione dell'aggregazione calendario (media)
`Assistant.upcoming_events` e `GET /api/calendar/upcoming` contengono logica di
aggregazione; il riquadro UI la consuma. Va spostata nel Personal Manager.
**Proposta:** `PersonalManager.agenda()` come unica fonte.

### P7 — UI monolitica (media)
`app.js` è 1.786 righe con sezioni diverse nello stesso file; nessun pannello moduli.
**Proposta:** split progressivo in moduli JS (caricati localmente, senza bundler),
stati da `/api/modules`; mantenere stile e accessibilità.

### P8 — Configurazione senza versione (media)
I default vengono fusi, ma non c'è `config_version` né migrazione. Nuove chiavi
funzionano, ma cambi strutturali non sono tracciati.
**Proposta:** `config_version` + migrazioni idempotenti; backup prima della modifica.

### P9 — Logging senza correlazione (media)
Audit JSONL e log testuali non condividono un `turn_id`/`request_id`; difficile
seguire un turno tra Core, modulo e strumento.
**Proposta:** contesto di correlazione (`turn_id`, `module`, `tool`) in log e audit.

### P10 — Timeout degli strumenti via thread (media)
Un thread bloccato non viene terminato con la forza; il timeout restituisce errore
ma la risorsa resta occupata. Già noto in `STATO_PROGETTO`.
**Proposta:** mantenere, ma documentare per modulo; per operazioni esterne usare
timeout nativi (già fatto per subprocess e HTTP).

### P11 — Dipendenza da TCC e permessi manuali (media)
Microfono, Automazione, Registrazione schermo, Mail e Calendario richiedono
permessi concessi a mano; gli errori sono onesti ma l'onboarding è fragile.
**Proposta:** `system.settings` guidato + diagnostica `amy doctor` per modulo.

### P12 — Documentazione con derive (bassa, ma va corretta)
`docs/CONTROLLO_MAC.md` dice «35 strumenti» (oggi 57); `docs/ARCHITETTURA.md` nei
limiti dice «STT non installato» (oggi `small` è installato e verificato);
`STATO_PROGETTO` ha data 2 novembre con voci del 6 novembre.
**Proposta:** aggiornare nella fase di documentazione; un test può verificare il
conteggio strumenti citato.

### P13 — Vision limitata all'OCR (media)
Nessuna telecamera, nessuna descrizione di scena, nessun provider visivo. L'OCR
legge testo, non oggetti.
**Proposta:** modulo Vision con due capacità separate: `ocr` (locale, già pronta)
e `describe` (provider visivo gratuito, opzionale, spento per default).

### P14 — Smart Home assente (media)
Nessun modello di dispositivi, nessun broker configurabile oltre al robot, nessuna
scena. Il requisito è esplicito.
**Proposta:** modulo Home con registry dispositivi, MQTT, sensori, scene; spento
per default, nessun produttore obbligatorio.

### P15 — Personal Manager incompleto (media)
Mancano task, note, liste, ricorrenze, modifica eventi. La memoria personale non
ha categorie né verifica.
**Proposta:** tabelle `tasks`, `notes`, `memory_items`; strumenti dedicati; agenda
unificata.

### P16 — Developer Assistant delegato (media)
OpenCode è potente ma esterno; non ci sono strumenti nativi per test, diff,
analisi statica, né un report strutturato. Il rischio è che Amy non sappia cosa
OpenCode ha fatto.
**Proposta:** strumenti `dev.status`, `dev.test`, `dev.diff`, `dev.analyze` che
usano test e git in sola lettura; OpenCode resta per le modifiche.

### P17 — Nessuna sandbox per OpenCode (alta)
`opencode.run` esegue un agente con i permessi dell'utente; la conferma C non è una
sandbox. È documentato, ma va reso esplicito nel modulo Developer e nella UI.
**Proposta:** mostrare la cartella, il comando e le conseguenze nella conferma;
consentire solo radici autorizzate; valutare un `worktree` temporaneo per default.

### P18 — Test forti ma non end-to-end (media)
376 test unitari/integrati, self-test nativo, ma nessun test hardware, nessun test
prolungato, pochi test di concorrenza/eventi. La migrazione deve aggiungere test di
contratto dei moduli.

---

## 7. Duplicazioni e punti da razionalizzare

| Duplicazione | Dove | Proposta |
| --- | --- | --- |
| Informazioni di sistema | `core/system_info.py` vs `macos/applescript.system_info` | unico `SystemService` |
| Aggregazione calendario | `Assistant.upcoming_events` + `server` + UI | `PersonalManager.agenda()` |
| Stato provider | `Assistant.provider_status` + `ui/providerView` | `AIService.status()` + modulo |
| Stato voce | `VoiceService.status` + `coreView` + `voice.state` | unico stato modulo + eventi |
| Catalogo strumenti | `builtin.py` + registry + UI | `ModuleRegistry` + `/api/modules` |
| Config/percorsi | `core/config.py` + `path_guard` + moduli | `ModuleContext` condiviso |
| Errori | `AmyError` + errori di modulo | gerarchia unica + `module` nel contesto |

Non tutte sono “bug”: alcune sono strati legittimi. Vanno unificate solo dove la
duplicazione produce divergenza di dati o di stato.

---

## 8. Componenti riutilizzabili (da non riscrivere)

- `Assistant` come motore di turno, da scomporre ma non da buttare.
- `ToolSpec`/`ToolResult`/`ToolContext` e `ToolRegistry`.
- `PolicyEngine` A/B/C, `PathGuard`, `Audit`.
- `AIProvider` + `FallbackProvider` + preset gratuiti.
- `MemoryStore` SQLite (estendibile con migrazioni).
- `VoiceService`, `VoiceStateMachine`, registratore VAD, STT, TTS, wake word.
- `RobotLink`/simulatore/protocollo.
- `macos/*` (AppleScript, Calendar, Reminders, Mail, Screen/OCR).
- Server HTTP locale e dashboard; app Swift.
- Test suite e `TempAmy`.

La migrazione deve **avvolgere** questi componenti in moduli, non riscriverli.

---

## 9. Vincoli per la migrazione

1. **Compatibilità**: nessuna rottura di CLI, API, config, test.
2. **Gratuità**: nessuna dipendenza a pagamento; verificare licenze.
3. **Hardware**: Mac Intel x86_64; niente GPU NVIDIA/Apple Silicon.
4. **Sicurezza**: C mai automatico; E-stop fuori policy; path guard; shell chiusa.
5. **Onestà**: stati reali; offline dichiarato; nessun dato inventato.
6. **Documentazione**: italiano; separare verificato/ipotesi/proposte.
7. **Robot**: nessun comando diretto a GPIO/PWM; il Pi/ESP32 mantengono la sicurezza.
8. **Free-only**: OpenCode e modelli online solo se gratuiti e con consenso.

---

## 10. Conclusione dell'audit

Amy ha già il **valore funzionale** che l'architettura target deve preservare:
sicurezza nel codice, strumenti reali, voce locale, memoria, robot simulato, UI
nativa. La riorganizzazione non deve essere una riscrittura: deve introdurre
**contratti** (moduli, eventi, stato, autorizzazioni) e **adapter** attorno al
codice esistente, spostando i file solo quando i test sono verdi.

Le priorità architetturali sono, in ordine:

1. contratto `Module` + `ModuleRegistry` + `EventBus`;
2. stato moduli e `/api/modules` + pannello UI;
3. autorizzazioni per modulo (capacità) senza indebolire A/B/C;
4. memoria estesa (categorie, progetti, note, task);
5. Vision (descrivi/camera) e Smart Home come moduli spenti per default;
6. Developer Assistant nativo accanto a OpenCode;
7. documentazione allineata e test di contratto.

Nessuna modifica invasiva è stata fatta in questa fase.
