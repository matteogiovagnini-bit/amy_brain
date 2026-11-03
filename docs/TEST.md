# Test e verifica

Questo documento descrive cosa viene verificato, come, e cosa **non** viene
dimostrato. Un test verde non è una prova di sicurezza fisica.

## 1. Comandi

```bash
python3 -m compileall -q amy tests
python3 -m unittest discover -s tests -t . -v
```

Smoke test manuali:

```bash
python3 -m amy doctor
python3 -m amy ask "che ore sono?" --offline
python3 -m amy ask "rispondi solo con: ciao"
python3 -m amy robot status
python3 -m amy voice status
python3 -m amy memory sessions
```

## 2. Esito verificato

Data della verifica: **2 novembre 2026**.

```text
Ran 318 tests in 19.0s

OK
```

`compileall` non produce errori. I test sono 255, tutti superati.

| File | Test | Copertura |
| --- | --- | --- |
| `tests/test_battery.py` | 11 | parsing di `pmset -g batt`, Mac senza batteria, batteria carica senza «0:00», strumento in sola lettura, distinzione fra batteria del Mac e del robot |
| `tests/test_calendar.py` | 18 | date ISO, scelta del calendario, escaping AppleScript, evento di un giorno intero, durata limitata, lettura e ordinamento eventi, rischio B per la creazione |
| `tests/test_config.py` | 16 | default gratuiti, endpoint remoto, fallback, schema URL, segreti, init |
| `tests/test_conversation.py` | 9 | stati vocali, conversazione continua senza wake word, «basta», timeout con verifica presenza, barge-in durante la sintesi, filtro dell'eco |
| `tests/test_files.py` | 9 | radici, deny-list, symlink, backup, cestino, ricerca, diff |
| `tests/test_free_only.py` | 6 | nessuna dipendenza obbligatoria, host commerciali, default locali |
| `tests/test_native_app.py` | 13 | app nativa: file, sole dipendenze di sistema, nessuna risorsa esterna, loopback, heartbeat su coda dedicata, App Nap disattivata, avviso non modale, self-test isolato dalla cronologia, versione del bundle sincronizzata |
| `tests/test_memory.py` | 5 | sessioni, messaggi, conteggio, fatti, attività, redazione |
| `tests/test_offline.py` | 13 | intenzioni italiane, ora, file, web, memoria, conversazione |
| `tests/test_online_presets.py` | 17 | preset gratuiti, consenso esplicito, default locale, fallback, sonda chiave senza rete, `User-Agent`, retry sul limite |
| `tests/test_orchestrator.py` | 13 | turno, conferme, rifiuti, limite passaggi, audit, storia |
| `tests/test_policy.py` | 12 | livelli A/B/C, allow-list, E-stop non bloccato, TTL |
| `tests/test_prompt_budget.py` | 2 | prompt compatto entro il limite gratuito, catalogo testuale senza campi riservati alla UI |
| `tests/test_protocol.py` | 8 | envelope, versione, campi extra, ruoli, topic |
| `tests/test_providers.py` | 11 | stato del fallback, endpoint locale/remoto, chiave opzionale, attesa consigliata dal servizio |
| `tests/test_recorder.py` | 12 | scelta del motore audio, WAV valido, stato senza modulo, blocco del HAL con limite di tempo, blocco dichiarato e non ritentato, sonda microfono del doctor |
| `tests/test_reminders.py` | 12 | liste, creazione con scadenza, parsing di scadenze assenti, completamento ed eliminazione, rischio B/C |
| `tests/test_schema.py` | 8 | schema JSON, tipi, argomenti, campi extra |
| `tests/test_server_watchdog.py` | 5 | heartbeat assente o scaduto: il backend si chiude solo se il processo padre è morto; con padre vivo resta attivo (App Nap) |
| `tests/test_server.py` | 25 | API, conferme, stato con sistema e voce, endpoint wake word (incluso il rifiuto onesto con microfono bloccato), conferma vocale sì/no, bind remoto, header |
| `tests/test_shell.py` | 5 | comandi ammessi, rifiuto arbitrario, git, timeout |
| `tests/test_simulator.py` | 12 | limiti, ACK/NACK, watchdog, E-stop, deduplicazione, modalità |
| `tests/test_system_info.py` | 5 | dati locali reali, disco, nessun segreto o dato robot |
| `tests/test_tts_cache.py` | 2 | elenco voci calcolato una sola volta |
| `tests/test_tts_echo.py` | 5 | intervalli di sintesi: sovrappposizione, sintesi conclusa, TTS nullo |
| `tests/test_ui_static.py` | 19 | otto stati, palco a strati, barra comandi separata, campo stellato locale, pulsante ascolto «Amy», accessibilità, reduced motion, fullscreen, nessuno stile inline, nessun `innerHTML`, nessuna risorsa esterna |
| `tests/test_voice_service.py` | 10 | `speaking` reale dal TTS, stop della sintesi, saluto di avvio, sintesi che non conclude |
| `tests/test_voice.py` | 8 | TTS, stato, wake word testuale, STT assente, limite di tempo della sintesi bloccante, prompt STT italiano |
| `tests/test_voice_wake.py` | 27 | wake word tollerante, comando estratto, avvio automatico disattivabile, conferma vocale senza wake word, scadenza e annullamento, limite di durata, stop esplicito, microfono bloccato, protezione half-duplex (nessuna registrazione durante la sintesi, frammenti contaminati scartati, pausa dopo la sintesi) |
| **Totale** | **318** | |

I conteggi sono quelli osservati con `unittest`. Se si aggiungono test, aggiornare
questa tabella.

## 3. Cosa coprono i test

### Sicurezza

- Il livello A viene auto-approvato secondo configurazione.
- Il livello B richiede conferma salvo allow-list esplicita per nome.
- Il livello C non è mai auto-approvato, nemmeno se inserito in configurazione.
- `robot.estop` e `robot.stop` non vengono mai messi in attesa di conferma.
- Un pending scaduto non viene eseguito.
- Un rifiuto dell'utente non esegue l'azione.
- Strumenti inesistenti e argomenti invalidi producono attività fallite e audit.
- Il path guard nega percorsi fuori dalle radici, file sensibili e symlink.
- La shell rifiuta stringhe arbitrarie e comandi non in enum.
- `web.fetch` rifiuta loopback e reti private (dove testato).
- La dashboard rifiuta il bind non-loopback senza `ui.allow_remote`.

### Vincolo gratuito

- Il provider predefinito è Ollama locale e il fallback è offline.
- L'endpoint OpenAI-compatible predefinito è locale.
- Un endpoint pubblico senza `allow_remote=true` viene rifiutato dalla configurazione.
- Un endpoint pubblico può essere abilitato solo esplicitamente.
- Un endpoint privato di rete è accettato.
- La chiave API è opzionale per i server locali e obbligatoria solo se configurata.
- Ogni preset online dichiara endpoint HTTPS compatibile OpenAI, licenza e data di
  verifica; le condizioni dichiarano l'assenza di carta di credito.
- Un preset online senza `ai.online.consent = true` viene rifiutato da `Config` e dal
  factory.
- Il default del repository resta `ai.provider = "ollama"` e `consent = false`.
- Il fallback di un preset resta locale (`offline`) e non può essere online.
- Senza chiave il provider online risulta non disponibile, con nota esplicita.
- La sonda `/models` non viene chiamata senza chiave: nessun traffico nei test.
- `pyproject.toml` non dichiara dipendenze Python obbligatorie.
- Le dipendenze opzionali restano nella lista verificata (`paho-mqtt`).
- Nessun host IA commerciale noto è cablato nel codice.
- La configurazione predefinita non contiene campi di fatturazione o piani.

### Robot

- Il simulatore parte in `TEST` e non calibrato.
- `READY` viene rifiutato senza calibrazione.
- I limiti per giunto vengono applicati; le posizioni fuori limite vengono rifiutate.
- Velocità e accelerazione fuori range vengono riportate al massimo consentito.
- La deadline viene rispettata o il comando viene rifiutato.
- L'E-stop latches e blocca i movimenti.
- Il reset richiede `operator_ack` e non riprende il movimento.
- Lo stop porta in `HOLD`.
- Il watchdog scatta senza heartbeat e porta in `SAFE`.
- Lo stesso `req_id` non viene eseguito due volte.
- `seq` viene controllato.
- Un dispositivo non può inviare comandi di movimento.
- Ogni esito simulato dichiara `simulated` e nessun movimento fisico.

### Interfacce

- La CLI costruisce i comandi attesi.
- Il server HTTP risponde su stato, cronologia, conferme, attività e robot.
- `/api/state` include informazioni di sistema locali reali e `voice.speaking`.
- La dashboard usa solo risorse locali, non usa `innerHTML` e non scrive stili inline.
- Gli otto stati del nucleo sono presenti sia nel JS sia nel CSS e derivano da
  segnali reali (attività `in_corso`, conferma pendente, `voice.speaking`,
  disponibilità del provider, errore reale, latch E-stop).
- Le tre aree, il layout responsivo, lo schermo intero e il movimento ridotto sono
  verificati staticamente.
- Accessibilità statica: skip link, `:focus-visible`, `aria-live`, dialog, focus trap,
  `Esc`, stato non comunicato solo dal colore.
- Gli header di sicurezza sono presenti.
- La voce riporta correttamente disponibilità di STT e registratore.
- Il pulsante «Ascolta «Amy»» esiste e chiama l'avvio solo dentro il gestore del
  click: nessun ascolto automatico al caricamento.
- Gli endpoint `/api/voice/wake/start` e `/stop` avviano e fermano il ciclo; senza
  configurazione esplicita l'avvio restituisce `400`.
- Lo stato `speaking` del servizio vocale riflette la sintesi reale e si azzera con
  `stop_speaking`.
- L'elenco delle voci TTS viene calcolato una sola volta (cache): ogni richiesta di
  stato non riesegue `say -v ?`.
- Il backend si chiude quando il heartbeat del genitore sparisce o invecchia: il
  server locale non resta orfano.
- L'app nativa usa solo framework di sistema, non contiene risorse esterne e non
  espone il backend fuori dal loopback.

## 4. Smoke test eseguiti realmente

| Comando | Esito |
| --- | --- |
| `python3 -m amy doctor` | Ollama raggiungibile, modello installato, TTS su file riuscito (58.276 byte), STT e registratore segnalati come mancanti |
| `python3 -m amy ask "che ore sono?" --offline` | Risposta italiana corretta |
| `python3 -m amy ask "rispondi solo con: ciao"` | Risposta `ciao` dal modello Ollama reale |
| `python3 -m amy robot status` | Simulatore in `TEST`, non calibrato, `simulated: true`, `physical_motion: false` |
| `python3 -m amy voice status` | TTS, STT `faster-whisper` e registratore `sounddevice` disponibili; `ready_for_voice_commands: true` |
| `POST /api/voice/listen` | Registrazione reale di 6 s con «Amy, che ore sono?» dagli altoparlanti → trascrizione «Emi, che ore sono?» |
| `POST /api/voice/wake/start` | Wake word rilevata dal parlato, comando `che ore sono` eseguito, risposta «Sono le 17:21 del 31/10/2026.» pronunciata e scritta in chat |
| `python3 -m amy memory sessions` | Sessione con conteggio messaggi reale |
| `python3 apps/AmyCore/selftest.py` | App nativa: dashboard montata nella WebView, messaggio inviato dal DOM, risposta in chat, backend chiuso |
| SIGKILL dell'app | Il backend si chiude entro ~10 s grazie al watchdog heartbeat: nessun processo orfano |

Questi smoke test non sono test automatici: vanno rieseguiti manualmente dopo
modifiche a provider, voce, robot o dashboard.

Nota: la verifica del provider richiede `ollama serve` attivo. Se il servizio non è
in esecuzione, `amy doctor` mostra `ATTENZIONE` su «Motore IA» e Amy usa il fallback
offline, senza fingere che il modello sia disponibile.

## 5. Cosa NON è verificato

| Area | Perché | Cosa manca |
| --- | --- | --- |
| Movimento fisico | Nessun hardware | Robot, alimentazione, banco di prova |
| E-stop fisico | Nessun hardware | Prova sotto carico secondo `../amy/docs/07_sicurezza.md` |
| MQTT reale | Nessun broker | Broker, credenziali, dispatcher sul Pi |
| ACK/NACK reali | Nessun nodo | ESP32-L e ESP32-T collegati |
| Watchdog reale | Solo simulazione | Perdita heartbeat su hardware |
| Qualità STT su più parlanti | Una sola voce di prova | Trascrizioni con voci diverse, rumore, accenti |
| Wake word acustica | Solo testuale | Filtro acustico dedicato a basso consumo |
| Consumo CPU prolungato | Test brevi | Misura su ore di ciclo continuo |
| Dashboard remota | Volutamente non esposta | Autenticazione, se mai necessaria |
| Uso prolungato | Solo test brevi | Prove di ore/giorni, memoria, log |
| Sicurezza di rete | Solo loopback | Minaccia reale su rete locale |

## 6. Test manuale consigliato

### Configurazione

```bash
python3 -m amy init
python3 -m amy config show
python3 -m amy config path
```

Verificare che il file sia in `~/.amy/config.json` con permessi `0600`.

### Provider

```bash
ollama list
python3 -m amy ask "rispondi solo con: ciao"
python3 -m amy ask "che ore sono?" --offline
```

Se Ollama non è attivo, il fallback deve essere visibile nello stato, non nascosto.

### File

```bash
python3 -m amy ask "elenca i file in ~/Progetti" --offline
```

Verificare che un percorso fuori dalle radici venga negato.

### Voce

```bash
python3 -m amy voice speak "Prova di sintesi"
python3 -m amy voice status
```

La sintesi deve essere udibile. Se non lo è, controllare volume e voce configurata.

Ascolto e wake word richiedono microfono e modello locale:

```bash
python3 -m amy voice listen --seconds 6   # se il comando è disponibile
python3 -m amy voice loop                 # trascrive senza eseguire
python3 -m amy voice loop --execute       # esegue e pronuncia la risposta
```

Nella dashboard il pulsante «Ascolta «Amy»» avvia lo stesso ciclo dell'app; il
pulsante «Stop voce» interrompe solo la sintesi. Un ascolto non parte mai da solo:
verificare che lo stato `running` resti falso finché non si preme il pulsante.

`python3 -m amy doctor` apre il microfono per un secondo e scarta l'audio: la voce
«Microfono» distingue «il modulo è installato» da «l'ingresso audio risponde
davvero». Se Core Audio si blocca nel HAL, la verifica termina con una nota e il
backend non resta appeso: la registrazione ha un limite di tempo
(`durata + 6 s`, oppure il valore passato come `timeout`), oltre il quale Amy
risponde «Il microfono non risponde» e sospende i tentativi per 60 secondi.

Prova end-to-end con parlato reale, senza hardware aggiuntivo:

```bash
say -v Alice "Amy, che ore sono?"
```

Con il ciclo attivo il log deve contenere `Wake word rilevata`, la trascrizione deve
mostrare la domanda e la risposta, e la risposta deve essere pronunciata. Attenzione:
Amy sente anche i propri altoparlanti, quindi una frase trascritta male o un rumore
può produrre un falso positivo; il log lo rende visibile.

### Robot simulato

```bash
python3 -m amy robot status
python3 -m amy robot ping
python3 -m amy robot stop
python3 -m amy robot estop
python3 -m amy robot reset --confirm
```

Ogni risposta deve dichiarare `simulated: true`. Nessuna deve suggerire movimento
fisico.

### Dashboard

```bash
python3 -m amy serve --open-browser
```

Verificare:

- chat, cronologia e invio con `Invio` / `Shift+Invio`;
- conferma di un'azione di livello B e annullamento con `Esc`;
- nessuna conferma eseguita prima della risposta;
- pannello sistema con valori reali e pannello voce con `speaking` coerente;
- E-stop e stop, con etichetta «E-STOP SOFTWARE»;
- stato `offline` quando Ollama è fermo e fallback disponibile;
- ridimensionamento della finestra fino alla dimensione minima e layout a una colonna;
- schermo intero ed uscita;
- navigazione da tastiera, focus visibile, focus trap nelle modali;
- interruttore «Movimento» e rispetto di `prefers-reduced-motion`;
- assenza di errori in console;
- nessuna richiesta a domini esterni.

Dettagli dell'interfaccia: [INTERFACCIA.md](INTERFACCIA.md).

### Applicazione nativa

```bash
./apps/AmyCore/build.sh
python3 apps/AmyCore/selftest.py
open "apps/AmyCore/dist/Amy Core.app"
```

Lo self-test eseguito davvero il 31 ottobre 2026 ha verificato: avvio dell'app,
backend in ascolto su `127.0.0.1`, dashboard montata nella WebView (titolo e stato
del nucleo letti dal DOM), invio di un messaggio reale dal form della chat, risposta
in chat («Sono le 08:24 del 31/10/2026.») e chiusura del backend all'uscita.

Verificare a mano (non ancora eseguito):

- aspetto dei pannelli e del nucleo nella finestra reale;
- ridimensionamento fino alla dimensione minima e layout a una colonna;
- schermo intero dal menu e pulsante «Schermo intero» della UI;
- navigazione da tastiera e focus visibile;
- interruttore «Movimento» e rispetto di `prefers-reduced-motion`;
- icona nel Dock e menu dell'app;
- comportamento con Ollama fermo (stato `offline`).

## 7. Come aggiungere un test

1. Scegliere il file corrispondente al modulo.
2. Riprodurre il comportamento con il caso più piccolo.
3. Verificare sia il caso positivo sia il rifiuto.
4. Per una nuova azione pericolosa, testare policy, conferma e audit.
5. Aggiornare la tabella di questo documento.
6. Rieseguire l'intera suite, non solo il nuovo test.

## 8. Criterio di verità

Un'affermazione è accettabile solo se:

- esiste codice che la implementa;
- esiste un test che la copre, quando è testabile in locale;
- esiste una verifica reale, quando dipende da hardware o servizi esterni;
- la documentazione dice chiaramente cosa non è stato verificato.

In caso di dubbio, la formulazione corretta è «implementato ma non verificato», non
«funziona».
