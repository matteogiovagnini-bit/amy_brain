# Stato del progetto

Ultima verifica: **2 novembre 2026**. Ogni voce è separata tra ciò che è stato
eseguito davvero, ciò che è implementato ma non verificato, ciò che è sperimentale e
ciò che è solo pianificato.

## 1. Ambiente della verifica

| Elemento | Valore osservato |
| --- | --- |
| Sistema | macOS 26.7.1 |
| Architettura | x86_64 |
| Python | 3.9.6 |
| Provider IA | `groq` (GroqCloud piano Free, `openai/gpt-oss-120b`) con chiave valida e risposta reale verificata; fallback `offline` |
| TTS | comando `say`, voce italiana `Alice` |
| STT | `faster-whisper` 1.2.1 locale, modello `small`, CPU int8, prompt comandi italiano |
| Registratore | `sounddevice` 0.5.6 su Core Audio, 16 kHz mono |
| Robot | simulatore locale; nessun hardware collegato |
| MQTT | `paho-mqtt` disponibile, ma nessun broker verificato |
| Test | 280 test, tutti superati, più il self-test dell'app nativa |
| Applicazione | «Amy Core.app» compilata in locale e installata in `~/Applications` |
| Controllo versione | repository Git pubblico su GitHub, branch `main`, primo commit `404aacf` |

## 2. Implementato e verificato

- Configurazione in `~/.amy/config.json`, override da variabili d'ambiente,
  segreti da `~/.amy/secrets.json`, redazione nei log.
- CLI: `init`, `doctor`, `providers`, `secret`, `tools`, `config`, `chat`, `ask`,
  `memory`, `robot`, `voice`, `serve`.
- Provider online gratuito verificato: preset `groq` (GroqCloud piano Free, senza
  carta di credito) con modello `openai/gpt-oss-120b`, spento per default e
  attivabile solo con `ai.online.consent = true`. La chiave si salva con
  `python3 -m amy secret set` in `~/.amy/secrets.json` (`0600`), mai nella
  configurazione o nei log.
- `amy providers` elenca preset, limiti, licenza e privacy; `amy doctor` verifica la
  chiave con `GET /models` e mostra le condizioni del piano gratuito.
- Richiesta reale al provider online verificata il 31 ottobre 2026 (`amy ask`
  risponde tramite GroqCloud Free); `amy doctor` conferma chiave valida e modello
  presente nell'elenco del servizio.
- Worker offline sempre disponibile come fallback: un preset online non può essere
  scelto come fallback.
- Provider Ollama con richiesta reale riuscita in una prova precedente; resta il
  default del repository e la scelta consigliata quando si vuole tutto locale.
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
- 38 strumenti registrati e validati.
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
  pannelli motore IA/robot/sistema/voce/memoria/attività/strumenti, E-stop software
  e stop. Il nucleo occupa l'intero palco, la chat è un satellite a destra, la barra
  comandi è centrata in fondo, lo sfondo ha un campo stellato statico e i pannelli
  informativi si sovrappongono a sinistra, con chiusura sfumata e layout verticale
  sotto 1040 px.
- Applicazione macOS nativa «Amy Core» (Swift, AppKit, WebKit): finestra propria,
  icona nel Dock generata localmente, menu, schermo intero nativo, avvio e chiusura
  del backend locale, heartbeat anti-orfano. Verificata con self-test end-to-end:
  dashboard montata, messaggio inviato dal DOM, risposta in chat, backend chiuso.
  Accetta `--snapshot` per catturare la WebView durante le verifiche visive.
- Il backend locale si chiude da solo entro ~10 s se l'app viene uccisa con
  SIGKILL: nessun processo orfano.
- Informazioni di sistema reali via libreria standard (`macOS`, architettura, Python,
  CPU, carico, disco) esposte in `status()["system"]`.
- Voce completa e locale: `sounddevice` per il microfono, `faster-whisper` per la
  trascrizione, `say` per la sintesi, wake word «Amy» sul testo trascritto.
  Verificata anche end-to-end: «Amy, che ore sono?» → comando eseguito e risposta
  pronunciata. L'ascolto continuo si avvia automaticamente all'avvio se
  `voice.wake_word.start_on_launch` è attivo (default: sì) e si ferma da solo
  dopo 20 minuti; resta disattivabile.
- Protezione dall'eco **half-duplex** nel ciclo vocale: durante la sintesi il
  microfono non registra, i frammenti che contengono la voce di Amy vengono
  scartati e dopo la risposta segue una pausa di 0,8 s
  (`voice.wake_word.echo_guard`, `voice.wake_word.echo_guard_cooldown_s`).
  Verificata dal vivo il 2 novembre 2026: con tre comandi dagli altoparlanti uno
  è stato perso durante la risposta e, forzando una sovrapposizione, il log ha
  riportato «Frammento scartato: Amy stava parlando (protezione dall'eco).».
- Strumento `system.battery`: stato reale della batteria del Mac letto con
  `pmset -g batt` (sola lettura), con percentuale, carica/scarica e tempo
  residuo; su un Mac senza batteria dichiara l'assenza senza inventare valori.
- Calendario: `calendar.list` e `calendar.events` leggono calendari ed eventi,
  `calendar.create` crea un appuntamento reale in Calendar.app via AppleScript
  (rischio B, conferma obbligatoria). Verificato il 3 novembre 2026 con un evento
  creato, riletto e rimosso; il primo uso richiede il permesso Automazione.
- Registrazione con limite di tempo: se PortAudio si blocca nel HAL di Core Audio,
  la chiamata fallisce dopo `durata + 6 s` con «Il microfono non risponde», lo stato
  espone `stuck: true` e il ciclo di wake word si ferma dichiarando il motivo.
  `amy doctor` apre il microfono per un secondo per distinguere «modulo installato»
  da «ingresso che risponde».
- Stato voce con `speaking` reale, usato dalla UI per lo stato di sintesi.
- Dashboard e app nativa resistenti agli stalli: heartbeat su coda dedicata
  (`DispatchSourceTimer`) avviato prima del backend, tolleranza del watchdog 20 s,
  controllo di salute a 6 s con 3 fallimenti, avviso «backend non risponde» come
  sheet non modale, sintesi bloccante con limite di tempo.
- API HTTP locale e protezioni di base: CSP, `X-Frame-Options`, nessun CDN,
  nessun `innerHTML`.
- Bind della dashboard limitato a loopback salvo consenso esplicito.
- Simulatore robotico protocollo v1: TEST iniziale, calibrazione assente, ACK/NACK,
  deduplicazione, sequenza, limiti, watchdog, E-stop.
- Saluto di avvio «Amy è attiva e operativa.» pronunciato dalla dashboard all'avvio
  con la sola sintesi locale: nessuna registrazione, testo configurabile
  (`voice.startup_greeting_text`) e disattivabile.
- Test suite: 280 test superati, inclusi sicurezza, protocollo, server, UI statica,
  app nativa, watchdog del server, cache TTS, sistema locale, servizio vocale,
  voce, wake word, protezione dall'eco, batteria del Mac, registratore (incluso il
  blocco del HAL), saluto di avvio, provider gratuiti online, vincolo gratuito e
  sonda del microfono.

## 3. Implementato ma non verificato in questo ambiente

| Area | Perché non è verificata | Cosa è stato verificato |
| --- | --- | --- |
| Movimento robot fisico | Nessun robot collegato | Solo simulatore; ogni esito dichiara `simulated` e nessun movimento fisico |
| Link MQTT | Nessun broker/robot configurato | Codice e test di protocollo; nessuna connessione reale |
| Wake word acustica | Non esiste un rilevatore dedicato | Rilevamento sul testo trascritto, verificato con parlato reale |
| Qualità su parlanti diversi | Una sola voce di prova | Trascrizione verificata con voce sintetica e con la stessa frase dal microfono |
| Consumo CPU del ciclo continuo | Nessuna misura prolungata | Latenza misurata su frasi brevi (~1–2 s per comando) |
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
- Installazione guidata del modello STT con verifica automatica.
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
- Auto-approvazione del livello C.
- Uso della dashboard su rete pubblica.
- Invio di segreti al modello o nei log.

## 7. Rischi aperti

1. **Hardware reale mai validato.** Il simulatore non dimostra la sicurezza fisica.
2. **MQTT non validato.** Un ACK non è un completamento verificato.
3. **Voce dipendente dall'ambiente.** Microfono, permesso di sistema e modello
   scaricato sono prerequisiti; senza di essi la chat resta testuale e la UI lo
   dichiara. La wake word è testuale e può avere falsi positivi, anche con Amy che
   sente i propri altoparlanti. Il 1 novembre 2026 l'ingresso audio si è bloccato
   nel HAL di Core Audio per cause esterne ad Amy: ora l'errore è onesto e limitato
   nel tempo, ma il rimedio richiede un riavvio del servizio audio o del Mac.
4. **Saluto di avvio non verificato a mano.** Il messaggio «Amy è attiva e
   operativa.» è stato verificato dai log (sintesi avviata e completata) e dal
   self-test del servizio, ma non con una verifica uditiva dell'utente.
5. **Dashboard senza autenticazione.** Mitigata dal bind locale, non adatta alla rete.
6. **SSRF con DNS lookup.** La risoluzione è controllata prima della richiesta, ma
   non è una difesa contro ogni forma di DNS rebinding.
7. **Timeout strumenti via thread.** Un thread bloccato non viene terminato con la
   forza.
8. **Prompt injection.** Il prompt istruisce a trattare file e web come dati non
   attendibili, ma la difesa principale resta la policy nel codice.
9. **Endpoint IA remoto.** Amy verifica autonomamente solo i preset dichiarati in
   `amy/ai/presets.py`, con limiti e licenza riportati e datati; un endpoint remoto
   generico (`ai.openai.allow_remote`) non è verificabile da sola. In entrambi i casi
   la responsabilità è esplicita e documentata in [GRATUITO.md](GRATUITO.md).

## 8. Come verificare lo stato

```bash
python3 -m compileall -q amy tests
python3 -m unittest discover -s tests -t . -v
python3 -m amy doctor
python3 -m amy ask "che ore sono?" --offline
```

Per una verifica reale del provider:

```bash
python3 -m amy providers
python3 -m amy doctor
python3 -m amy ask "rispondi solo con: ciao"
```

Per il robot, senza hardware:

```bash
python3 -m amy robot status
python3 -m amy robot ping
```

Non usare questi comandi per affermare che il robot fisico funziona.
