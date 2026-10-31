# Changelog

Formato ispirato a Keep a Changelog. Le date sono in UTC. Il progetto è in fase
iniziale: non tutte le voci sono state verificate su hardware.

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
- Test suite con 168 test.
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
