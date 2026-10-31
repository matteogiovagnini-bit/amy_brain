# Decisioni tecniche

Registro sintetico delle scelte che vincolano il progetto. Ogni decisione indica
contesto, scelta e conseguenze. Non è un diario di ogni modifica: per quello c'è
[CHANGELOG.md](CHANGELOG.md).

## D-001 — `amy_brain` è il cervello L2, non il firmware

**Contesto:** esistono già il repository `../amy/` con hardware, protocollo e
documentazione canonica.

**Scelta:** `amy_brain` contiene assistente, policy, memoria, strumenti macOS e link
al robot. Non duplica protocollo, pinout o firmware.

**Conseguenze:** ogni dettaglio hardware va linkato a `../amy/docs/`. Modifiche al
robot reale richiedono interventi nel repository canonico, non solo qui.

## D-002 — Python 3.9, libreria standard prima

**Contesto:** l'ambiente di riferimento ha Python 3.9.6 e non tutte le dipendenze
sono installate.

**Scelta:** il nucleo funziona con la sola libreria standard. `paho-mqtt` è opzionale
per MQTT; STT e registratore sono opzionali.

**Conseguenze:** meno attrito di installazione, ma alcune funzioni vocali e MQTT
restano non disponibili finché l'utente non installa altro.

## D-003 — Il modello propone, il codice decide

**Contesto:** un LLM può inventare strumenti, argomenti o esiti.

**Scelta:** il modello emette un JSON con una sola azione. Il codice valida schema e
rischio e decide se eseguire, chiedere conferma o rifiutare.

**Conseguenze:** il prompt non è una frontiera di sicurezza. Gli errori di formato
non eseguono nulla.

## D-004 — Livelli A/B/C con C mai automatico

**Contesto:** servono azioni ordinarie, azioni con impatto e azioni irreversibili.

**Scelta:** A auto-approvato se configurato; B su conferma o allow-list per nome;
C sempre su conferma esplicita.

**Conseguenze:** anche una configurazione errata non può auto-approvare C. In CLI il
livello C richiede la parola `CONFERMO`. La dashboard mostra una conferma dedicata.

## D-005 — Conferma in due fasi

**Contesto:** il turno conversazionale non deve bloccarsi in attesa dell'utente.

**Scelta:** `handle()` restituisce `confirmation_required` e un `pending`;
`resolve_confirmation()` esegue o annulla e riprende il turno.

**Conseguenze:** la richiesta può vivere nella CLI, nella dashboard o in un client
futuro. Esiste una TTL configurabile. Il pending non è persistito su disco.

## D-006 — E-stop e stop fuori dalla policy di conferma

**Contesto:** un arresto non può dipendere dall'approvazione del modello o
dall'utente che conferma un'altra azione.

**Scelta:** `robot.estop` e `robot.stop` sono livello A e non richiedono conferma.
L'E-stop software ha priorità assoluta nel simulatore e nel link.

**Conseguenze:** restano sempre disponibili. L'E-stop fisico rimane l'unico arresto
garantito: il software non può sostituirlo.

## D-007 — Nessun GPIO/PWM, solo comandi di alto livello

**Contesto:** il controllo diretto degli attuatori moltiplica i rischi e ignora la
sicurezza del firmware.

**Scelta:** Amy espone solo comandi come movimento per giunto, stop, reset,
modalità e stato.

**Conseguenze:** i limiti e la sicurezza appartengono al robot. Amy non può aggirare
il firmware.

## D-008 — Simulatore predefinito, MQTT sperimentale

**Contesto:** non c'è hardware disponibile durante lo sviluppo.

**Scelta:** il trasporto predefinito è `simulated`. MQTT è implementato ma etichettato
sperimentale e non verificato.

**Conseguenze:** nessuna demo può far credere che ci sia movimento fisico. Ogni esito
simulato dichiara `simulated: true` e `physical_motion: false`.

## D-009 — Il simulatore parte in TEST e non calibrato

**Contesto:** una modalità READY simulata potrebbe suggerire una readiness fisica
inesistente.

**Scelta:** mode `TEST`, `zero_offset_deg=None`, `calibrated=False`. READY è
rifiutato finché la calibrazione non è impostata. Solo i test usano
`simulation_calibrate()`.

**Conseguenze:** il simulatore è utile e onesto, ma non prova la calibrazione reale.

## D-010 — Shell a enum chiuso

**Contesto:** una shell arbitraria vanificherebbe la policy.

**Scelta:** solo comandi di sola lettura predefiniti, avviati come lista di argomenti,
senza `shell=True`, con timeout e output limitato.

**Conseguenze:** Amy non è un terminale generale. Nuovi comandi richiedono una
decisione esplicita e test.

## D-011 — File confinati e cancellazioni recuperabili

**Contesto:** l'assistente non deve poter leggere chiavi o distruggere dati.

**Scelta:** radici autorizzate, deny-list per `.ssh`, `.aws`, `.env`, chiavi e simili,
symlink risolti, backup prima della sovrascrittura, cestino Amy al posto della
cancellazione definitiva.

**Conseguenze:** alcune operazioni legittime fuori dalle radici vengono negate.
L'utente può ampliare le radici in configurazione.

## D-012 — Web non attendibile e SSRF bloccato

**Contesto:** una pagina web può contenere istruzioni malevole o puntare alla rete
locale.

**Scelta:** `web.fetch` accetta solo http/https pubblici, risolve l'host e blocca
loopback, link-local, multicast, reserved e reti private. Il contenuto è dato, non
istruzione.

**Conseguenze:** non si possono leggere servizi locali tramite Amy. Resta un rischio
residuo di DNS rebinding non coperto completamente.

## D-013 — Dashboard locale senza dipendenze esterne

**Contesto:** la UI non deve diventare un canale di esfiltrazione o dipendere dal
cloud.

**Scelta:** server Python, HTML/CSS/JS locali, nessun CDN, nessun `innerHTML`, CSP
restrittiva, `X-Frame-Options: DENY`, bind loopback obbligatorio salvo
`ui.allow_remote`.

**Conseguenze:** la dashboard non è pensata per Internet. Non c'è autenticazione:
l'esposizione remota resta sconsigliata anche con il flag.

## D-014 — TTS macOS, STT opzionale

**Contesto:** macOS offre `say`, mentre lo STT richiede dipendenze e permessi.

**Scelta:** TTS nativo sempre disponibile; STT tramite adattatori; registratore
`ffmpeg`/`sox`; wake word testuale dopo trascrizione.

**Conseguenze:** la voce in uscita funziona subito; quella in ingresso no. Non si
simula uno STT assente.

## D-015 — Nessuna registrazione in background non richiesta

**Contesto:** un microfono sempre acceso è un rischio di privacy.

**Scelta:** la registrazione avviene solo su comando esplicito o nel ciclo
`voice loop` avviato dall'utente.

**Conseguenze:** niente wake word sempre attiva per default. Il ciclo continuo va
avviato consapevolmente.

## D-016 — Memoria e audit separati

**Contesto:** la memoria serve alla conversazione; l'audit serve a ricostruire le
decisioni.

**Scelta:** SQLite per la memoria, JSONL append-only per l'audit. Entrambi redigono i
segreti.

**Conseguenze:** l'audit non è modificabile dalla UI. La memoria è ispezionabile,
esportabile e cancellabile.

## D-017 — Nessun commit automatico

**Contesto:** il repository può non avere convenzioni Git consolidate.

**Scelta:** non inizializzare, aggiungere o committare senza richiesta esplicita.

**Conseguenze:** la continuità è affidata a file e documentazione, non a commit
automatici.

## D-018 — Solo strumenti gratuiti, nessun costo obbligatorio

**Contesto:** il progetto deve poter essere sviluppato e usato senza pagamenti
presenti o futuri. Un piano gratuito limitato o una prova non sono garanzie
sufficienti.

**Scelta:** il default è interamente locale: Ollama, `say`, SQLite, simulatore e
strumenti macOS. Il fallback è l'interprete offline, mai un servizio a pagamento.
L'adattatore compatibile OpenAI è pensato per server locali; un endpoint pubblico
richiede `ai.openai.allow_remote=true` esplicito. La chiave API è opzionale per i
server locali. `amy doctor` espone una voce «Costi IA».

**Conseguenze:** nessuna funzione fondamentale richiede account, carta o cloud. Un
endpoint remoto resta possibile solo come scelta consapevole dell'utente, che deve
verificarne le condizioni economiche. Il vincolo è permanente e vale per tutte le
fasi future: conversazione, modelli, voce, wake word, controllo del Mac, interfaccia
e robot. Se non esiste un'alternativa gratuita adeguata, lo sviluppo si ferma e si
chiede indicazione all'utente. I test `tests/test_free_only.py` controllano che non
vengano introdotte dipendenze obbligatorie o host commerciali. Le licenze e l'audit
sono documentati in [GRATUITO.md](GRATUITO.md).

## D-019 — Interfaccia «Amy Core» nel browser, senza framework

**Contesto:** la dashboard esistente è servita dal cervello Python con la sola
libreria standard. Serve un'identità visiva stabile, una chat realmente usabile e un
pannello informativo onesto, senza introdurre un secondo programma né dipendenze
frontend.

**Scelta:** la dashboard resta un'applicazione web locale servita da `amy serve`.
L'identità «Amy Core» è costruita con SVG, CSS e JavaScript originali, senza
framework, font remoti, icone o CDN. Lo schermo intero usa il Fullscreen API del
browser, non un'app separata. Gli otto stati del nucleo derivano solo da segnali
reali del backend: richiesta in corso, attività `in_corso`, conferma pendente,
`voice.speaking`, errore restituito, latch E-stop, disponibilità del provider.

**Conseguenze:** nessuna nuova dipendenza e nessun costo. La UI resta separata dal
database e dalle chiavi: parla solo con le API locali. La CSP vieta stili inline e
risorse esterne, quindi il codice usa classi e `textContent`. I dati assenti sono
mostrati come «Non disponibile» o «Non configurato», mai inventati. Il pulsante
E-stop è etichettato come software e non sostituisce quello fisico. Dettagli in
[INTERFACCIA.md](INTERFACCIA.md).

## D-020 — Applicazione macOS nativa per Amy Core

**Contesto:** la dashboard servita da `amy serve` funziona, ma obbliga a usare un
browser. Per un assistente personale serve un programma vero: finestra propria,
icona nel Dock, menu, schermo intero e avvio con doppio clic.

**Scelta:** l'interfaccia diventa un bundle macOS nativo scritto in Swift
(`apps/AmyCore`), con `WKWebView` per mostrare la stessa dashboard e il backend
Python avviato come processo figlio. Solo framework di sistema (AppKit, WebKit,
Foundation, Darwin) e solo `Xcode Command Line Tools`: nessuna dipendenza
frontend, nessun framework, nessun account, nessun costo. L'icona è generata
localmente con CoreGraphics. La firma è ad-hoc, senza certificato a pagamento.

Il backend resta identico e resta legato a `127.0.0.1`. L'app scrive un heartbeat
ogni 2 secondi: se l'app muove (anche con SIGKILL), il backend si chiude da solo
entro pochi secondi, così non restano processi orfano. La console web
(`python3 -m amy serve`) resta disponibile come canale alternativo e di debug.

**Conseguenze:** un solo front-end da mantenere (HTML/CSS/JS) con due ospiti
(schermo intero nativo e browser). L'app richiede macOS 12 o superiore e le
Command Line Tools, entrambe gratuite. Il self-test (`apps/AmyCore/selftest.py`)
verifica end-to-end che la WebView monti la pagina, che un messaggio inviato dal DOM
produca una risposta in chat e che il backend venga chiuso. Dettagli in
[INTERFACCIA.md](INTERFACCIA.md).

## D-021 — Provider IA online gratuito, con consenso esplicito

**Contesto:** su questo Mac il modello locale via Ollama è troppo lento per un uso
quotidiano. Serve una risposta rapida senza violare il vincolo permanente di
gratuità: il servizio deve funzionare senza carta di credito, senza crediti
obbligatori e senza piani premium necessari.

**Scelta:** `amy/ai/presets.py` contiene un elenco chiuso di servizi online
verificati, con endpoint, modello, licenza, quote, privacy e data di verifica. Il
primo è GroqCloud piano Free, modello `openai/gpt-oss-120b` (Apache-2.0). Un preset:

- resta spento nel repository: `ai.provider` predefinito è `ollama` e
  `ai.online.consent` è `false`;
- si attiva solo con `ai.provider` uguale al preset **e** `ai.online.consent = true`,
  cioè una conferma esplicita che i messaggi lasciano il computer;
- non può mai essere il fallback: il fallback resta `offline` (o `ollama`);
- legge la chiave solo da variabile d'ambiente o `~/.amy/secrets.json` (`0600`),
  scritta con `python3 -m amy secret set` senza mostrarla;
- non introduce nuove dipendenze: riusa l'adattatore compatibile OpenAI già
  presente, quindi solo libreria standard.

**Conseguenze:** la conversazione può essere più rapida senza costi, ma smette di
essere locale: privacy e disponibilità dipendono dal servizio, che va riverificato
prima di aggiornare i preset. Se il servizio cambia condizioni o quote, il preset va
corretto o rimosso; se non esiste un'alternativa gratuita adeguata, ci si ferma e lo
si chiede all'utente. Senza chiave o con il servizio irraggiungibile Amy usa il
fallback locale e lo dichiara nella UI e in `amy doctor`. Dettagli e fonti in
[GRATUITO.md](GRATUITO.md); configurazione in
[CONFIGURAZIONE.md](CONFIGURAZIONE.md#provider-online-gratuito-groq).

## D-022 — Interfaccia a palco: nucleo, satellite, pannelli sovrapposti

**Contesto:** l'utente ha chiesto un'interfaccia ispirata a J.A.R.V.I.S. e ha
indicato come riferimento il minuto 5:28 del video
<https://www.youtube.com/watch?v=8CQ1rfwS_RE>: nucleo luminoso al centro, chat su un
lato, pannelli informativi sovrapposti, sfondo scuro a campo stellato.

**Scelta:** la dashboard usa un unico palco (`.stage`):

- il nucleo è un pannello a piena area (`.core-panel`), senza card contenitiva;
- la chat è un satellite a destra, alto quasi quanto il palco, sopra il nucleo;
- i pannelli informativi sono schede sovrapposte a sinistra, con sollevamento su
  hover/focus e chiusura sfumata in basso;
- la barra comandi è staccata dalla chat e centrata in fondo al palco, come nel
  riferimento, con gli stessi identificativi del vecchio compositore;
- lo sfondo è un campo stellato statico in SVG inline, senza immagini esterne;
- sotto 1040 px il palco non regge tre strati e diventa un flusso verticale con chat,
  barra comandi, nucleo e pannelli in quest'ordine; a 960×600 resta utilizzabile.

Il riferimento è stato ricavato dai fotogrammi pubblici del video, non da risorse
protette: nessun asset, font o codice del video è stato copiato.

**Conseguenze:** l'aspetto è più vicino al riferimento senza rinunciare a
accessibilità, CSP e leggibilità. Il compositore è unico e vive nella barra, quindi
il punto di invio resta uno solo; la chat conserva la cronologia e il pulsante
«Nuova», mentre il nucleo riserva spazio in fondo per non finire sotto la barra. Gli
identificativi non cambiano, così il codice della UI non è stato riscritto. La
verifica è visiva tramite snapshot; interazioni manuali (ridimensionamento,
fullscreen, focus) restano da provare a mano.

