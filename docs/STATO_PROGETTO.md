# Stato del progetto

Ultima verifica: **31 ottobre 2026**. Ogni voce è separata tra ciò che è stato
eseguito davvero, ciò che è implementato ma non verificato, ciò che è sperimentale e
ciò che è solo pianificato.

## 1. Ambiente della verifica

| Elemento | Valore osservato |
| --- | --- |
| Sistema | macOS 26.7.1 |
| Architettura | x86_64 |
| Python | 3.9.6 |
| Provider IA | configurato Ollama `qwen2.5-coder:14b`; server non in esecuzione all'ultima verifica, fallback offline attivo |
| TTS | comando `say`, voce italiana `Alice` |
| STT | non installato (`whisper-cli` assente) |
| Registratore | non installato (`ffmpeg` e `sox` assenti) |
| Robot | simulatore locale; nessun hardware collegato |
| MQTT | `paho-mqtt` disponibile, ma nessun broker verificato |
| Test | 168 test, tutti superati, più il self-test dell'app nativa |
| Applicazione | «Amy Core.app» compilata in locale e installata in `~/Applications` |
| Controllo versione | nessun repository Git inizializzato in questa verifica |

## 2. Implementato e verificato

- Configurazione in `~/.amy/config.json`, override da variabili d'ambiente,
  segreti da `~/.amy/secrets.json`, redazione nei log.
- CLI: `init`, `doctor`, `tools`, `config`, `chat`, `ask`, `memory`, `robot`,
  `voice`, `serve`.
- Provider Ollama con richiesta reale riuscita in una prova precedente; all'ultima
  verifica il server non era in esecuzione e Amy è ricaduta sul fallback offline
  senza fingere che il modello fosse disponibile.
- Interprete offline con comandi italiani frequenti.
- Fallback provider con stato esposto correttamente.
- Vincolo solo-gratuito **globale e permanente**: default locale, fallback offline,
  endpoint OpenAI-compatible remoto bloccato senza `allow_remote=true`, controllo
  «Costi IA» in `amy doctor`.
- Audit delle dipendenze: nessuna dipendenza Python obbligatoria, solo `paho-mqtt`
  opzionale, nessun host IA commerciale cablato, nessun CDN nella dashboard.
- Test `tests/test_free_only.py` che impediscono l'introduzione di dipendenze
  obbligatorie o configurazioni a pagamento.
- Orchestrazione con validazione schema, limite passaggi, conferme in due fasi e
  registrazione di strumenti inesistenti/argomenti invalidi.
- Policy A/B/C: A automatico, B su conferma o allow-list, C sempre su conferma.
- E-stop e stop robot non bloccati da conferma.
- 34 strumenti registrati e validati.
- File confinati nelle radici, deny-list per percorsi sensibili, backup prima della
  sovrascrittura, cestino recuperabile.
- Shell a enum chiuso di sola lettura, senza `shell=True`.
- `web.fetch` con blocco di indirizzi privati/loopback/link-local e limite di
  dimensione.
- Memoria SQLite con sessioni, messaggi, fatti, attività, eventi robotici.
- Audit append-only JSONL con redazione.
- TTS macOS e sintesi su file verificata da `amy doctor` (58.276 byte).
- Dashboard locale «Amy Core» con chat reale, cronologia, conferme in due fasi,
  nucleo a otto stati derivati da segnali reali, informazioni di sistema locali,
  pannelli motore IA/voce/robot/memoria/attività/strumenti, E-stop software e stop.
- Applicazione macOS nativa «Amy Core» (Swift, AppKit, WebKit): finestra propria,
  icona nel Dock generata localmente, menu, schermo intero nativo, avvio e chiusura
  del backend locale, heartbeat anti-orfano. Verificata con self-test end-to-end:
  dashboard montata, messaggio inviato dal DOM, risposta in chat, backend chiuso.
- Il backend locale si chiude da solo entro ~10 s se l'app viene uccisa con
  SIGKILL: nessun processo orfano.
- Informazioni di sistema reali via libreria standard (`macOS`, architettura, Python,
  CPU, carico, disco) esposte in `status()["system"]`.
- Stato voce con `speaking` reale, usato dalla UI per lo stato di sintesi.
- API HTTP locale e protezioni di base: CSP, `X-Frame-Options`, nessun CDN,
  nessun `innerHTML`.
- Bind della dashboard limitato a loopback salvo consenso esplicito.
- Simulatore robotico protocollo v1: TEST iniziale, calibrazione assente, ACK/NACK,
  deduplicazione, sequenza, limiti, watchdog, E-stop.
- Test suite: 168 test superati, inclusi sicurezza, protocollo, server, UI statica,
  app nativa, watchdog del server, cache TTS, sistema locale, servizio vocale,
  voce, provider e vincolo gratuito.

## 3. Implementato ma non verificato in questo ambiente

| Area | Perché non è verificata | Cosa è stato verificato |
| --- | --- | --- |
| Movimento robot fisico | Nessun robot collegato | Solo simulatore; ogni esito dichiara `simulated` e nessun movimento fisico |
| Link MQTT | Nessun broker/robot configurato | Codice e test di protocollo; nessuna connessione reale |
| Riconoscimento vocale | Mancano registratore e motore STT | TTS e stato `ready_for_voice_commands=false` |
| Microfono della dashboard | Stessi limiti dello STT | Endpoint testato con voce finta, non con audio reale |
| Wake word audio | Non esiste un motore audio dedicato | Rilevamento testuale dopo trascrizione |
| Uso prolungato | Non testato per ore/giorni | Test unitari e smoke test brevi |
| Verifica visiva della finestra dell'app | Non ispezionata a mano | Verifica programmatica: pagina montata, invio reale, risposta in chat, chiusura del backend |
| Notifiche e Dock dell'app | Solo icona e menu di base | Bundle firmato ad-hoc e avviato dal Finder |

## 4. Sperimentale

- Trasporto `robot.transport = "mqtt"`. Il codice esiste, ma non è stato provato su
  un broker reale né su un Raspberry Pi.
- Il link MQTT diretto dal Mac al broker è una deviazione consapevole
  dall'architettura canonica in cui il Pi è l'autorità MQTT. Va trattato come prova
  di laboratorio.
- Il reset E-stop via MQTT è implementato come richiesta al nodo, ma non è stato
  verificato su hardware.

## 5. Pianificato, non implementato

- Wake word audio dedicata (rilevamento locale prima della trascrizione).
- Installazione guidata di `ffmpeg`/STT con verifica automatica.
- Test end-to-end su Raspberry Pi e broker MQTT reale.
- Calibrazione meccanica e verifica dei limiti reali del robot.
- Autenticazione o token per la dashboard, se mai si vorrà esporla in rete.
- Controllo vocale bidirezionale continuo con interruzione affidabile su hardware.
- Packaging/installer e servizio di avvio automatico.
- Metriche e rotazione della memoria a lungo termine.

## 6. Non supportato per scelta

- Comandi GPIO, PWM, tensione o controllo diretto dei servi.
- Shell arbitraria.
- Cancellazione definitiva dei file tramite strumenti.
- Registrazione audio in background non richiesta.
- Auto-approvazione del livello C.
- Uso della dashboard su rete pubblica.
- Invio di segreti al modello o nei log.

## 7. Rischi aperti

1. **Hardware reale mai validato.** Il simulatore non dimostra la sicurezza fisica.
2. **MQTT non validato.** Un ACK non è un completamento verificato.
3. **Voce incompleta.** Senza STT/registratore, l'uso è testuale.
4. **Dashboard senza autenticazione.** Mitigata dal bind locale, non adatta alla rete.
5. **SSRF con DNS lookup.** La risoluzione è controllata prima della richiesta, ma
   non è una difesa contro ogni forma di DNS rebinding.
6. **Timeout strumenti via thread.** Un thread bloccato non viene terminato con la
   forza.
7. **Prompt injection.** Il prompt istruisce a trattare file e web come dati non
   attendibili, ma la difesa principale resta la policy nel codice.
8. **Endpoint IA remoto.** Se l'utente abilita `allow_remote`, Amy non può verificare
   da sola che il servizio sia gratuito, che non richieda carta o che i limiti siano
   sostenibili. La responsabilità è esplicita e documentata in
   [GRATUITO.md](GRATUITO.md).

## 8. Come verificare lo stato

```bash
python3 -m compileall -q amy tests
python3 -m unittest discover -s tests -t . -v
python3 -m amy doctor
python3 -m amy ask "che ore sono?" --offline
```

Per una verifica reale del provider:

```bash
python3 -m amy ask "rispondi solo con: ciao"
```

Per il robot, senza hardware:

```bash
python3 -m amy robot status
python3 -m amy robot ping
```

Non usare questi comandi per affermare che il robot fisico funziona.
