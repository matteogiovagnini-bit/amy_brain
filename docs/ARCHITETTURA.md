# Architettura di Amy Brain

Questo documento descrive il cervello Mac. Per protocollo robotico, elettronica,
firmware e calibrazione la fonte canonica resta `../amy/docs/`.

## 1. Posizione nel sistema

```text
┌──────────────────────────────────────────────────────────────┐
│ macOS — amy_brain (L2)                                       │
│                                                              │
│  CLI / Dashboard locale                                      │
│        │                                                     │
│        ▼                                                     │
│  Assistant ──► provider IA (Ollama / OpenAI-compat / offline)│
│        │                                                     │
│        ├──► policy A/B/C ──► conferma utente                 │
│        ├──► registry strumenti ──► macOS / file / web / voce │
│        ├──► memoria SQLite + audit JSONL                     │
│        └──► robot link ──► simulatore locale                 │
│                         └─► MQTT sperimentale ──► robot      │
└──────────────────────────────────────────────────────────────┘
```

`amy_brain` non parla direttamente con GPIO, PWM o servi. Invia comandi di alto
livello. Il robot reale ha una propria catena di sicurezza hardware descritta in
`../amy/docs/07_sicurezza.md`.

## 2. Moduli

| Modulo | Responsabilità |
| --- | --- |
| `amy/core/config.py` | configurazione, override ambiente, segreti, percorsi |
| `amy/core/assistant.py` | turno conversazionale, validazione, conferme, orchestrazione |
| `amy/core/prompts.py` | prompt di sistema e formato dei risultati strumento |
| `amy/core/logging_setup.py` | logging con redazione dei segreti |
| `amy/ai/` | provider Ollama, preset online gratuiti, compatibile OpenAI, offline, fallback |
| `amy/memory/store.py` | SQLite: sessioni, messaggi, fatti, attività, eventi |
| `amy/security/policy.py` | livelli A/B/C, path guard, richieste di conferma |
| `amy/security/audit.py` | registro append-only delle decisioni |
| `amy/tools/` | 49 strumenti registrati e validati |
| `amy/voice/` | TTS macOS, STT locale, registratore, wake word testuale, macchina a stati e conversazione continua |
| `amy/robot/` | protocollo v1, simulatore, link simulato e MQTT |
| `amy/ui/server.py` | API HTTP locale, file statici, CSP |
| `amy/ui/static/` | interfaccia «Amy Core» senza dipendenze esterne |
| `amy/core/system_info.py` | informazioni locali di sistema, sola libreria standard |
| `amy/macos/` | integrazione AppleScript, incluse applicazioni, batteria, Calendar, Promemoria e Mail |
| `apps/AmyCore/` | applicazione macOS nativa (Swift, AppKit, WebKit), build e self-test |

## 3. Flusso di un turno

1. L'utente scrive o pronuncia una richiesta.
2. `Assistant.handle()` crea o riprende la sessione, salva il messaggio utente e
   costruisce il contesto: prompt di sistema, catalogo strumenti, fatti, storia
   recente, contesto robot.
3. Il provider risponde. Amy accetta due forme:
   - testo semplice;
   - JSON `{"say": "...", "action": {"tool": "...", "args": {...}}}`.
4. `parse_response()` estrae l'azione. Un JSON malformato non viene eseguito.
5. Il registry verifica che lo strumento esista e che gli argomenti rispettino lo
   schema JSON. Strumenti inesistenti e argomenti invalidi vengono registrati come
   attività fallite e restituiti al modello come risultato, senza esecuzione.
6. `PolicyEngine.evaluate()` decide in base al rischio:
   - **A** ordinario: auto-approvato se configurato;
   - **B** impatto significativo: conferma, salvo auto-approvazione esplicita per
     nome;
   - **C** sensibile/irreversibile: conferma sempre, anche se configurato male.
7. Se serve conferma, il turno viene sospeso e restituito con `pending`. Nessuna
   esecuzione avviene prima della risposta.
8. Alla conferma, `resolve_confirmation()` esegue o annulla e riprende il turno.
9. Ogni esecuzione produce una riga in `activities` e eventi in `audit.jsonl`.
10. Il risultato viene formattato come dato non attendibile e restituito al modello,
    che chiude il turno in italiano.

Il numero massimo di passaggi è `ai.max_tool_steps` (default 4). Al raggiungimento
del limite Amy si ferma con `error_code="tool_step_limit"`.

## 4. Protocollo d'azione

Forma richiesta:

```json
{
  "say": "Controllo l'ora.",
  "action": {
    "tool": "time.now",
    "args": {}
  }
}
```

Regole:

- una sola azione per turno;
- solo strumenti e parametri presenti nel catalogo;
- nessun campo aggiuntivo;
- se non serve uno strumento, testo semplice;
- nessuna dichiarazione di completamento senza un risultato positivo.

La risposta del modello non è mai eseguita come codice.

## 5. Provider IA

`amy/ai/factory.py` costruisce il provider in base a `ai.provider`:

- `ollama`: API locale `http://127.0.0.1:11434`, modello configurabile;
- `groq` (e futuri preset in `amy/ai/presets.py`): servizio online **gratuito**
  verificato, compatibile OpenAI, attivo solo con `ai.online.consent = true`;
- `openai`: endpoint compatibile OpenAI, pensato per un server **locale**; un
  endpoint pubblico richiede `ai.openai.allow_remote=true` e non è mai il default;
- `offline`: interprete deterministico di comandi italiani frequenti.

Il progetto è vincolato a strumenti gratuiti: nessun provider a pagamento è
obbligatorio, e il fallback predefinito è `offline`, non un servizio cloud. Un
preset online non può essere usato come fallback. Dettagli, limiti e licenze in
[GRATUITO.md](GRATUITO.md).

I preset vivono in un elenco chiuso e versionato (`amy/ai/presets.py`) con endpoint,
modello, licenza, condizioni del piano gratuito, privacy e data di verifica. La
chiave non entra mai nella configurazione: arriva da variabile d'ambiente o da
`~/.amy/secrets.json` (`0600`). Senza chiave il primario risulta non disponibile, non
«disponibile ma lento».

Se il provider primario fallisce, `FallbackProvider` usa il fallback configurato
(default `offline`) e riporta il motivo. Lo stato del provider espone
`available`, `model_installed`, stato del primario e del fallback. La dashboard
mostra il fallback senza nasconderlo.

L'offline non è un modello linguistico: è un insieme di regole. Non va presentato
come equivalente a Ollama.

## 6. Memoria

SQLite locale in `~/.amy/amy.db` (configurabile). Tabelle:

- `sessions`, `messages`: conversazione;
- `facts`: preferenze e fatti duraturi;
- `activities`: esito degli strumenti, con rischio e risultato;
- `robot_events`: eventi robotici.

La storia salvata contiene solo messaggi utente/assistente, non i JSON interni delle
azioni. Gli argomenti vengono redatti prima della scrittura. La memoria è
esportabile e cancellabile da CLI.

## 7. Sicurezza

La sicurezza non dipende dal prompt. È nel codice:

- schema JSON rigoroso;
- path guard con radici, symlink risolti e deny-list;
- shell a enum chiuso, senza `shell=True`;
- web con blocco di loopback, link-local e reti private;
- C mai automatico;
- audit append-only;
- dashboard locale «Amy Core» senza CDN, con CSP, nessun `innerHTML` e nessuno
  stile inline; gli stati derivano da segnali reali del backend;
- applicazione macOS nativa: il backend resta legato a `127.0.0.1`, non viene
  esposto in rete e non resta orfano se l'app muore (heartbeat con chiusura
  automatica).

Dettagli: [SICUREZZA.md](SICUREZZA.md).

## 8. Robot

Due trasporti:

- `simulated` (default): simulatore in-process, sempre trasparente
  (`simulated: true`, `physical_motion: false`);
- `mqtt`: link sperimentale, non verificato su hardware reale.

Il simulatore implementa envelope v1, ACK/NACK, deduplicazione per `req_id`,
sequenza per destinatario, limiti per giunto, watchdog e latch E-stop. Parte in
modalità `TEST` e con calibrazione assente: `READY` viene rifiutato finché
`zero_offset_deg` non è impostato.

Dettagli: [ROBOTICA.md](ROBOTICA.md).

## 9. Voce

- TTS: comando `say` di macOS, voce italiana configurabile.
- STT: locale, `faster-whisper` (CPU int8) con ripiego su CLI Whisper e whisper.cpp.
- Registratore: `sounddevice` (in-process, WAV 16 kHz mono) con ripiego su `ffmpeg`
  o `sox`.
- Wake word: rilevamento **testuale** dopo la trascrizione, non un motore audio
  dedicato. Confronto tollerante ristretto al primo token o dopo un prefisso di
  richiamo.
- Registrazione in background: possibile su richiesta esplicita o con avvio
  automatico abilitato (`voice.wake_word.start_on_launch`, default attivo).
- Messaggio di avvio: pronunciato all'avvio della dashboard con la sola sintesi
  locale, senza registrazione. Il testo viene dalla configurazione
  (`voice.startup_greeting_text`) ed è disattivabile con
  `voice.startup_greeting = false` o `AMY_STARTUP_GREETING=0`.

Dettagli: [VOCE.md](VOCE.md).

## 10. Dashboard

Server HTTP con `ThreadingHTTPServer`, solo `127.0.0.1` per default. API principali:

| Metodo | Percorso | Funzione |
| --- | --- | --- |
| GET | `/api/state` | stato completo |
| GET | `/api/transcript` | cronologia sessione |
| GET | `/api/pending` | conferme in attesa |
| GET | `/api/tools` | catalogo strumenti |
| GET | `/api/activities` | attività recenti |
| GET | `/api/robot/events` | eventi robotici |
| POST | `/api/chat` | messaggio |
| POST | `/api/new_session` | nuova sessione |
| POST | `/api/confirm` | autorizza/annulla |
| POST | `/api/speak` | sintesi vocale |
| POST | `/api/voice/stop` | interrompe la voce |
| POST | `/api/voice/listen` | ascolto singolo |
| POST | `/api/voice/greet` | ripete il messaggio di avvio |
| POST | `/api/voice/wake/start` | avvia l'ascolto continuo della wake word |
| POST | `/api/voice/wake/stop` | ferma l'ascolto continuo |
| POST | `/api/robot/estop` | E-stop software |
| POST | `/api/robot/stop` | arresto controllato |

Non c'è autenticazione. Per questo il bind non-loopback richiede
`ui.allow_remote=true` ed è sconsigliato.

## 11. Limiti noti

- Nessuna verifica su robot fisico.
- MQTT sperimentale.
- STT non installato in questo ambiente.
- Wake word non audio-first.
- Dashboard senza autenticazione.
- `web.fetch` non esegue JavaScript e ha una protezione SSRF di tipo DNS lookup;
  non è una sandbox di rendering.
- Il timeout degli strumenti usa thread: non può interrompere con la forza un
  thread bloccato, anche se gli strumenti hanno timeout interni.
