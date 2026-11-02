# Amy Brain

Amy è un assistente personale locale per macOS, con un cervello software che può
estendere il proprio controllo a un robot basato su Raspberry Pi. Questo repository
contiene il **livello L2**: l'assistente, la memoria, la policy di sicurezza, gli
strumenti macOS e il collegamento al robot. Il firmware e i documenti canonici
dell'hardware restano nel repository gemello `../amy/`.

Stato attuale, senza ottimismo: il nucleo testuale, gli strumenti macOS, la memoria,
l'applicazione macOS «Amy Core», la dashboard locale e il simulatore robotico
funzionano e sono coperti da test. Il collegamento MQTT è **sperimentale e non
verificato** su hardware reale. Il movimento fisico del robot **non è stato
verificato**. Il riconoscimento vocale non è operativo su questa macchina perché
mancano registratore audio (`ffmpeg`/`sox`) e motore STT.

## Solo strumenti gratuiti

Amy è vincolata a strumenti, librerie, modelli e servizi **gratuiti**, senza
pagamenti obbligatori. Il vincolo è **globale e permanente**: vale per il nucleo
conversazionale, i modelli IA, la voce, la wake word, il controllo del Mac,
l'interfaccia e il robot Raspberry Pi. Il default è interamente locale:

- Ollama su `127.0.0.1` per la conversazione;
- interprete offline come fallback;
- `say` di macOS per la sintesi;
- `faster-whisper` e `sounddevice` per la trascrizione e il microfono, entrambi
  locali e gratuiti;
- SQLite per la memoria;
- simulatore robotico locale.

Nessuna funzione fondamentale richiede account, carta di pagamento o cloud. Se il
modello locale è troppo lento si può scegliere un **provider online gratuito**
verificato: oggi GroqCloud piano Free, senza carta di credito. Non è il default, è
spento nel repository, richiede `ai.online.consent = true` e la conversazione lascia
il Mac. Il fallback non può mai essere online. Licenze, limiti e alternative sono in
[docs/GRATUITO.md](docs/GRATUITO.md).

## Avvio rapido

Requisiti: macOS, Python 3.9 o superiore. Il nucleo usa solo la libreria standard.

### Applicazione macOS (interfaccia principale)

Amy è un'applicazione nativa macOS: finestra propria, icona nel Dock, menu e
schermo intero. Si compila una volta e poi si avvia con doppio clic.

```bash
# Compila l'app (usa solo tool di sistema: swiftc, iconutil, codesign)
./apps/AmyCore/build.sh

# Prova subito
open "apps/AmyCore/dist/Amy Core.app"

# Installa per l'utente (nessun admin, nessun account)
mkdir -p ~/Applications && cp -R "apps/AmyCore/dist/Amy Core.app" ~/Applications/
```

L'app avvia in background il backend Python locale, mostra la dashboard nella
finestra e chiude tutto quando esci. Se il repository viene spostato, l'app lo
chiede una volta e lo ricorda in `~/.amy/app.json`.

### CLI e console web

```bash
# 1. Configurazione iniziale in ~/.amy/config.json
python3 -m amy init

# 2. Verifica ambiente, voce, IA e robot
python3 -m amy doctor

# 3. Prova senza modello IA (interprete locale di comandi italiani)
python3 -m amy ask "che ore sono?" --offline

# 4. Conversazione interattiva
python3 -m amy chat

# 5. Stessa dashboard dell'app, aperta nel browser
python3 -m amy serve --open-browser

# 6. Saluto vocale di prova (sintesi locale, non registra)
python3 -m amy voice greet
```

Con Ollama attivo e un modello installato, Amy usa il modello configurato:

```bash
ollama serve
ollama pull qwen2.5-coder:14b
python3 -m amy ask "elenca i file in ~/Progetti"
```

Se il modello locale è troppo lento, si può passare a un provider online gratuito
verificato (nessuna carta di credito, quote dichiarate). La chiave non va mai
scritta in chat o nel repository: si salva con il comando dedicato, che non la mostra.

```bash
python3 -m amy providers              # preset, limiti, licenza, privacy
python3 -m amy secret set GROQ_API_KEY
# poi nella configurazione: ai.provider="groq", ai.online.consent=true
python3 -m amy doctor                 # verifica chiave e modello
```

Dettagli e condizioni: [docs/CONFIGURAZIONE.md](docs/CONFIGURAZIONE.md#provider-online-gratuito-groq).

La dashboard ascolta su `127.0.0.1:8765` per impostazione predefinita. Non ha
autenticazione: l'esposizione su altre interfacce è bloccata salvo consenso esplicito
(`ui.allow_remote`), e resta sconsigliata.

## Cosa sa fare oggi

- Conversazione in italiano con provider astratti: Ollama locale, preset online
  gratuito verificato (GroqCloud Free, spento per default), endpoint compatibile
  OpenAI **locale**, oppure interprete offline deterministico.
- 35 strumenti reali: sistema (inclusa la batteria del Mac), applicazioni macOS,
  file confinati, shell in allowlist, web con protezione SSRF, memoria, voce e
  robot.
- Policy A/B/C con conferma esplicita; il livello C non è mai automatico.
- E-stop e arresto robot mai bloccati da conferma o dal modello.
- Memoria SQLite locale con fatti, sessioni, attività ed eventi robotici.
- Audit append-only con redazione dei segreti.
- Applicazione macOS nativa «Amy Core» (Swift + AppKit + WebKit): finestra
  propria, icona nel Dock, menu, schermo intero, avvio e chiusura del backend
  locale senza processi orfani.
- Dashboard locale «Amy Core» con nucleo a otto stati, chat reale, cronologia,
  conferme, stato del motore IA, informazioni di sistema locali, voce, robot,
  attività, memoria, strumenti ed E-stop software.
- Informazioni di sistema reali raccolte con la libreria standard: macOS,
  architettura, Python, CPU, carico e disco. Nessuna telemetria.
- Interfaccia accessibile da tastiera, con focus visibile, movimento ridotto,
  schermo intero e layout responsivo; nessuna risorsa esterna e nessun CDN.
- Simulatore robotico del protocollo v1 con limiti, ACK/NACK, deduplicazione,
  watchdog e modalità TEST senza movimento fisico.
- Voce completa e locale: microfono con `sounddevice`, trascrizione con
  `faster-whisper`, sintesi con `say` e wake word «Amy». All'avvio Amy dice
  «Amy è attiva e operativa»; l'ascolto continuo si avvia automaticamente
  all'avvio (disattivabile) e si ferma da solo dopo 20 minuti.
- Protezione dall'eco **half-duplex** nel ciclo vocale: mentre Amy parla il
  microfono resta chiuso e i frammenti che contengono la sua voce vengono
  scartati, così la sua risposta non viene scambiata per un comando.

## Cosa non è verificato o non è disponibile

| Area | Stato |
| --- | --- |
| Movimento fisico del robot | Non verificato: nessun hardware collegato in questo ambiente |
| Collegamento MQTT reale | Sperimentale: implementato, ma senza broker/robot verificato |
| Riconoscimento vocale | Verificato il 31 ottobre 2026: `faster-whisper` 1.2.1 con modello `base` locale, `sounddevice` 0.5.6 sul microfono. Verificata anche la trascrizione di parlato reale |
| Provider online gratuito | Verificato il 31 ottobre 2026: chiave in `~/.amy/secrets.json` (`600`), risposta reale del modello GroqCloud Free. Il modello locale resterebbe il default del repository |
| Wake word audio | Non è un motore audio dedicato: rileva la parola dopo la trascrizione. Consumi CPU e falsi positivi restano possibili |
| Qualità vocale su più parlanti | Verificato solo con una voce di prova | Trascrizioni con voci diverse, rumore e accenti |
| Dashboard remota | Volutamente bloccata di default; nessuna autenticazione |
| Uso continuativo / produzione | Non dichiarato stabile |

## Sicurezza in una frase

Il modello propone un'azione JSON; il codice valida schema, rischio, percorsi e
policy prima di eseguire. Le azioni di livello C richiedono una conferma esplicita
dell'utente. L'E-stop software e l'arresto hanno priorità assoluta, ma **l'unico
arresto garantito resta l'E-stop fisico**.

Dettagli: [docs/SICUREZZA.md](docs/SICUREZZA.md) e
[docs/ROBOTICA.md](docs/ROBOTICA.md).

## Struttura

```text
amy/
  ai/         provider Ollama, preset online gratuiti, OpenAI-compatible, offline, fallback
  core/       configurazione, orchestrazione, prompt, errori, logging
  memory/     SQLite: sessioni, messaggi, fatti, attività, eventi
  security/   livelli di rischio, policy, path guard, audit
  tools/      strumenti macOS, file, shell, web, memoria, voce, robot
  voice/      TTS macOS, STT locale, registratore, wake word testuale
  robot/      protocollo v1, simulatore, link simulato e MQTT
  ui/         server HTTP locale e dashboard statica
  macos/      integrazione AppleScript e informazioni di sistema
apps/AmyCore/ applicazione macOS nativa (Swift) e self-test
tests/        suite unittest (257 test)
docs/         documentazione italiana del progetto
```

## Test

```bash
python3 -m compileall -q amy tests
python3 -m unittest discover -s tests -t . -v

# Self-test dell'app nativa: avvia l'app, invia un messaggio, verifica la risposta
./apps/AmyCore/build.sh && python3 apps/AmyCore/selftest.py
```

Risultato verificato il 2 novembre 2026: **257 test, tutti superati**, più il
self-test dell'app nativa (messaggio inviato dal DOM, risposta in chat, backend
chiuso correttamente). I test non dimostrano il funzionamento su hardware robotico
reale; la voce è stata verificata a mano sul microfono del Mac, non dalla suite; il
provider online richiede una chiave personale e non viene esercitato dalla suite con
traffico reale. Vedi [docs/TEST.md](docs/TEST.md).

## Documentazione

- [Architettura](docs/ARCHITETTURA.md)
- [Stato del progetto](docs/STATO_PROGETTO.md)
- [Roadmap](docs/ROADMAP.md)
- [Decisioni tecniche](docs/DECISIONI.md)
- [Sicurezza](docs/SICUREZZA.md)
- [Solo strumenti gratuiti](docs/GRATUITO.md)
- [Interfaccia Amy Core](docs/INTERFACCIA.md)
- [Voce](docs/VOCE.md)
- [Controllo del Mac](docs/CONTROLLO_MAC.md)
- [Robotica](docs/ROBOTICA.md)
- [Configurazione](docs/CONFIGURAZIONE.md)
- [Test](docs/TEST.md)
- [Changelog](docs/CHANGELOG.md)

Documenti canonici del robot (protocollo, sicurezza hardware, firmware):
`../amy/docs/`. In particolare
[`06_protocollo_mqtt.md`](../amy/docs/06_protocollo_mqtt.md) e
[`07_sicurezza.md`](../amy/docs/07_sicurezza.md).

## Licenza

MIT, come dichiarato in `pyproject.toml`.
