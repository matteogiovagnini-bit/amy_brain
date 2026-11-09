# Interfaccia — Amy Core

L'interfaccia locale di Amy è **un'applicazione macOS nativa**: `Amy Core.app`,
scritta in Swift con AppKit e WebKit. Finestra propria, icona nel Dock, menu con
scorciatoie, schermo intero nativo. Non è un mockup: ogni pannello legge dati
reali dal backend tramite le API HTTP locali e dichiara esplicitamente ciò che non
è disponibile.

La stessa interfaccia è anche servita come **console web locale** dal comando
`python3 -m amy serve`: è il canale di fallback e di debug (per esempio da un
terminale o da un browser remoto sulla stessa macchina). Backend e frontend sono
identici in entrambi i casi.

Identità visiva: **Amy Core**. Sfondo nero/notte, firma ciano e blu elettrico,
nucleo centrale con anelli e archi originali disegnati in SVG e CSS. Attorno al
nucleo fluttua un **campo di neuroni** su canvas: nodi luminosi, dendriti brevi e
sinapsi tra vicini. Sopra gli anelli, un **HUD radiale** in SVG mostra archi
segmentati, tacche e quattro etichette con dati reali (IA, MEM, VOICE, ROBOT).
Tutto è disegnato in locale, senza immagini né risorse esterne. Per contenere
CPU e temperatura, neuroni e archi si animano solo durante un'interazione
(conversazione, elaborazione, voce, conferma): in attesa e offline restano
visibili ma statici. Il campo neuronale si ferma anche quando la scheda o la
finestra perdono il fuoco; con «Movimento: ridotto» mostra un solo fotogramma. Nessun font remoto, nessuna CDN, nessuna immagine di terze parti.

## 1. Avvio

### Applicazione (canale principale)

```bash
# Compila (solo tool di sistema: swiftc, iconutil, codesign)
./apps/AmyCore/build.sh

# Prova
open "apps/AmyCore/dist/Amy Core.app"

# Installa per l'utente
mkdir -p ~/Applications && cp -R "apps/AmyCore/dist/Amy Core.app" ~/Applications/
```

L'app:

1. cerca il repository di Amy Brain (percorso salvato in `~/.amy/app.json`, altrimenti
   chiesto una volta con un selettore di cartelle);
2. avvia il backend Python come processo figlio, legato solo a `127.0.0.1`, sulla
   prima porta libera da 8765 in su;
3. mostra la dashboard in una `WKWebView` nativa;
4. scrive un heartbeat ogni 2 secondi: se l'app muove, il backend si chiude da
   solo entro pochi secondi (nessun processo orfano);
5. alla chiusura della finestra ferma il backend e cancella i file di stato.

Menu dell'app: Informazioni, Apri cartella configurazione, Apri log, Ricarica
dashboard (`⌘R`), Schermo intero (`⌘F`), Modifica (copia/incolla), Finestra. Il
pulsante «Schermo intero» della UI usa la Fullscreen API del web, il menu usa lo
schermo intero nativo della finestra.

Per la verifica visiva automatica lo stesso binario accetta `--snapshot <percorso>`
e `--snapshot-size WxH`: carica la dashboard, salva un PNG della `WKWebView` e
termina. Non è un secondo programma: è l'app in modalità di prova, utile quando il
terminale non ha il permesso di cattura schermo.

Requisiti: macOS 12 o superiore e **Xcode Command Line Tools** (gratuite, già
presenti su questo computer). Non serve installare nulla.

### Console web (canale alternativo)

```bash
python3 -m amy serve --open-browser
```

- indirizzo predefinito: `http://127.0.0.1:8765`
- host e porta: `--host` / `--port` (il bind non locale richiede
  `ui.allow_remote=true`)
- nessuna autenticazione: l'esposizione in rete resta volutamente sconsigliata

La dashboard funziona anche senza Ollama: in quel caso il nucleo mostra lo stato
`offline` e la chat usa il fallback locale se configurato.

## 2. Struttura

```text
┌──────────────────────────────────────────────────────────────┐
│ topbar: marchio · pillole di stato · azioni                  │
├──────────────────────────────────────────────────────────────┤
│ ┌───────────┐                                                │
│ │ pannelli  │        nucleo a tutto schermo                  │
│ │ sovrap-   │   anelli, stato, attività, provider            │
│ │ posti     │                                ┌─────────────┐ │
│ │ a sinistra│       ┌───────────────┐        │    chat     │ │
│ │           │       │ barra comandi │        │  satellite  │ │
│ └───────────┘       └───────────────┘        └─────────────┘ │
├──────────────────────────────────────────────────────────────┤
│ footer: percorso configurazione · stato sintetico            │
└──────────────────────────────────────────────────────────────┘
```

- **Nucleo** (tutto il palco): pannello a piena area, senza bordo né card
  contenitiva. Anelli, stato testuale, attività reale e disponibilità del provider.
  Il fondo è un alone radiale, non un riquadro. Nel palco il pulsante «Nuova
  interazione» è nascosto perché il campo di scrittura è sempre visibile; nel flusso
  verticale ricompare.
- **Chat** (satellite a destra, quasi tutta l'altezza del palco): cronologia reale
  della sessione, `Invio` per inviare, `Shift+Invio` per andare a capo, «Nuova»,
  «Stop voce» e pulsante microfono solo se il backend dichiara STT e registratore
  disponibili. Non contiene il compositore. Fluttua sopra il palco con un arco
  luminoso che la collega idealmente al nucleo; i messaggi tagliati dai bordi
  sfumano invece di restare visibili a metà.
- **Barra comandi** (in basso al centro del palco, staccata dalla chat): campo di
  scrittura, microfono, «Invia», promemoria da tastiera e interruttore «Pronuncia le
  risposte». Conserva gli stessi identificativi di prima (`chatForm`,
  `composerInput`, `micBtn`, `sendBtn`, `speakToggle`), quindi c'è un solo punto di
  invio e la cronologia resta nella chat. Il nucleo riserva spazio in fondo per non
  finire sotto la barra.
- **Pannelli informativi** (sovrapposti a sinistra): motore IA, robot, sistema,
  voce, memoria, attività recenti, **prossimi appuntamenti** e catalogo strumenti.
  Le schede si accavallano di pochi pixel e si sollevano con hover o focus da
  tastiera; il contenuto scorre dentro il pannello e l'ultimo tratto sfuma verso il
  palco. Il robot è il secondo pannello perché contiene l'E-stop software. Il
  riquadro del calendario è il settimo; il catalogo strumenti resta l'ultimo.
- **Topbar**: oltre a movimento, schermo intero e impostazioni, due azioni vocali:
  «Ascolta «Amy»» (diventa «Ferma ascolto» mentre il ciclo continuo è attivo,
  con `aria-pressed` che segue lo stato reale) e «Stop voce» (interrompe la sintesi).
  Il pannello Voce mostra inoltre la riga «Saluto iniziale» e il pulsante «Ripeti
  saluto», che riproduce il messaggio di avvio con la stessa sintesi locale.
- **Sfondo**: campo stellato statico, disegnato con un SVG inline e stelle generate
  localmente, sopra il gradiente notte e la griglia. Nessuna immagine, nessun filmato
  e nessuna animazione: non pesa sulla GPU e resta compatibile con la CSP.

Finestre e modali: conferma di rischio, impostazioni, toast. Sopra 1040 px il layout
è a strati sovrapposti, con la barra comandi sopra il palco; sotto 1040 px diventa un
flusso verticale con la chat subito dopo la topbar, poi la barra comandi, poi il
nucleo e infine i pannelli. Sotto 680 px tutto è una colonna. La finestra minima
dell'app nativa è 960×600: a quell'altezza il flusso verticale evita che chat, nucleo
e pannelli si coprano.

## 3. Palette e token

I colori sono definiti una sola volta in `style.css` come variabili CSS.

| Token | Valore | Uso |
| --- | --- | --- |
| `--bg-0` / `--bg-1` | `#03060d` / `#060b16` | sfondo notte |
| `--panel` | `rgba(10, 18, 33, 0.84)` | pannelli |
| `--text` | `#e9f3ff` | testo principale |
| `--muted` / `--dim` | `#96adc6` / `#6b829c` | testo secondario |
| `--cyan` | `#3fe3ff` | firma, focus, stato attivo |
| `--cyan-2` / `--blue` | `#26c7ff` / `#2f7bff` | archi e gradienti |
| `--ok` | `#45e3a4` | disponibile |
| `--warn` | `#ffc46b` | attenzione, conferma, simulato |
| `--bad` | `#ff6478` | errore, E-stop, non disponibile |

Ambra e rosso non sono decorativi: indicano condizioni che richiedono attenzione.
Lo stato non è mai comunicato solo dal colore: c'è sempre un'etichetta testuale.

## 4. Stati del nucleo

Il nucleo ha otto stati. Sono derivati **solo** da segnali reali del backend, mai da
timer casuali o animazioni finte.

| Stato | Quando appare | Segnale reale |
| --- | --- | --- |
| `idle` | nessuna operazione in corso | stato applicativo stabile |
| `listening` | registrazione dal microfono in corso | richiesta `/api/voice/listen` attiva |
| `processing` | richiesta chat o conferma in corso | richiesta HTTP in corso |
| `speaking` | sintesi vocale in corso | `voice.speaking` reale (TTS) |
| `executing` | uno strumento è in esecuzione | attività con `status = "in_corso"` |
| `waiting_confirmation` | c'è una conferma pendente | pending reale o `pending_confirmations > 0` |
| `error` | errore restituito o E-stop attivo | risposta di errore, errore di rete, `estop_latched` |
| `offline` | nessun motore IA disponibile | provider primario e fallback non disponibili |

Ordine di priorità: conferma → errore → E-stop → esecuzione → ascolto → elaborazione
→ sintesi → offline → pronta. Una conferma pendente non viene mai coperta da uno
stato meno importante.

Ogni stato cambia colore, animazione e testo (`#coreState`, `#coreActivity`,
`#coreHint`) e aggiorna `aria-label` sul contenitore `#amyCore`.

## 5. Dati reali, dati assenti

- Il pannello **Sistema** usa `collect_system_info()` (`amy/core/system_info.py`):
  versione macOS, architettura, versione Python, numero di CPU, carico medio e spazio
  disco, tutti letti con la libreria standard. Nessuna telemetria. Il nome del
  sistema viene composto da `os_name` e `os`, senza prefissi inventati.
- Il pannello **Motore IA** legge `provider.status()`: provider, modello, endpoint,
  fallback e disponibilità effettiva. Se Ollama risponde ma il modello configurato
  non è installato, la UI lo dichiara come «modello mancante» invece di mostrare
  «disponibile». Se è attivo un preset online gratuito e manca la chiave API, mostra
  «chiave API non configurata» con il nome della variabile; se è configurata ricorda
  che la conversazione lascia il Mac e usa il servizio scelto.
- Il pannello **Voce** legge `voice.status()`: TTS, STT, registratore, wake word,
  `speaking` reale e il messaggio di avvio (`startup_greeting`). Il testo del saluto
  mostrato è quello dichiarato dal backend, non una stringa fissa in JavaScript.
- Il pannello **Robot** legge `robot.status()`. Con il simulatore etichetta i valori
  come simulati/stimati; per MQTT mostra lo stato ricevuto e ricorda che il movimento
  fisico non è verificato.
- Batteria, temperatura, stato del Raspberry Pi e movimento fisico **non** vengono
  inventati: se il backend non li fornisce, la UI mostra `Non disponibile` o
  `Non collegato`.
- I campi non configurati mostrano `Non configurato`, non zero.
- Il pannello **Moduli** legge `GET /api/modules`: per ogni modulo mostra manifest,
  stato reale (`ready`, `degraded`, `offline`, `disabled`, …), dettaglio, numero di
  strumenti e interruttore. Disabilitare un modulo rimuove i suoi strumenti dal
  catalogo attivo; **Memory** è essenziale e non può essere spento. Lo stato dei
  toggle è a runtime: al riavvio i moduli tornano abilitati.
- Il pannello **Progetto** legge `GET /api/dev/status`: mostra ramo, modifiche,
  ultimo commit e diff statistico. Non esegue test e non modifica file; il
  pulsante «Aggiorna» ripete la sola lettura. Il codice vive in `static/project.js`,
  caricato prima di `app.js`.
- Il pannello **Log recenti** legge `GET /api/logs`: mostra le ultime righe del
  solo file configurato in `logging.file`, già redatte. Non accetta percorsi
  arbitrari e non espone segreti.
- Il pannello **Attività e note** legge i campi `tasks` e `notes` di
  `GET /api/state`: mostra le attività con stato, priorità e scadenza e le note
  recenti. Creazione e modifica avvengono tramite gli strumenti di Amy.
- Il pannello **Permessi** legge `GET /api/permissions`: elenca le capacità dei
  moduli e permette di revocarle o ripristinarle. Una capacità revocata blocca
  gli strumenti corrispondenti; il livello C resta sempre soggetto a conferma.
- Il pannello **Prossimi appuntamenti** legge `GET /api/calendar/upcoming`: il
  backend esegue `calendar.events` (livello A, sola lettura) per ogni giorno dei
  prossimi 7, scarta gli eventi già terminati, unisce gli eventi che coprono più
  giorni e limita l'elenco a 8 voci. Il calendario, la finestra e l'eventuale
  lettura parziale sono dichiarati; se Calendar.app non risponde il pannello
  mostra «Calendario non disponibile» con il motivo, senza inventare appuntamenti.

## 6. Funzioni reali

- Invio messaggi a `/api/chat` con sessione corrente e cronologia da
  `/api/transcript`.
- Conferme in due fasi: `/api/pending` e `/api/confirm`, con dettagli su rischio,
  argomenti, conseguenze e annullamento.
- Nuova sessione: `/api/new_session`.
- Voce: `/api/speak`, `/api/voice/listen`, `/api/voice/stop`, `/api/voice/greet`
  e il ciclo continuo `/api/voice/wake/start` e `/api/voice/wake/stop`.
- Robot: `/api/robot/estop` e `/api/robot/stop`.
- Moduli: `GET /api/modules`, `GET /api/modules/{name}` e
  `POST /api/modules/{name}/enabled` con `{"enabled": true|false}`. Il toggle è
  a runtime e aggiorna il catalogo strumenti; Memory non è disabilitabile.
- Permessi: `GET /api/permissions`, `POST /api/permissions/revoke` e
  `POST /api/permissions/restore` con `{"capability": "..."}`. La revoca è a
  runtime e impedisce l'esecuzione degli strumenti collegati.
- Aggiornamento stato da `/api/state`, polling base ogni 5 s e più frequente
  (1 s) durante un turno, un'attività, l'ascolto o la sintesi.
- Calendario da `/api/calendar/upcoming`, con polling separato ogni 2 minuti,
  rilettura quando la pagina torna visibile e pulsante «Aggiorna». Non blocca
  l'avvio della chat.
- Errori di rete e del backend mostrati in chat, nel footer e nello stato `error`
  per 8 secondi.

## 7. Funzioni assenti per scelta

- Nessun pulsante per interrompere la generazione della risposta: il backend non
  espone questa operazione. «Stop voce» interrompe solo la sintesi.
- Il microfono può restare in ascolto all'avvio se
  `voice.wake_word.start_on_launch` è attivo; il pulsante «Ferma ascolto» lo
  interrompe. Il saluto di avvio usa solo la sintesi e non registra.
- Nessun dato remoto, nessuna telemetria, nessuna sincronizzazione cloud.
- Nessuna modifica del file di configurazione dalla UI: i toggle dei moduli sono
  a runtime e il file va modificato a mano per renderli permanenti.
- Nessun secondo programma a schermo intero: si usa il Fullscreen API del browser,
  più il controllo nativo di macOS.

## 8. Accessibilità

- Skip link verso la chat, landmark semantici, etichette `aria-label`.
- `:focus-visible` sempre visibile su pulsanti, input, link e summary.
- `role="log"` e `aria-live` sulla cronologia; `role="status"` sullo stato.
- Modali con `role="dialog"`, `aria-modal`, focus trap, `Esc` per annullare o
  chiudere, ritorno del focus all'elemento precedente.
- Stato comunicato da testo e icona, non solo dal colore.
- Rispetto di `prefers-reduced-motion` e interruttore «Movimento» con preferenza
  salvata in `localStorage`.
- Tastiera: `Invio` invia, `Shift+Invio` va a capo, `Tab` attraversa i controlli.

## 9. Sicurezza e CSP

Il server invia una Content-Security-Policy restrittiva. Di conseguenza il frontend:

- non usa `style` inline né scritture `.style` da JavaScript;
- non usa `innerHTML`, `document.write` o `eval`;
- non carica risorse esterne: solo `/static/style.css` e `/static/app.js`;
- inserisce il testo del modello con `textContent` e nodi DOM, mai come HTML;
- non legge database o chiavi API: parla solo con le API locali.

L'E-stop della dashboard è etichettato **E-STOP SOFTWARE** e il pannello ricorda che
non sostituisce l'E-stop fisico in serie al bus dei servi. La conferma di rischio non
viene mai aggirata dalla UI.

## 10. File coinvolti

| File | Ruolo |
| --- | --- |
| `apps/AmyCore/Sources/AmyCoreApp.swift` | app nativa: finestra, WebView, backend, heartbeat, menu |
| `apps/AmyCore/Tools/make_icon.swift` | generatore dell'icona (CoreGraphics, nessuna risorsa esterna) |
| `apps/AmyCore/build.sh` | build del bundle `.app` con tool di sistema e firma ad-hoc |
| `apps/AmyCore/selftest.py` | self-test end-to-end dell'app (solo libreria standard) |
| `apps/AmyCore/Resources/Info.plist` | metadati del bundle e ATS locale |
| `amy/ui/static/index.html` | palco, nucleo a tutto schermo, chat satellite, barra comandi, campo stellato, pannelli sovrapposti, modali |
| `amy/ui/static/style.css` | token, layout, stati, animazioni, responsive, reduced motion |
| `amy/ui/static/app.js` | stato, polling, chat, conferme, pannelli, accessibilità, fullscreen |
| `amy/ui/static/neurons.js` | campo neuronale decorativo su canvas, con reduced motion e pausa a scheda nascosta |
| `amy/ui/static/project.js` | pannello Progetto in sola lettura, primo modulo locale estratto da `app.js` |
| `amy/ui/server.py` | server HTTP locale, API, header di sicurezza, watchdog heartbeat |
| `amy/core/system_info.py` | informazioni locali di sistema |
| `amy/core/assistant.py` | `status()` con `system`, `tool_context()`, `upcoming_events()`, chat e conferme |
| `amy/tools/calendar_tools.py` | strumenti `calendar.*` e raccolta dei prossimi appuntamenti |
| `amy/voice/service.py` | stato voce con `speaking` reale |
| `amy/voice/tts.py` | TTS macOS con elenco voci in cache |

## 11. Verifica

Test automatici:

```bash
python3 -m compileall -q amy tests
python3 -m unittest tests.test_ui_static tests.test_system_info tests.test_voice_service -v
python3 -m unittest discover -s tests -t . -v

# Self-test dell'app nativa
./apps/AmyCore/build.sh && python3 apps/AmyCore/selftest.py
```

Copertura specifica dell'interfaccia:

- `tests/test_ui_static.py`: file, endpoint attesi, nessuna risorsa esterna, nessun
  `innerHTML`, nessuno stile inline, otto stati nel JS e nel CSS, derivazione da
  segnali reali, tre aree, accessibilità, reduced motion, fullscreen, responsive,
  dati assenti dichiarati, E-stop etichettato come software, riquadro del
  calendario e polling separato.
- `tests/test_calendar.py`: raccolta dei prossimi appuntamenti tramite
  `calendar.events`, filtro, deduplica, limite, fallimenti dichiarati e blocco se
  il tool non è più di livello A.
- `tests/test_server.py`: `GET /api/calendar/upcoming` con AppleScript sostituito
  da mock, calendario non leggibile e limite della finestra.
- `tests/test_system_info.py`: campi reali, disco, nessun segreto.
- `tests/test_voice_service.py`: `speaking` riflette il TTS reale.
- `tests/test_tts_cache.py`: l'elenco delle voci è calcolato una sola volta.
- `tests/test_server.py`: `/api/state` include `system` e `voice.speaking`.
- `tests/test_server_watchdog.py`: il backend si chiude se il heartbeat del
  genitore sparisce o invecchia (nessun processo orfano).
- `tests/test_native_app.py`: sorgenti, bundle, sole dipendenze di sistema, nessuna
  risorsa esterna, backend legato al loopback, heartbeat presente.

Il **self-test dell'app** (`apps/AmyCore/selftest.py`) avvia l'app reale, aspetta
che la WebView monti la dashboard, invia un messaggio dal DOM (`requestSubmit` sul
form della chat), verifica che la risposta compaia in chat e controlla che il backend
venga chiuso. Esito del 31 ottobre 2026: self-test superato.

Esito del 31 ottobre 2026: **189 test, tutti superati**. Esito del 6 novembre 2026:
**467 test, tutti superati** (9 novembre 2026). La verifica **visiva a mano** nella finestra
(ridimensionamento, schermo intero, navigazione da tastiera, movimento ridotto,
aspetto dei pannelli, compreso quello del calendario) non è stata eseguita: non
viene dichiarata come eseguita.

## 12. Licenze e costo

L'interfaccia è codice originale del progetto (licenza MIT del repository). Non usa
librerie frontend, font, icone o servizi esterni: quindi non introduce dipendenze a
pagamento. Usa solo API native del browser (Fullscreen, `matchMedia`, `fetch`,
`localStorage`) e la libreria standard Python lato server.

L'app nativa usa **solo framework di sistema macOS** (AppKit, WebKit, Foundation,
Darwin) e gli strumenti di `Xcode Command Line Tools` (`swiftc`, `iconutil`,
`codesign`), gratuiti e già presenti su questo computer. L'icona è generata
localmente con CoreGraphics: nessun file immagine di terze parti. La firma è ad-hoc,
quindi nessun certificato a pagamento e nessun account sviluppatore. Vale il vincolo
`solo strumenti gratuiti` descritto in [GRATUITO.md](GRATUITO.md).
