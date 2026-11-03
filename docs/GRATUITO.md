# Solo strumenti gratuiti

Questo documento è vincolante. Amy deve poter essere sviluppata, installata e usata
senza pagamenti obbligatori, presenti o futuri. La comodità non giustifica una
dipendenza a pagamento.

## 1. Regola

Amy può usare solo:

1. software open source gratuito;
2. modelli IA eseguibili localmente;
3. librerie gratuite senza abbonamento;
4. servizi online realmente gratuiti e senza pagamento obbligatorio;
5. strumenti già presenti nell'ambiente dell'utente.

Non sono ammessi come requisiti:

- abbonamenti;
- API con fatturazione obbligatoria;
- crediti acquistabili;
- piani premium necessari;
- licenze commerciali a pagamento;
- funzionalità bloccate dietro un pagamento.

Un piano gratuito con limiti, una prova temporanea o crediti promozionali **non**
sono sufficienti per rendere un servizio una dipendenza del progetto.

### 1.1 Ambito permanente

Il vincolo è **globale e permanente**. Non vale solo per il nucleo attuale, ma per
ogni fase futura:

- nucleo conversazionale e orchestrazione;
- modelli IA, con Ollama e l'esecuzione locale come default;
- voce: sintesi, riconoscimento e wake word;
- controllo del Mac e automazioni;
- CLI, dashboard e futura interfaccia grafica;
- robot Raspberry Pi, protocollo e link di comunicazione;
- test, sviluppo, packaging e distribuzione.

Ogni nuova funzionalità deve rispettare questo documento. Se una scelta comporta
costi obbligatori, va sostituita con un'alternativa gratuita oppure esclusa. Se non
esiste un'alternativa adeguata, il lavoro si ferma e si chiede indicazione all'utente:
non si integra un servizio a pagamento nemmeno come opzione temporanea o fallback.

## 2. Stato del progetto

Amy è progettata per funzionare interamente in locale:

| Funzione | Soluzione predefinita | Costo previsto |
| --- | --- | --- |
| Conversazione | Ollama su `127.0.0.1` | nessuno, solo hardware ed elettricità |
| Fallback conversazione | interprete offline deterministico | nessuno |
| Sintesi vocale | comando `say` di macOS | nessuno aggiuntivo |
| Riconoscimento vocale | `faster-whisper` locale (CPU) | nessuno; il modello si scarica una volta da Hugging Face |
| Registrazione dal microfono | `sounddevice` (in-process) | nessuno |
| Wake word | confronto testuale sulla trascrizione locale | nessuno |
| Memoria | SQLite locale | nessuno |
| Controllo Mac | strumenti Python e AppleScript locali | nessuno |
| Robot | simulatore o MQTT locale | nessuno |
| Dashboard | server HTTP locale | nessuno |
| Web | browser dell'utente e HTTP diretto | dipende dalla connessione dell'utente |

Nessuna funzione fondamentale richiede un account, una carta di pagamento o un
servizio cloud.

### 2.1 Verifica delle dipendenze attuali

Audit eseguito il **30 ottobre 2026** sul repository:

| Elemento | Stato | Valutazione |
| --- | --- | --- |
| `pyproject.toml` | `dependencies = []` | nessuna dipendenza Python obbligatoria |
| Import del pacchetto `amy` | solo libreria standard e moduli interni | nessun pacchetto commerciale |
| `requirements-optional.txt` | solo `paho-mqtt` | opzionale, licenza EPL-2.0/EDL-1.0 |
| Componenti vocali installati a mano | `faster-whisper`, `sounddevice` e dipendenze | opzionali, licenze MIT/BSD/Apache-2.0; nessuna richiesta di account, carta o crediti |
| Provider IA predefinito | Ollama su `127.0.0.1` | locale, nessun costo |
| Provider IA online (facoltativo) | preset `groq` verificato, spento per default | piano Free senza carta di credito; si attiva solo con consenso esplicito |
| Fallback IA predefinito | `offline` | deterministico, nessun costo |
| Endpoint OpenAI-compatible | `http://127.0.0.1:8000/v1` | locale; remoto bloccato senza consenso |
| TTS | comando `say` di macOS | già presente, nessun costo aggiuntivo |
| STT e registratore | adapter locali opzionali (`faster-whisper`, `sounddevice`) | installati e verificati localmente; nessun servizio cloud |
| Wake word | confronto testuale su trascrizione locale | nessun servizio cloud |
| Dashboard «Amy Core» | file statici locali, SVG/CSS originali, nessuna libreria frontend, nessun CDN | nessuna risorsa esterna né dipendenza a pagamento |
| Applicazione «Amy Core.app» | Swift + framework di sistema macOS (AppKit, WebKit, Foundation, Darwin), `Xcode Command Line Tools` | nessuna dipendenza di terze parti, nessun account sviluppatore, firma ad-hoc |
| Web | browser dell'utente e HTTP diretto | nessuna API key o account |
| Robot | simulatore predefinito, MQTT locale opzionale | nessun servizio cloud |
| Test | `unittest` della libreria standard | nessun servizio esterno |

I test `tests/test_free_only.py` verificano che non vengano introdotte dipendenze
obbligatorie, host IA commerciali cablati o campi di fatturazione nella
configurazione predefinita. `tests/test_online_presets.py` verifica che ogni preset
online sia gratuito senza carta, spento per default e attivabile solo con consenso
esplicito.

## 3. Licenze verificate

Verifica effettuata il **30 ottobre 2026** sulle fonti ufficiali dei progetti;
componenti vocali verificati il **31 ottobre 2026** sui metadati dei pacchetti
installati.

| Componente | Licenza | Note |
| --- | --- | --- |
| Python 3.9+ | PSF License 2.0 | open source, nessun costo |
| SQLite | public domain | incluso in Python |
| Ollama | MIT | server locale, open source |
| `qwen2.5-coder:14b` | Apache-2.0 | verificare la model card della versione usata |
| `say` di macOS | componente di macOS | nessun costo aggiuntivo; macOS non è open source |
| faster-whisper | MIT | opzionale; verificato installato (1.2.1) il 31 ottobre 2026 |
| ctranslate2 (usato da faster-whisper) | MIT | opzionale; verificato installato (4.8.4) il 31 ottobre 2026 |
| sounddevice (PortAudio bindings) | MIT | opzionale; verificato installato (0.5.6) il 31 ottobre 2026 |
| NumPy (usato da faster-whisper) | BSD-3-Clause | opzionale; verificato installato (2.0.2) il 31 ottobre 2026 |
| huggingface-hub (download del modello) | Apache-2.0 | opzionale; verificato installato (1.8.0) il 31 ottobre 2026 |
| tokenizers (usato da faster-whisper) | Apache-2.0 | opzionale; verificato installato (0.22.2) il 31 ottobre 2026 |
| onnxruntime | MIT | opzionale; verificato installato (1.19.2) il 31 ottobre 2026 |
| OpenAI Whisper (codice e modelli) | MIT | opzionale |
| whisper.cpp | MIT | opzionale |
| FFmpeg | LGPL-2.1+ o GPL-2.0+ secondo la build | opzionale; la licenza dipende dai codec abilitati |
| SoX | GPL-2.0-or-later; libsox LGPL-2.1-or-later | opzionale |
| paho-mqtt | EPL-2.0 / EDL-1.0 | opzionale per MQTT |
| GroqCloud (piano Free) | condizioni d'uso del servizio, uso gratuito entro quote | opzionale; nessun metodo di pagamento richiesto per il piano Free |
| `openai/gpt-oss-120b` (modello ospitato da Groq) | Apache-2.0 | pesi aperti; verificare la model card della versione usata |
| AppKit, WebKit, Foundation, Darwin | componenti di macOS (SDK Apple) | di sistema, già presenti; nessun costo |
| Swift compiler (`swiftc`) | parte di Xcode Command Line Tools | gratuito, già presente; nessun account richiesto per l'uso locale |
| Icona dell'app | originale, generata con CoreGraphics | nessun file di terze parti |
| Firma del bundle | ad-hoc (`codesign -s -`) | nessun certificato a pagamento, nessun account sviluppatore |
| DuckDuckGo | nessuna API usata | Amy apre solo il browser dell'utente |

Fonti consultate:

- <https://github.com/ollama/ollama/blob/main/LICENSE>
- <https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct>
- <https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE>
- <https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE>
- <https://github.com/alsrd/sounddevice/blob/master/LICENSE>
- <https://github.com/numpy/numpy/blob/main/LICENSE.txt>
- <https://github.com/huggingface/huggingface_hub/blob/main/LICENSE>
- <https://github.com/huggingface/tokenizers/blob/main/LICENSE>
- <https://github.com/microsoft/onnxruntime/blob/main/LICENSE>
- <https://github.com/openai/whisper/blob/main/LICENSE>
- <https://github.com/ggerganov/whisper.cpp/blob/master/LICENSE>
- <https://ffmpeg.org/legal.html>
- <https://sourceforge.net/projects/sox/>
- <https://github.com/eclipse-paho/paho.mqtt.python/blob/master/LICENSE.txt>
- <https://console.groq.com/docs/rate-limits>
- <https://console.groq.com/docs/billing-faqs>
- <https://console.groq.com/docs/your-data>
- <https://huggingface.co/openai/gpt-oss-120b>

Le licenze possono cambiare nelle versioni future. Prima di aggiornare un componente
importante, ricontrollare la licenza della versione scelta. I modelli IA hanno
licenze proprie, separate da quelle del runtime: non basta che Ollama sia MIT.

## 4. Servizi online

Amy **non richiede** servizi online: il default è locale e funziona senza rete. Un
modello online gratuito può però essere scelto esplicitamente quando il computer è
lento a eseguire un modello locale. In quel caso la conversazione lascia il Mac e
Amy lo dichiara nella dashboard.

Le funzioni che possono usare Internet sono:

- `web.open`: apre un URL nel browser dell'utente;
- `web.search`: apre una ricerca DuckDuckGo nel browser;
- `web.fetch`: legge una pagina pubblica via HTTP;
- il provider IA online, solo se scelto esplicitamente con un preset verificato.

`web.*` non richiede chiavi API né account. Il costo è quello della connessione
dell'utente, se presente. Se la rete non c'è, queste funzioni falliscono e il resto
continua a funzionare.

### Provider IA online gratuiti (facoltativi)

`ai.provider` accetta i preset elencati da `python3 -m amy providers`. Oggi è
disponibile un preset: `groq`.

| Voce | Valore |
| --- | --- |
| Servizio | GroqCloud, piano **Free** |
| Endpoint | `https://api.groq.com/openai/v1` (compatibile OpenAI) |
| Modello predefinito | `openai/gpt-oss-120b` (Apache-2.0) |
| Alternativa | `openai/gpt-oss-20b` (più veloce, meno preciso) |
| Chiave | `GROQ_API_KEY`, da <https://console.groq.com/keys> |
| Registrazione | nessuna carta di credito richiesta |
| Limiti Free, `gpt-oss-120b` | 30 richieste/min, 1.000/giorno, 8.000 token/min, 200.000 token/giorno |
| Costo per Amy | 0: il piano Developer a consumo è facoltativo e non serve |
| Privacy | dati non conservati per default; fino a 30 giorni per affidabilità e abuso; conservazione zero attivabile; elaborazione negli USA |
| Fallback | `offline`, locale e deterministico |

Limiti verificati il **31 ottobre 2026** sulle fonti ufficiali indicate sotto. Se il
servizio cambia condizioni, il preset va riverificato o rimosso.

Il tetto di **8.000 token al minuto** è il vincolo pratico più stretto. Il catalogo
degli strumenti viene inviato in forma testuale compatta (nome, argomenti e
descrizione): il prompt di sistema scende da circa 3.100 a circa 1.700 token, così
Amy gestisce più messaggi ravvicinati restando nel piano gratuito. Un `429` viene
ritentato fino a due volte usando l'attesa indicata dal servizio nel corpo della
risposta (`try again in Xs`) o nell'header `Retry-After`, con un tetto di 20 secondi.
Una risposta vuota viene ritentata una volta. Se il limite resta superato, Amy
risponde con il fallback locale e lo dichiara; la quota si libera da sola nel giro di
un minuto.

Regole applicate dal codice:

- il preset è **spento per impostazione predefinita**;
- si attiva solo con `ai.provider` uguale al preset **e** `ai.online.consent = true`,
  cioè una conferma esplicita che i messaggi lasciano il computer;
- la chiave non sta mai nella configurazione: solo `~/.amy/secrets.json` con permessi
  `0600` oppure variabile d'ambiente;
- senza chiave il provider risulta **non disponibile**, non "disponibile ma lento";
- il fallback non può essere un preset online: resta `offline` o `ollama`;
- `amy doctor` verifica chiave e modello con una richiesta leggera a `/models` e
  mostra limiti e condizioni del piano;
- se il piano gratuito finisce o il servizio non risponde, Amy usa il fallback
  locale: non esiste alcun percorso che possa generare un addebito.

Fonti consultate:

- <https://console.groq.com/docs/rate-limits>
- <https://console.groq.com/docs/billing-faqs>
- <https://console.groq.com/docs/your-data>
- <https://huggingface.co/openai/gpt-oss-120b>

### Endpoint compatibile OpenAI

Il provider `openai` è un adattatore generico, non un obbligo e non il default. Serve
per collegare un server **locale** compatibile OpenAI, per esempio llama.cpp,
LM Studio, vLLM o un endpoint sulla propria rete.

Regole applicate dal codice:

- l'endpoint predefinito è `http://127.0.0.1:8000/v1`;
- un endpoint pubblico è rifiutato dalla configurazione;
- per usarlo serve `ai.openai.allow_remote = true`, con consapevolezza esplicita;
- la chiave API è opzionale per i server locali;
- il fallback predefinito è `offline`, mai un servizio a pagamento;
- `amy doctor` mostra una voce «Costi IA».

Se un endpoint remoto è gratuito solo entro limiti, è responsabilità dell'utente
verificare condizioni, carta richiesta, quote e cosa succede quando finiscono. Amy
non presume che un servizio sia gratuito perché ha un piano gratuito.

## 5. Costi nascosti

Amy non introduce costi nascosti, ma l'ambiente può averne:

| Voce | Nota |
| --- | --- |
| Hardware | Mac e robot sono necessari per l'uso previsto |
| Elettricità | Ollama e Whisper consumano CPU/GPU |
| Connessione Internet | solo per web e aggiornamenti |
| macOS | sistema non open source, ma già presente |
| Modelli IA | gratuiti solo se la licenza della versione scelta lo consente |
| Servizi remoti | esclusi dal default; possibili solo con opt-in |

Amy non vende, non telemetrizza e non richiede account.

## 6. Dipendenze che potrebbero diventare a pagamento

- Un endpoint OpenAI-compatible pubblico potrebbe introdurre limiti o prezzi. Per
  questo non è il default ed è bloccato senza consenso.
- Una nuova versione di un modello potrebbe cambiare licenza. Il progetto non
  aggiorna automaticamente i modelli.
- Un pacchetto opzionale potrebbe cambiare licenza. Le dipendenze obbligatorie sono
  comunque zero.

## 7. Alternative gratuite

| Se manca… | Alternativa |
| --- | --- |
| Ollama | interprete offline; altro server locale compatibile OpenAI |
| `say` | altro TTS locale open source, se installato |
| whisper.cpp | faster-whisper o Whisper CLI |
| FFmpeg | SoX |
| paho-mqtt | trasporto simulato; MQTT resta opzionale |
| Dashboard | CLI |

## 8. Checklist per nuove integrazioni

Prima di aggiungere un componente:

1. La licenza consente l'uso previsto senza pagamento?
2. Funziona offline o solo online?
3. Richiede un account, una carta o crediti?
4. Cosa succede quando il piano gratuito finisce?
5. Esiste un'alternativa locale o open source?
6. La dipendenza è obbligatoria o opzionale?
7. È documentata con licenza, limiti e condizioni?
8. I test funzionano senza il servizio esterno?

Se una risposta è incerta, il componente non diventa una dipendenza obbligatoria.
Se una scelta comporta costi obbligatori, va sostituita o esclusa.

Se non esiste un'alternativa gratuita concretamente utilizzabile, **non procedere**:
descrivi il limite, le alternative valutate e chiedi all'utente come preferisce
procedere. La gratuità non è un'ottimizzazione facoltativa: è un requisito di
accettazione.
