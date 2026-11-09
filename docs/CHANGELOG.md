# Changelog

Formato ispirato a Keep a Changelog. Le date sono in UTC. Il progetto è in fase
iniziale: non tutte le voci sono state verificate su hardware.

## [Non rilasciato]

### Aggiunto

- **Neuroni fluttuanti attorno al nucleo.** Campo decorativo su canvas locale
  (`static/neurons.js`) con nodi luminosi, dendriti e sinapsi; la densità e la
  luminosità aumentano negli stati attivi. Rispetta «Movimento: ridotto», disegna
  un solo fotogramma statico e si ferma quando la scheda è nascosta.
- 1 test nuovo (466 totali) e verifica visiva sull'app installata.
- **Ottimizzazione delle animazioni.** Neuroni a 24 fps e solo durante
  un'interazione; in attesa e offline il canvas resta statico. Archi e particelle
  CSS in pausa in attesa/offline e quando la finestra perde il fuoco. Misura:
  WebKit GPU da ~50% a ~0,3% con Amy in attesa.
- **HUD radiale attorno al nucleo.** Archi segmentati, tacche e quattro etichette
  con dati reali (IA, MEM, VOICE, ROBOT) in SVG, coerenti con gli stati del nucleo.
  Un test nuovo (467 totali) e verifica visiva sull'app installata.

- **Dashboard e documentazione finale (Fase 9).** Pannello «Log recenti» con
  `GET /api/logs`: legge solo il file configurato, limita le righe e redige i
  segreti. Primo split di `app.js`: il pannello Progetto vive in
  `static/project.js`, caricato localmente prima di `app.js`, senza bundler.
  Creata la sintesi `docs/knowledge/stato_corrente.md`.
- 3 test nuovi (465 totali, 79 strumenti). Verifica finale con suite, doctor e
  self-test nativo.

- **Developer Assistant nativo (Fase 8).** `dev.status`, `dev.diff` e
  `dev.analyze` leggono ramo, modifiche, diff, file, TODO/FIXME ed errori di
  sintassi senza modificare nulla (A). `dev.test` esegue la suite con timeout e
  output limitato (B). Comandi Git in lista chiusa, nessuna shell arbitraria e
  percorso confinato al progetto. OpenCode resta per le modifiche (C).
- Pannello «Progetto» nella dashboard con ramo, modifiche, ultimo commit e diff
  statistico in sola lettura.
- 12 test nuovi (462 totali, 79 strumenti). Verifica reale su questo repository:
  stato, diff, analisi di `amy/dev` e 462 test eseguiti.
- **Vision e Smart Home opzionali (Fase 7).**
  - `vision.capture` (B) cattura un fotogramma dalla telecamera predefinita tramite
    AVFoundation; è spento per default (`vision.camera = false`) e salva in
    `~/Downloads/Amy/camera`. Cattura reale verificata con un JPEG 1280×720.
  - `vision.describe` resta non implementato: richiede un provider visivo gratuito
    configurato e non viene simulato.
  - Smart Home con `home.devices` (A), `home.state` (A), `home.set` (B) e
    `home.scene` (C), spenta per default (`home.enabled = false`), broker MQTT e
    dispositivi configurati dall'utente, password da variabile d'ambiente. Nessun
    broker o dispositivo reale verificato: solo configurazione e mock.
  - 15 test nuovi (450 totali, 75 strumenti).

- **Riquadro «Prossimi appuntamenti» nella dashboard.** `GET
  /api/calendar/upcoming` esegue `calendar.events` (livello A, sola lettura) sui
  prossimi 7 giorni, scarta gli eventi già terminati, unisce i duplicati per UID,
  ordina e limita il risultato. Il pannello mostra data, ora e titolo con
  `textContent`, dichiara i dati mancanti e le letture parziali senza inventarli,
  e si aggiorna ogni 2 minuti o con il pulsante «Aggiorna». Verificato con 13
  nuovi test automatici (AppleScript sostituito da mock): la lettura reale di
  Calendar.app attraverso il nuovo endpoint **non** è stata verificata a mano.
- Nessuna nuova dipendenza e nessuna nuova impostazione: il riquadro usa
  Calendar.app locale e il tool `calendar.events` già esistente.

## [0.14.0] — 2026-11-07

### Aggiunto

- **Personal Manager completo (Fase 6).** `calendar.update` modifica titolo, ora,
  durata, note e luogo di un evento (B). Attività e note persistenti con
  `tasks.create/list/update/complete/delete` e `notes.create/list/update/delete`
  (B per le scritture, C per le cancellazioni). Agenda unica in
  `PersonalManager.agenda()`.
- Pannello «Attività e note» nella dashboard con stato reale.
- 10 test nuovi (435 totali, 70 strumenti). Verifica reale di calendar.update.

## [0.13.0] — 2026-11-07

### Aggiunto

- **Memoria estesa (Fase 5).** Nuova tabella `memory_items` con categorie
  (`personal`, `project`, `operational`, …), tag, `verified`, `confidence`,
  `expires_at`; migrazione non distruttiva da `facts` (schema 2). Tabelle `tasks`
  e `notes` pronte per la Fase 6.
- Strumenti `memory.search`, `memory.update`, `memory.categories`; `memory.remember`
  accetta categoria, tag, verificabilità, confidenza e scadenza; `memory.list`
  filtra per categoria e cerca testo.
- Il prompt include la memoria di progetto entro il budget dei fatti.
- 9 test nuovi (425 totali); migrazione verificata sul database reale.

## [0.12.0] — 2026-11-07

### Aggiunto

- **Autorizzazioni per modulo e capacità (Fase 4).** `AuthorizationBroker`
  verifica che lo strumento appartenga a un modulo abilitato, che la capacità sia
  dichiarata e non revocata. La policy A/B/C resta l'ultima parola: il livello C
  non diventa mai automatico.
- `GET /api/permissions`, `POST /api/permissions/revoke`,
  `POST /api/permissions/restore`; pannello «Permessi» nella dashboard.
- Audit con `module` e `capability`; `tool_rejected` con
  `authorization_denied`.
- 11 test nuovi (416 totali).

### Nota

Le revoche sono a runtime: al riavvio tornano tutte attive.

## [0.11.0] — 2026-11-07

### Aggiunto

- **Moduli visibili e controllabili (Fase 3).** `/api/state` include `modules`;
  `GET /api/modules` elenca gli otto moduli con manifest e stato reale;
  `POST /api/modules/{name}/enabled` abilita/disabilita un modulo. Disabilitarlo
  rimuove i suoi strumenti dal catalogo attivo; Memory è essenziale e resta
  sempre attivo.
- **Pannello «Moduli»** nella dashboard: stato, dettaglio, numero di strumenti e
  interruttore. Aggiornamento ogni 30 secondi e dopo ogni modifica.
- 6 test nuovi tra server e UI (405 totali).
- Disabilitare un modulo annulla le conferme pendenti dei suoi strumenti.

### Nota

L'abilitazione è a runtime: al riavvio i moduli tornano abilitati. La persistenza
in `~/.amy/config.json` sarà affrontata nella fase di configurazione.

## [0.10.1] — 2026-11-07

### Aggiunto

- **Adapter dei moduli (Fase 2).** `amy/modules/` contiene otto adapter che
  avvolgono il codice esistente: Voice, Mac Control, Personal, Memory, Developer,
  Vision, Home e Robot. Ogni adapter dichiara manifest, capacità e strumenti;
  `build_module_registry()` li registra senza avviarli.
- 10 test verificano che l'unione degli strumenti dei moduli coincida con i 57
  strumenti del registry esistente e che enable/disable, stati e dipendenze siano
  corretti.

### Modificato

- `time.now` è stato spostato da `voice_tools.py` a `system.py` per coerenza
  architetturale. Nome, schema e comportamento dello strumento non cambiano.

## [0.10.0] — 2026-11-07

### Aggiunto

- **Contratti dei moduli (Fase 1).** `amy/shared/module.py` definisce
  `ModuleState`, `ModuleManifest`, `ModuleStatus`, `ModuleContext` e il protocollo
  `AmyModule`. `amy/core/modules.py` aggiunge `ModuleRegistry` con ciclo di vita,
  stato, strumenti per modulo e isolamento degli errori.
- **Bus di eventi locale.** `amy/shared/events.py` offre pub/sub thread-safe,
  wildcard, storico circolare, `flush()` e isolamento dei listener rotti.
- 13 test nuovi (389 totali).

### Nota

L'infrastruttura non è ancora collegata a Core, strumenti o UI: nessun
comportamento esistente è cambiato.

## [0.9.0] — 2026-11-06

### Aggiunto

- **Screenshot e OCR locale.** `screen.capture` salva un PNG; `screen.read`
  cattura lo schermo (o legge un'immagine) ed estrae il testo con Vision, senza
  rete. Livello B, conferma obbligatoria, permesso Registrazione schermo.
  Verificato su uno schermo reale: 500 caratteri in circa 5 secondi. Non riconosce
  oggetti o immagini senza testo: per quello serve un modello visivo.

## [0.8.0] — 2026-11-06

### Aggiunto

- **Apertura di file e ricerca nel testo.** `files.open` apre un file con l'app
  predefinita; `files.grep` cerca una parola o frase dentro i documenti di testo
  di una cartella autorizzata, restituendo file, riga ed estratto.
- **CPU e RAM in `system.info`**: carico medio a 1/5/15 minuti, RAM totale,
  libera, usata e percentuale, oltre a disco e batteria già presenti.

### Corretto

- **`system.processes` non restituiva risultati**: su macOS `ps` ordina con `-r`
  e `-m`, non con `-pcpu`/`-pmem`; inoltre il locale italiano usa la virgola come
  separatore decimale. Ora i processi sono ordinati e i valori letti davvero.

## [0.7.0] — 2026-11-05

### Aggiunto

- **Integrazione con OpenCode 2.** `opencode.run` apre o continua una sessione
  `opencode2` nella cartella di progetto e le affida una richiesta; la sessione
  viene ricordata per cartella. Livello C, conferma sempre obbligatoria, nessun
  `--auto`, nessuna shell, timeout e output limitati. `opencode.status` mostra
  configurazione e sessioni. Verificato con una richiesta reale che ha creato e
  riletto un file di prova.
- `opencode.enabled` è spento per default; `opencode.project_dir` sceglie la
  cartella (sempre dentro le radici autorizzate).
- **Riavvio dell'app dopo le modifiche.** `app.restart` e
  `opencode.run restart_after=true` programmano il riavvio di Amy Core con un
  helper staccato: attende l'uscita, riapre il bundle e verifica `/api/health`.
  Livello C, conferma obbligatoria; log in `~/.amy/restart.log`.
- **Ciclo di auto-sviluppo**: Amy può chiedere a OpenCode di implementare una
  modifica, aspettare l'esito e riavviarsi per caricarla.

## [0.6.0] — 2026-11-05

### Aggiunto

- **Lettura della posta da Mail.app.** `mail.accounts`, `mail.mailboxes`,
  `mail.list` e `mail.search` leggono account, cassette, mittenti, oggetti e date.
  `mail.read` apre il corpo di un messaggio per ID ed è di livello B: richiede
  conferma perché con un provider online il contenuto lascia il Mac. Verificato
  sull'account `info@ewp.it` configurato in Mail.
- **Invio di email.** `mail.send` crea e invia un messaggio dall'account
  configurato, con destinatari, oggetto, corpo e copie. È di livello C: richiede
  sempre la conferma e non può essere annullato. Gli indirizzi sono validati.
- `mail.default_account` e `mail.default_mailbox` scelgono account e cassetta.

## [0.5.0] — 2026-11-03

### Aggiunto

- **Conversazione continua.** Dopo la wake word l'utente non deve più ripetere
  «Amy»: le risposte successive vengono interpretate nel contesto della sessione.
  Dopo 30 secondi di silenzio Amy chiede «Sei ancora lì?» e poi torna in standby;
  «basta», «stop» e «fine conversazione» chiudono lo scambio.
- **Interruzione durante la sintesi (barge-in).** Con
  `voice.conversation.barge_in` attivo il microfono resta in ascolto mentre Amy
  parla: se sente «Amy» ferma subito `say`, passa allo stato `interrupted` e
  accetta il nuovo comando senza wake word. Il filtro anti-eco è testuale
  (confronto con il testo in pronuncia), non cancellazione acustica.
- **Macchina a stati vocale** (`amy/voice/state.py`): `idle`,
  `wake_word_detected`, `listening`, `processing`, `speaking`,
  `conversation_active`, `waiting_for_input`, `waiting_for_confirmation`,
  `interrupted`, `error`, `offline`, con transizioni dichiarate e stato esposto
  alla dashboard.
- **Dashboard**: nuovi indicatori «Conversazione» e «Interrotta», sincronizzati
  con lo stato reale.

### Corretto

- **Dettatura tagliata**: la registrazione in conversazione si fermava dopo 3,5 s
  e un indirizzo email non finiva in tempo. Ora un VAD adattivo chiude il turno
  dopo circa un secondo di silenzio, con un massimo di 15 s: le frasi lunghe non
  vengono tagliate e le risposte brevi non fanno aspettare.
- **Latenza dopo l'interruzione**: la finestra di ascolto in conversazione scende a
  3,5 s (da 5 s) e lo storico inviato al modello è limitato a 4.000 caratteri.
  Una risposta lunga non fa più raggiungere il limite di 8.000 token/minuto e
  Amy non passa più decine di secondi in attesa del provider.
- **Ascolto che si fermava dopo 20 minuti**: `voice.wake_word.max_minutes` ora è
  `0` per default (nessun limite); il ciclo resta attivo finché l'app è aperta.
- **Dashboard bloccata su /api/state**: `MacSayTTS.status()` eseguiva `say -v ?`
  dentro la richiesta HTTP; con la voce occupata il sottoprocesso poteva
  bloccarsi e la dashboard restava in attesa. Ora lo stato legge solo la cache,
  riempita in background da `warm()`.
- **Backend riavviato dall'app mentre era vivo**: il controllo di salute usava
  `/api/state`, che interroga PortAudio; con il microfono aperto poteva superare
  il timeout di 1 s. Ora usa `/api/health` e il nome del dispositivo viene letto
  una sola volta.
- **Backend chiuso da solo**: il watchdog dell'heartbeat chiudeva la dashboard
  quando App Nap sospendeva il timer dell'app, anche con l'app viva. Ora il
  backend controlla il PID del genitore e resta attivo se è ancora presente;
  l'app dichiara un'attività `userInitiated` per non farsi sospendere.

### Limiti dichiarati

- L'interruzione non usa AEC: se Amy sta pronunciando la parola «Amy», il filtro
  può scartare l'interruzione come eco.
- La latenza del barge-in dipende dallo STT locale (1–3 s con `small` su Intel).

## [0.4.0] — 2026-11-03

### Aggiunto

- **Creazione di appuntamenti in Calendar.app.** Nuovi strumenti
  `calendar.list`, `calendar.events` e `calendar.create`: Amy legge i calendari
  e gli eventi e crea un appuntamento reale con titolo, data, ora, durata,
  note e luogo. La creazione è di livello B e richiede la conferma; il primo uso
  richiede il permesso Automazione per Calendar. Verificato il 3 novembre 2026
  con un evento creato, riletto e rimosso.
- `calendar.default_name` (default `"Calendario"`) sceglie il calendario di
  destinazione; i calendari di sistema vengono esclusi.
- **Eliminazione di eventi.** `calendar.delete` cancella per UID oppure per titolo
  e data; è di livello C e richiede sempre conferma.
- **Conferma vocale.** Quando un comando richiede conferma, Amy pronuncia la
  domanda e ascolta «sì»/«no» per 30 secondi senza richiedere di nuovo «Amy».
  Una risposta non chiara fa ripetere la domanda; allo scadere l'operazione viene
  annullata. Le azioni di livello C restano sempre soggette a conferma.
- **Promemoria completi.** `reminders.lists`, `reminders.list`, `reminders.create`,
  `reminders.complete` e `reminders.delete` gestiscono Promemoria.app: elenco,
  creazione con scadenza (B), completamento (B) ed eliminazione (C).
  `reminders.default_list` sceglie la lista. Verificato il 3 novembre 2026 con un
  promemoria creato, completato e rimosso.

## [0.3.1] — 2026-11-02

### Modificato

- **Avvio automatico dell'ascolto continuo.** Su richiesta esplicita dell'utente
  è stata rimossa la regola che vietava la registrazione in background senza
  azione esplicita: l'ascolto continuo si avvia automaticamente all'avvio del
  server se `voice.wake_word.start_on_launch` è attivo (default: true), ed è
  disattivabile con `voice.wake_word.enabled = false` o
  `start_on_launch = false`. La responsabilità della privacy è dell'utente.
- **Versione del bundle macOS** sincronizzata con `pyproject.toml` tramite
  `PlistBuddy` in `build.sh` (prima restava a 0.1.0).
- **Conteggio strumenti** corretto da 34 a 35 (era sfuggito `system.battery`).

### Corretto

- **Trascrizione italiana**: modello `small` e prompt iniziale italiano. Prima
  «apri mail» diventava «apre i mail» e «Amy» spariva; ora la stessa frase è
  trascritta correttamente.
- **Falsi risvegli**: la wake word non viene più attivata da parole comuni come
  «ha», «mai» o «mia».
- **Limite gratuito del provider online**: il catalogo degli strumenti è inviato
  in forma testuale compatta (da ~12.500 a ~6.700 caratteri di prompt) e, in caso
  di HTTP 429, Amy usa l'attesa indicata dal servizio (fino a tre tentativi)
  invece di scivolare subito nel fallback offline.
- **Risposta vuota**: un secondo tentativo evita il fallback offline per un
  singolo pacchetto perso.
- **Messaggio di fallback più onesto**: se il provider online non risponde e
  l'interprete offline non capisce, Amy dice che il servizio non è disponibile e
  invita a riprovare, senza suggerire Ollama.

## [0.3.0] — 2026-10-31

### Aggiunto

- **Attivazione vocale completa e locale.** Registrazione dal microfono con
  `sounddevice` (PortAudio/Core Audio, WAV PCM 16 bit mono a 16 kHz scritto con il
  modulo standard `wave`), trascrizione con `faster-whisper` 1.2.1 su CPU (int8,
  modello `base` scaricato una volta in `~/.amy/models/whisper`) e sintesi con `say`
  di macOS. Nessun audio lascia il Mac, nessun account o credito richiesto.
- **Wake word «Amy»** (`amy/voice/wakeword.py`): confronto testuale tollerante
  ristretto al primo token o dopo un prefisso di richiamo, per riconoscere gli
  errori tipici dello STT su una parola inventata («Emi», «Ami», «Emy») senza
  attivarsi su parole comuni.
- **Ciclo di ascolto continuo** (`VoiceService.start_wake_loop`): parte solo da un
  comando esplicito (pulsante «Ascolta «Amy»» o `amy voice loop`), si ferma con lo
  stesso comando e comunque dopo `voice.wake_word.max_minutes` (20 di default,
  massimo 120).
- **Endpoint di dashboard** `POST /api/voice/wake/start`, `POST /api/voice/wake/stop`
  e `POST /api/voice/greet`.
- **Saluto di avvio**: all'avvio della dashboard Amy pronuncia «Amy è attiva e
  operativa.» con la sola sintesi locale, senza registrare nulla. Il testo è
  configurabile (`voice.startup_greeting_text`), disattivabile in modo permanente
  (`voice.startup_greeting`) o per una sessione (`AMY_STARTUP_GREETING=0`).
- **Strumento `system.battery`**: legge lo stato della batteria del **Mac**
  (`pmset -g batt`, sola lettura) e restituisce percentuale, carica o scarica e
  tempo residuo stimato. Rischio A, nessuna modifica. Su un Mac senza batteria
  integrata dichiara l'assenza invece di inventare un valore. La batteria del
  robot resta `robot.status`.
- **Protezione dall'eco in modalità half-duplex** (`voice.wake_word.echo_guard`):
  mentre Amy parla il microfono non registra, i frammenti che contengono la sua
  voce vengono scartati e dopo la sintesi segue una pausa breve
  (`voice.wake_word.echo_guard_cooldown_s`, default 0,8 s). La sintesi non
  bloccante viene seguita da un thread di sorveglianza che chiude l'intervallo di
  sintesi (`MacSayTTS.speech_overlaps`).
- `python3 -m amy voice greet`: ripete il messaggio di avvio dalla CLI.
- **Pulsante «Ascolta «Amy»»** nella topbar, con `aria-pressed` che segue lo stato
  reale, e **«Ripeti saluto»** nel pannello Voce.
- `tests/test_recorder.py` (12 test), `tests/test_voice_wake.py` (21 test),
  `tests/test_battery.py` (11 test), `tests/test_tts_echo.py` (5 test) e nuovi
  casi in `tests/test_voice_service.py`, `tests/test_server.py`,
  `tests/test_native_app.py`, `tests/test_server_watchdog.py`, `tests/test_voice.py` e
  `tests/test_ui_static.py`: 351 test in totale, tutti superati.
- `python3 -m amy doctor` apre il microfono per un secondo, cancella subito l'audio e
  riporta la voce «Microfono»: distingue un modulo installato da un ingresso che
  risponde davvero.

### Modificato

- `voice.stt.engine` default `auto`: sceglie `faster-whisper` se installato, altrimenti
  `whisper-cli`; `voice.recorder.engine` default `auto`: preferisce `sounddevice`,
  poi `ffmpeg`. Il motore `faster-whisper` viene usato come ripiego locale anche
  quando è configurato `whisper-cli` senza comando o modello.
- Corretto un difetto latente in `FasterWhisperSTT`: il metodo `available()` sovrascriveva
  la proprietà `available` della classe base.
- Precaricamento del modello STT in background all'avvio del server
  (`VoiceService.warm()`): il primo comando vocale non aspetta il caricamento.
- `NSMicrophoneUsageDescription` aggiunto a `Info.plist`: il permesso Microfono è
  attribuito ad «Amy Core» e la sua descrizione spiega che la registrazione parte
  solo da un comando.
- L'app nativa passa `AMY_STARTUP_GREETING=0` durante il self-test, che non deve
  emettere audio.
- Documentazione aggiornata: `docs/VOCE.md` riscritto, nuove voci in `docs/GRATUITO.md`
  (licenze di `sounddevice`, `ctranslate2`, NumPy, `huggingface-hub`, `tokenizers`,
  `onnxruntime`), `docs/CONFIGURAZIONE.md`, `docs/INTERFACCIA.md`,
  `docs/ARCHITETTURA.md`, `docs/TEST.md`, `docs/STATO_PROGETTO.md`, `README.md` e
  decisione **D-023** in `docs/DECISIONI.md`.

### Corretto

- **Registrazione senza attese infinite.** PortAudio può bloccarsi dentro il HAL di
  Core Audio (`Pa_OpenStream` non restituisce il controllo): la cattura ora gira in
  un thread con limite `durata + 6 s`, poi `VoiceError` «Il microfono non risponde»,
  stato `stuck: true` e nessun nuovo tentativo per 60 secondi. Il ciclo di wake word
  si ferma dichiarando `microfono non rispondente`; `POST /api/voice/listen` risponde
  400 dopo ~11 s e `POST /api/voice/wake/start` risponde 503, invece di lasciare la
  richiesta appesa per sempre.
- **Heartbeat dell'app nativa** spostato su `DispatchSourceTimer` in una coda
  dedicata, avviato prima del backend: il timer sul run loop principale poteva
  fermarsi quando la finestra era occupata e il backend si chiudeva da solo durante
  l'ascolto continuo. Tolleranza del watchdog portata a 20 s, controllo di salute a
  6 s con 3 fallimenti consecutivi, messaggio di chiusura con file, età e tolleranza.
- **Avviso «backend non risponde» non modale** (`beginSheetModal`): con
  `runModal` l'app restava congelata finché l'utente non rispondeva.
- **Sintesi bloccante con limite di tempo** (`MacSayTTS.block_timeout`, minimo 20 s):
  un `say` appeso non blocca più il saluto di avvio né l'endpoint HTTP; il processo
  viene terminato e il risultato dichiara `spoken: false` con il motivo.
- Il saluto di avvio registra «pronunciato» solo quando la sintesi è davvero
  conclusa; altrimenti lascia un avviso con il motivo.
- **Self-test dell'app nativa più onesto**: apre la dashboard con `?selftest=1` e
  salta il caricamento della cronologia, così non può scambiare una risposta
  vecchia per quella nuova. Attende la prima risposta reale e riporta lo stato
  della UI (osservato il 2 novembre 2026: il test dichiarava OK con «07:47»
  alle 08:04, mentre l'app stava ancora elaborando).

### Verificato dal vivo

- **2 novembre 2026, protezione dall'eco**: tre comandi «Amy, che ore sono?» dagli
  altoparlanti con il ciclo attivo. Due rilevati, uno perso perché pronunciato
  mentre Amy rispondeva (microfono chiuso). Forzando una sintesi durante una
  registrazione, il log ha riportato
  `Frammento scartato: Amy stava parlando (protezione dall'eco).` e nessun comando
  è stato eseguito.
- **2 novembre 2026, batteria del Mac**: `python3 -m amy ask "quanto è carica la
  batteria del mac?" --offline` → «Batteria del Mac al 100%, carica.» (nessun
  «0:00» inventato quando il tempo residuo non è utile).
- Il ciclo CLI ora condivide la stessa `VoiceService` dell'assistente: prima ne
  creava una seconda e l'echo guard non vedeva la sintesi, e la risposta veniva
  troncata da `close()`.

### Limiti dichiarati

- La wake word **non** è un rilevatore acustico dedicato: consuma STT su tutto
  l'audio ascoltato e può avere falsi positivi. Un filtro acustico locale
  (per esempio openWakeWord) davanti allo STT non è ancora integrato.
- Con la protezione half-duplex attiva, **mentre Amy parla il microfono è
  chiuso**: un comando dettato durante la risposta viene perso e va ripetuto, e
  l'interruzione a voce non è più possibile.
- Il consumo CPU del ciclo continuo non è stato misurato su periodi lunghi.
- La qualità della trascrizione è stata verificata con una sola voce di prova e con
  frasi brevi.

## [0.2.0] — 2026-10-31

### Aggiunto

- **Provider IA online gratuiti verificati** (`amy/ai/presets.py`): elenco chiuso con
  endpoint, modello, licenza, condizioni del piano gratuito, privacy e data di
  verifica. Primo preset: GroqCloud piano Free (`groq`, `openai/gpt-oss-120b`,
  Apache-2.0), senza carta di credito, con quote dichiarate.
- `python3 -m amy providers`: mostra preset, limiti, licenza e privacy senza segreti.
- `python3 -m amy secret set|list`: scrittura di `~/.amy/secrets.json` con permessi
  `0600` e input nascosto; `list` mostra solo i nomi.
- `amy doctor` verifica `Servizio IA`, `Chiave API` (con `GET /models`, nessun token
  di conversazione) e `Modello online`, e riporta le condizioni del piano gratuito
  sotto `Costi IA`.
- `tests/test_online_presets.py` (17 test): metadati gratuiti, consenso esplicito,
  default locale, fallback locale, sonda senza chiave che non usa la rete, presenza
  di un `User-Agent` esplicito, retry singolo sul limite di token.
- `tests/test_prompt_budget.py` (2 test): il prompt di sistema resta sotto il budget
  compatibile con un piano gratuito e il catalogo inviato al modello non contiene i
  campi riservati all'interfaccia.
- Pannello Motore IA: distingue «chiave API non configurata», «servizio online
  gratuito autorizzato» e «modello mancante», senza inventare disponibilità.

### Modificato

- `ai.provider` accetta i preset online, ma solo con `ai.online.consent = true`.
  Senza consenso la configurazione viene rifiutata con un messaggio esplicito.
- Il fallback non può essere un servizio online: resta `offline` o `ollama`.
- **Dashboard ridisegnata**: il nucleo occupa l'intero palco, la chat è un satellite
  a destra, alto quasi quanto il palco, e i pannelli informativi si sovrappongono a
  sinistra, con chiusura sfumata e sollevamento su hover/focus. Il pannello Robot
  sale al secondo posto per tenere l'E-stop software raggiungibile; sotto 1040 px il
  layout passa a un flusso verticale con la chat subito dopo la topbar.
- **Barra comandi separata**, centrata in fondo al palco come nel riferimento
  J.A.R.V.I.S.: campo di scrittura, microfono, «Invia», promemoria e «Pronuncia le
  risposte» escono dalla chat e conservano gli stessi identificativi, quindi resta un
  solo punto di invio. Il nucleo riserva spazio per non finirci sotto.
- **Campo stellato statico** in SVG inline, con stelle generate localmente: nessuna
  immagine, nessun filmato e nessuna animazione, per non pesare sulla GPU (Mac Intel)
  e restare compatibile con la CSP che vieta stili inline e risorse esterne.
- `tests/test_ui_static.py`: nuovo test su barra comandi separata, unicità dei
  controlli di invio e campo stellato locale.
- `docs/GRATUITO.md`, `docs/CONFIGURAZIONE.md` e il resto della documentazione
  riportano licenze, limiti, privacy e il nuovo flusso di configurazione.

### Corretto

- Le richieste al provider online dichiarano un `User-Agent` esplicito
  (`AmyBrain/<versione>`): senza, Cloudflare davanti a Groq rispondeva `403` con
  «error code: 1010» anche con una chiave valida.
- La versione dell'applicazione è centralizzata in `amy.__version__` (0.2.0) e non
  più ripetuta come stringa letterale in server, assistente e CLI.
- Il catalogo strumenti inviato al modello contiene solo nome, descrizione e
  parametri: il prompt di sistema scende da ~6.500 a ~3.100 token stimati e resta
  dentro il limite gratuito di token al minuto.
- Una risposta `429` del provider viene ritentata una sola volta, rispettando
  `Retry-After` (massimo 20 s), prima di usare il fallback locale.
- Il motivo del fallback viene registrato con il dettaglio dell'errore, redatto e
  troncato, così un guasto del provider è diagnosticabile senza esporre segreti.

### Sicurezza

- La chiave API non compare nella configurazione, nei log, nella dashboard o nel
  repository; senza chiave il provider risulta non disponibile.
- Il default del repository resta locale (`ai.provider = "ollama"`,
  `ai.online.consent = false`): nessun traffico verso servizi esterni senza scelta
  esplicita.

## [0.1.0] — 2026-10-30

### Aggiunto

- **Applicazione macOS nativa «Amy Core»** (`apps/AmyCore`): Swift + AppKit +
  WebKit, finestra propria, icona nel Dock generata localmente con CoreGraphics,
  menu con scorciatoie, schermo intero nativo, build con soli tool di sistema e
  firma ad-hoc. Nessuna dipendenza di terze parti, nessun costo, nessun account.
- Self-test end-to-end dell'app (`apps/AmyCore/selftest.py`): avvia l'app, invia
  un messaggio reale dal DOM, verifica la risposta in chat e la chiusura del
  backend.
- Watchdog heartbeat nel server locale: il backend si chiude da solo se l'app
  nativa muore, anche con SIGKILL (nessun processo orfano).
- Gestore SIGTERM/SIGINT nell'app: chiusura ordinata e backend fermato subito.
- File di stato dell'app in `~/.amy`: `app.json` (percorso del repository),
  `app.pid`, `app.heartbeat`, `app.log`, `backend.log`.
- Test per l'app nativa, il watchdog del server e la cache delle voci TTS.
- Configurazione locale `~/.amy/config.json` con override ambiente e segreti separati.
- Logging con redazione e audit append-only JSONL.
- Memoria SQLite: sessioni, messaggi, fatti, attività ed eventi robotici.
- Orchestrazione del turno con protocollo d'azione JSON, limite passaggi e conferme
  in due fasi.
- Policy di rischio A/B/C; il livello C non è mai auto-approvato.
- Path guard con radici autorizzate, deny-list, backup e cestino recuperabile.
- Shell a enum chiuso di sola lettura, senza `shell=True`.
- Web con apertura URL, ricerca DuckDuckGo e lettura con protezione SSRF.
- 34 strumenti registrati: sistema, app macOS, file, shell, web, memoria, voce e
  robot.
- Provider Ollama, compatibile OpenAI, offline deterministico e fallback.
- TTS macOS con voce italiana, stato, interruzione e sintesi su file.
- Adattatori STT opzionali e registratore `ffmpeg`/`sox`.
- Rilevamento testuale della wake word e ciclo vocale esplicito.
- Protocollo robotico v1 e simulatore con limiti, ACK/NACK, deduplicazione, sequenza,
  watchdog ed E-stop.
- Link robot simulato e MQTT sperimentale.
- CLI: `init`, `doctor`, `tools`, `config`, `chat`, `ask`, `memory`, `robot`, `voice`,
  `serve`.
- Dashboard locale «Amy Core» con tre aree: chat reale, nucleo centrale a otto stati
  e pannello dati con motore IA, sistema, voce, robot, memoria, attività e strumenti.
- Stati del nucleo derivati solo da segnali reali: richiesta in corso, attività
  `in_corso`, conferma pendente, `voice.speaking`, disponibilità del provider,
  errore restituito e latch E-stop. Nessuna attività simulata dalla UI.
- Informazioni di sistema locali con la sola libreria standard: macOS, architettura,
  Python, CPU, carico medio e disco in `status()["system"]`.
- Stato voce con `speaking` reale dal TTS, usato dalla dashboard per lo stato di
  sintesi.
- Interfaccia accessibile e responsiva: skip link, focus visibile, `aria-live`,
  dialog con focus trap, `Esc`, schermo intero, movimento ridotto, nessuna risorsa
  esterna e nessuno stile inline compatibile con la CSP.
- Test per interfaccia statica, informazioni di sistema e servizio vocale.
- Test suite con 168 test (189 dalla 0.2.0).
- Vincolo «solo strumenti gratuiti» reso **globale e permanente** in `AGENTS.md`,
  `OpenCode.md`, `README.md` e documentazione tematica: vale per conversazione,
  modelli IA, voce, wake word, controllo del Mac, interfaccia e robot.
- Documentazione delle licenze, default locale, blocco degli endpoint IA remoti senza
  consenso esplicito, controllo «Costi IA» in `amy doctor`.
- Audit delle dipendenze e test `tests/test_free_only.py` contro dipendenze
  obbligatorie, host IA commerciali cablati e campi di fatturazione.
- Adattatore OpenAI-compatible orientato a server locali: endpoint predefinito
  `http://127.0.0.1:8000/v1`, chiave API opzionale, `allow_remote` esplicito.

### Corretto

- La dashboard non mostra più dati inventati: provider, voce, robot e sistema
  distinguono «Non disponibile», «Non configurato» e valori simulati.
- `/api/state` non impiegava più 1,2 secondi a ogni richiesta: `say -v ?` non
  viene più rieseguito a ogni poll (l'elenco delle voci è in cache e preparato in
  background), quindi la dashboard risponde subito.
- Il backend non resta più orfano se l'app nativa viene uccisa: heartbeat del
  genitore con chiusura automatica.
- Il pannello motore IA distingue «Ollama raggiungibile ma modello non installato»
  come «modello mancante», invece di dichiarare il motore disponibile.
- Il pannello motore IA distingue «Ollama raggiungibile ma modello non installato»
  come «modello mancante», invece di dichiarare il motore disponibile.
- L'etichetta del sistema operativo viene composta da `os_name` e versione: non
  mostra più «macOS» davanti a un sistema diverso da Darwin.
- Il preambolo di una richiesta di conferma viene mostrato in chat anche se il
  backend non lo salva nella trascrizione.
- Il pannello robot accetta sia lo stato piatto del simulatore sia quello annidato
  del collegamento MQTT, senza mostrare «Non disponibile» al posto di dati reali.
- Il provider con fallback ora espone `available` e `model_installed` a livello
  superiore, così `amy doctor` e la dashboard non mostrano uno stato falso.
- `amy doctor` non etichetta più come `OK` i controlli falliti.
- Strumenti inesistenti e argomenti non validi vengono registrati come attività
  fallite e nell'audit, senza eseguire nulla.
- Il limite di passaggi non consente più un turno extra.
- Il contatore `seq` MQTT è per destinatario.
- Il comando `amy memory sessions` mostra il numero reale di messaggi e il titolo.
- La dashboard invia `X-Frame-Options`, `Referrer-Policy` e una CSP con
  `frame-ancestors`.
- Il bind della dashboard su interfacce non locali richiede `ui.allow_remote=true`.

### Sicurezza

- Conferma esplicita obbligatoria per il livello C.
- E-stop e stop robot mai bloccati da conferma.
- Nessun segreto in codice, log, memoria o dashboard.
- Nessun CDN o risorsa esterna nella UI.
- Registrazione audio solo su azione esplicita.
- Nessun provider a pagamento obbligatorio e nessun fallback automatico verso un
  servizio a pagamento.
- Endpoint IA pubblico rifiutato senza `ai.openai.allow_remote=true`.

### Non verificato

- Movimento fisico del robot.
- Collegamento MQTT reale.
- Riconoscimento vocale e microfono su questa macchina.
- Uso prolungato e affidabilità nel tempo.

## Non rilasciato

Vedi [ROADMAP.md](ROADMAP.md) per le prossime attività.
