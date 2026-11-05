# Voce

Amy separa quattro funzioni che spesso vengono confuse: **sintesi vocale (TTS)**,
**riconoscimento vocale (STT)**, **registrazione dal microfono** e **wake word**.
Su questa macchina sono ora tutte operative e verificate, con una precisazione:
la wake word lavora sul testo trascritto, non su un rilevatore acustico dedicato.

## 1. Stato reale

| Funzione | Stato | Dettaglio |
| --- | --- | --- |
| TTS macOS | **Verificato** | Comando `say`, voce italiana `Alice`, sintesi su file riuscita |
| Interruzione TTS | **Verificato** | `voice.stop` termina il processo `say`; usato anche come barge-in |
| STT | **Verificato** | `faster-whisper` 1.2.1, modello `small` multilingua, CPU, int8, prompt comandi italiano |
| Registratore | **Verificato** | `sounddevice` 0.5.6 su Core Audio, WAV 16 kHz mono |
| Wake word | **Verificata** | «Amy, che ore sono?» → comando eseguito e risposta pronunciata |
| Ciclo continuo | **Verificato** | Avviato dalla dashboard o all'avvio, fermato dal pulsante; limite configurabile (0 = nessuno) |
| Saluto di avvio | **Verificato** | «Amy è attiva e operativa.» pronunciato all'avvio della dashboard |
| Protezione dall'eco | **Verificata** | Half-duplex: niente registrazione durante la sintesi, frammento contaminato scartato dal vivo il 2 novembre 2026 |

Prove eseguite il 31 ottobre 2026:

- trascrizione di un file sintetico: «Amy, che ore sono adesso» → «Emi, che ora sono adesso»;
- registrazione reale dal microfono con il parlato riprodotto dagli altoparlanti:
  «Amy, che ore sono?» → «Emi, che ore sono?» in circa 7 secondi (6 di ascolto);
- ciclo completo: wake word rilevata, comando `che ore sono` eseguito,
  risposta «Sono le 17:21 del 31/10/2026.» pronunciata e scritta in chat;
- avvio della dashboard: saluto «Amy è attiva e operativa.» pronunciato circa
  4 secondi dopo l'avvio del backend, senza alcuna registrazione.

Prove ripetute il 1 novembre 2026 con l'app nativa ricompilata:

- `/api/voice/listen` con «Amy, che ore sono?» dagli altoparlanti → «Emi che ore
  sono.» in 8,4 secondi;
- ciclo completo dalla dashboard: `Wake word rilevata`, comando `che ore sono`,
  risposta «Sono le 09:09 del 01/11/2026.» scritta in chat e pronunciata;
- ripetizione sulla build finale: rilevazione 2 secondi dopo la frase, risposta
  «Sono le 09:18 del 01/11/2026.» in chat, processo `say` attivo e
  `voice.speaking = true` osservati dal vivo;
- dopo «Ferma ascolto» lo stato `running` è falso entro un secondo e il backend
  resta vivo (heartbeat 0–2 s, `/api/health` `ok`).

Prove ripetute il 2 novembre 2026 (protezione dall'eco):

- ciclo `python3 -m amy voice loop --execute --offline` con tre comandi «Amy, che
  ore sono?» dagli altoparlanti a distanza di pochi secondi: due rilevati, uno
  **perso perché pronunciato mentre Amy rispondeva** (microfono chiuso). Nessun
  falso wake causato dalla voce di Amy;
- sovrapposizione forzata: con una registrazione da 5 s già in corso, Amy ha
  iniziato a parlare; al termine il log ha riportato
  `Frammento scartato: Amy stava parlando (protezione dall'eco).` e nessun comando
  è stato eseguito. È la prova reale del ramo di scarto, non solo dei test.

Nella stessa giornata l'ingresso audio si è bloccato **dentro il HAL di Core Audio**:
`Pa_OpenStream` non restituiva il controllo su nessun dispositivo e frequenza, né
dall'app né da un processo Python separato. Le registrazioni non sono più appese
all'infinito: dopo `durata + 6 s` la chiamata fallisce con «Il microfono non
risponde», lo stato espone `stuck: true` e i tentativi restano sospesi per 60
secondi. Il blocco è rientrato senza modifiche al codice dopo aver chiuso le
istanze del backend rimaste aperte.

`amy voice status` espone la situazione senza mascherarla:

```json
{
  "enabled": true,
  "tts": {"available": true, "engine": "say", "voice": "Alice", "rate": 185},
  "stt": {"available": true, "engine": "faster-whisper", "model": "small"},
  "recorder": {"available": true, "engine": "sounddevice", "device": "Microfono MacBook Pro", "stuck": false},
  "wake_word": {"phrase": "amy", "enabled": true, "running": false, "available": true, "max_minutes": 0, "echo_guard": true, "echo_guard_cooldown_s": 0.8},
  "startup_greeting": {"enabled": true, "text": "Amy è attiva e operativa."},
  "ready_for_voice_commands": true
}
```

`ready_for_voice_commands` è `true` solo se TTS, STT e registratore sono tutti
disponibili. Non viene forzato per far apparire la funzione completa.

## 2. Sintesi vocale

Motore: `say` di macOS. Non usa rete, non usa servizi cloud, non richiede API key.

Configurazione (`~/.amy/config.json`):

```json
{
  "voice": {
    "enabled": true,
    "tts": {
      "engine": "say",
      "voice": "Alice",
      "rate": 185
    }
  }
}
```

`rate` viene limitato tra 80 e 350 parole al minuto. Il testo viene compattato e
troncato a 4.000 caratteri.

Comandi:

```bash
python3 -m amy voice speak "Ciao, sono Amy."
python3 -m amy voice status
python3 -m amy chat --voice
python3 -m amy ask "che ore sono?" --voice
```

Comportamento:

- `voice.speak` avvia la sintesi e **non attende** la fine: la conversazione resta
  reattiva.
- Una nuova sintesi interrompe la precedente.
- `voice.stop` termina subito il processo `say`.
- Nella dashboard il pulsante «Stop voce» chiama `/api/voice/stop`.
- Il ciclo vocale esegue `tts.stop()` quando rileva la wake word, per il barge-in.
- Nel ciclo continuo la risposta viene sempre pronunciata, anche se l'interruttore
  «Pronuncia le risposte» della dashboard è spento: è una conversazione a voce.

Se la voce configurata non esiste, `say` fallisce e Amy riporta l'errore: non
sostituisce silenziosamente la voce.

### 2.1 Messaggio di avvio

All'avvio della dashboard Amy pronuncia un breve saluto: «Amy è attiva e
operativa.» È un messaggio di **sintesi**: non registra, non avvia l'ascolto e
non richiede il permesso del microfono.

Configurazione:

```json
{
  "voice": {
    "enabled": true,
    "startup_greeting": true,
    "startup_greeting_text": "Amy è attiva e operativa."
  }
}
```

- `startup_greeting: false` disattiva il saluto in modo permanente.
- `AMY_STARTUP_GREETING=0` lo disattiva per una sola sessione (usato dai test
  automatici, che non devono emettere audio).
- Il saluto parte circa un secondo dopo che il backend è pronto, così la
  dashboard è già visibile.
- Se la voce è disabilitata o `say` non è disponibile, Amy **non dice nulla** e
  registra nel log il motivo: non finge di aver parlato.

Ripetere il saluto a comando:

```bash
python3 -m amy voice greet
```

Dalla dashboard: pulsante **«Ripeti saluto»** nel pannello Voce
(`POST /api/voice/greet`).

## 3. Riconoscimento vocale

Amy supporta tre adattatori, scelti da `voice.stt.engine`:

| Valore | Motore | Requisiti |
| --- | --- | --- |
| `auto` (default) | il migliore disponibile | `faster-whisper` se importabile, altrimenti `whisper-cli` |
| `faster-whisper` | Python locale su CPU | pacchetto `faster-whisper`, modello scaricato |
| `whisper` | CLI OpenAI Whisper | comando `whisper` nel PATH |
| `whisper-cli` | whisper.cpp | comando `whisper-cli` e modello GGML locale |

Installazione usata su questo Mac (nessun costo, licenza MIT):

```bash
pip3 install --user faster-whisper
```

Il modello non è incluso nel repository: al primo uso `faster-whisper` lo scarica
in `~/.amy/models/whisper` (circa 145 MB per `base`, 460 MB per `small`). Il download avviene una sola
volta; dopo, la trascrizione funziona anche senza rete.

Configurazione:

```json
{
  "voice": {
    "stt": {
      "engine": "faster-whisper",
      "model": "small",
      "language": "it",
      "download_root": "~/.amy/models/whisper",
      "initial_prompt": "Comandi in italiano per Amy: apri mail, che ore sono, accendi la luce."
    }
  }
}
```

- Il modello viene caricato in background all'avvio del server (`voice.warm()`),
  così il primo comando non aspetta il caricamento.
- Se `whisper-cli` è configurato ma comando o modello mancano, Amy passa a
  `faster-whisper` **solo se è installato**: è un ripiego locale, mai un servizio
  online.
- Se nessun motore è disponibile, `voice listen` restituisce un errore esplicito e
  non inventa una trascrizione.

Prestazioni misurate su questo Intel: circa 1–2 secondi per una frase breve con
`base`, 2–3 secondi con `small`, dopo il primo caricamento in int8.

## 4. Registratore

Due famiglie di motori:

- `sounddevice` (preferito da `auto`): registra in-process con PortAudio, scrive un
  WAV PCM 16 bit mono a 16 kHz con il modulo standard `wave`. Nessun processo
  esterno, nessun file intermedio oltre al WAV temporaneo.
- `ffmpeg` (input `avfoundation`, dispositivo `:0`) o `sox`, se installati.

```json
{
  "voice": {
    "recorder": {
      "engine": "sounddevice",
      "device": "",
      "samplerate": 16000,
      "seconds": 5
    }
  }
}
```

`engine: "auto"` sceglie `sounddevice` se importabile, altrimenti `ffmpeg`.
La durata è limitata tra 1 e 30 secondi.

La prima registrazione richiede il permesso **Microfono**. Nell'app nativa la
richiesta arriva una volta, attribuita ad «Amy Core»: il bundle dichiara
`NSMicrophoneUsageDescription` e il backend è un processo figlio dell'app. Se il
permesso viene negato, la registrazione fallisce con un messaggio esplicito.

Per scegliere un microfono specifico con `sounddevice`, impostare
`voice.recorder.device` con l'indice o il nome del dispositivo (vuoto = predefinito).

### 4.1 Limite di tempo e microfono bloccato

PortAudio può restare bloccato dentro il HAL di Core Audio senza restituire il
controllo. Per questo la cattura gira in un thread separato con un limite:
`durata richiesta + 6 s` (o il valore passato come `timeout` al costruttore).
Oltre il limite:

- la chiamata fallisce con `VoiceError` «Il microfono non risponde: la registrazione è
  stata interrotta» e il dettaglio del limite superato;
- il registratore espone `stuck: true` e il motivo in `problem`;
- i tentativi successivi vengono rifiutati subito, senza aprire altri flussi, per 60
  secondi;
- il ciclo di wake word si ferma con `stop_reason = "microfono non rispondente"` e la
  dashboard lo dichiara (`Non risponde · sounddevice`);
- `POST /api/voice/listen` risponde con errore 400 e `POST /api/voice/wake/start` con
  503, invece di lasciare la richiesta appesa.

`python3 -m amy doctor` apre il microfono per un secondo e cancella subito il file:
la riga «Microfono» distingue un modulo installato da un ingresso che risponde
davvero. Il thread eventualmente ancora fermo nel HAL resta un daemon: non blocca il
backend, ma il rimedio definitivo è riavviare il servizio audio di macOS o il Mac.

## 5. Wake word

`WakeWordDetector` lavora sul **testo trascritto**, non sul segnale audio.
Normalizza il testo (minuscole, accenti rimossi, punteggiatura rimossa) e cerca la
frase configurata come parola intera.

Configurazione:

```json
{
  "voice": {
    "wake_word": {
      "enabled": true,
      "phrase": "amy",
      "sensitivity": 0.5,
      "max_minutes": 0,
      "echo_guard": true,
      "echo_guard_cooldown_s": 0.8
    }
  }
}
```

«Amy» è una parola inventata: lo STT la trascrive quasi sempre in modo diverso.
Per questo il confronto accetta una distanza di edit sul **primo token** o subito
dopo un prefisso di richiamo (`ehi`, `hey`, `ok`, `ciao`):

| Trascrizione | Riconosciuta | Comando estratto |
| --- | --- | --- |
| `Amy, che ore sono?` | sì | `che ore sono` |
| `Emi, che ore sono?` | sì | `che ore sono` |
| `Ami accendi la luce` | sì | `accendi la luce` |
| `ehi Emi che ore sono` | sì | `che ore sono` |
| `non lo faccio mai` | no | — |
| `grazie mille` | no | — |

Regole:

- sensibilità **< 0,5**: solo confronto esatto (nessuna tolleranza);
- sensibilità **≥ 0,5** (default): due errori ammessi per parole fino a 3 caratteri,
  uno per parole fino a 5;
- sensibilità **≥ 0,8**: tolleranza maggiore anche sulle parole più lunghe e
  varianti note (`ami`, `ammy`, `emmi`, `emi`, `emmy`);
- la tolleranza si applica **solo all'inizio della frase**: è ciò che evita di
  attivarsi su parole comuni come «mai» o «mia».

Due modalità d'uso:

- «Amy, che ore sono?» → estrae direttamente il comando;
- «Amy» da sola → ascolta un secondo frammento e lo usa come comando.

Limite dichiarato: **non è un rilevatore acustico dedicato**. Consuma STT su tutto
l'audio ascoltato e può attivarsi su frasi somiglianti all'inizio della frase. Per un
rilevamento a basso consumo servirebbe un filtro acustico (per esempio openWakeWord)
davanti allo STT, non ancora integrato.

### 5.1 Protezione dall'eco (half-duplex)

Amy sente anche i propri altoparlanti: senza protezione, la parola «Amy» dentro
una sua risposta riattiverebbe il ciclo e il microfono registrerebbe la voce di
Amy invece di quella dell'utente. Il 1 novembre 2026 è successo due volte
durante le prove reali.

Il ciclo è quindi **half-duplex**:

- mentre Amy parla, il microfono **non registra**: il ciclo attende che la
  sintesi finisca;
- un frammento registrato mentre la sintesi era in corso viene **scartato** (log
  «Frammento scartato: Amy stava parlando (protezione dall'eco).»);
- dopo la fine della sintesi il ciclo aspetta `voice.wake_word.echo_guard_cooldown_s`
  secondi (default 0,8) prima di riaprire il microfono, così la coda audio della
  sala non entra nel frammento successivo;
- l'attesa è limitata a 20 secondi: se `say` resta appeso, il ciclo non si
  blocca e prosegue dichiarando il motivo nel log.

La sintesi non bloccante viene seguita da un thread di sorveglianza che chiude
l'intervallo di sintesi: `MacSayTTS.speech_overlaps(inizio, fine)` dice se una
registrazione ha sovrapposto la voce di Amy.

Verifica dal vivo del 2 novembre 2026: con una registrazione già in corso, la
sintesi è partita e il frammento è stato scartato con il messaggio di log atteso;
i comandi pronunciati durante una risposta di Amy sono stati persi, come previsto.

Conseguenze dichiarate:

- **mentre Amy parla il microfono è chiuso**: un comando dettato in quel momento
  viene perso e va ripetuto;
- l'interruzione a voce («Amy» mentre Amy parla) non è più possibile: per
  fermarla si usa il pulsante «Stop voce» o `voice.stop`;
- il frammento che contiene la risposta di Amy viene scartato anche se contiene
  un comando: è il prezzo della protezione.

La protezione si può disattivare con `voice.wake_word.echo_guard: false`, ma
tornano i falsi positivi descritti sopra.

## 6. Ciclo vocale continuo

L'ascolto continuo si avvia **automaticamente all'avvio** quando
`voice.wake_word.start_on_launch` è attivo (default). Resta disattivabile con
`voice.wake_word.enabled = false` o `start_on_launch = false`, e si può avviare o
fermare a mano:

```bash
python3 -m amy voice loop
python3 -m amy voice loop --execute
```

- Senza `--execute` trascrive e mostra i comandi, senza eseguirli.
- Con `--execute` passa il testo all'assistente e pronuncia la risposta, ma **non**
  autorizza automaticamente azioni che richiedono conferma.
- `Ctrl-C` termina il ciclo.

Dalla dashboard: pulsante **«Ascolta «Amy»»** nella barra in alto. Chiama
`POST /api/voice/wake/start`; lo stesso pulsante, diventato «Ferma ascolto», chiama
`/api/voice/wake/stop`. Il pulsante è disabilitato se il backend dichiara microfono o
STT non disponibili.

Garanzie:

- il ciclo parte all'avvio solo se la configurazione lo richiede; il default del
  repository è attivo per scelta esplicita dell'utente;
- si ferma al click, alla chiusura dell'app e comunque dopo
  `voice.wake_word.max_minutes` minuti (0 = nessun limite, massimo 120);
- lo stato `running` passa a falso appena richiedi lo stop, anche se il thread è
  ancora dentro l'ultima registrazione;
- è **half-duplex**: durante la sintesi il microfono resta chiuso e i frammenti
  contaminati dalla voce di Amy vengono scartati (§5.1).

Se mancano registratore o STT, il ciclo si rifiuta di partire con un errore chiaro
(`400` con messaggio in italiano) e la UI lo mostra nel toast.

### Conferma vocale

Quando un comando richiede conferma (per esempio l'eliminazione di un evento),
Amy pronuncia la domanda e resta in attesa per **30 secondi**. In quella finestra
la wake word non serve: basta dire «sì», «confermo», «ok», «procedi» oppure «no»,
«annulla», «lascia stare».

- Una risposta non chiara fa ripetere «Rispondi sì oppure no.» senza chiudere la
  conferma.
- Allo scadere dei 30 secondi Amy dice «Conferma scaduta: operazione annullata.»
- La conferma resta comunque visibile nella dashboard: puoi rispondere a voce o
  con i pulsanti.
- Le eliminazioni restano di livello C: la voce è un modo per confermare, non un
  modo per saltare la conferma.

### Conversazione continua e interruzione

Dopo la wake word Amy resta in conversazione: le risposte successive **non
richiedono** di ripetere «Amy». Vale per domande di chiarimento, correzioni e
conferme.

Configurazione (`voice.conversation`):

| Chiave | Default | Significato |
| --- | --- | --- |
| `enabled` | `true` | conversazione continua attiva |
| `timeout_s` | `30` | silenzio massimo prima di chiedere «Sei ancora lì?» |
| `barge_in` | `true` | ascolta il microfono anche durante la sintesi |
| `barge_in_chunk_s` | `1.0` | durata dei frammenti di ascolto durante la sintesi |
| `barge_in_model` | vuoto | modello STT per il barge-in; vuoto = stesso modello dei comandi |
| `listen_seconds` | `8.0` | finestra fissa, usata solo se il VAD non è disponibile |
| `vad` | `true` | rileva la fine del parlato invece di tagliare a una durata fissa |
| `vad_silence_s` | `1.0` | pausa che chiude il turno |
| `vad_start_timeout_s` | `6.0` | attesa massima della voce prima di chiudere il frammento |
| `vad_max_seconds` | `15.0` | durata massima di un turno dettato |

Comportamento:

- Allo scadere del timeout Amy chiede «Sei ancora lì?» e concede un altro
  intervallo; se resta silenzio dice «Torno in standby.» e torna in attesa della
  wake word.
- «Basta», «stop», «fine conversazione», «chiudi» terminano la conversazione
  senza inviare il testo al modello.
- La conferma di un'operazione resta un caso a parte: la voce risponde «sì»/«no»
  e l'operazione è sempre legata alla conferma in sospeso.

**Interruzione durante la sintesi.** Con `barge_in` attivo il microfono continua
a registrare mentre Amy parla. Se il frammento trascritto contiene «Amy» e non è
l'eco della sintesi, Amy ferma subito `say`, passa allo stato `interrupted` e
ascolta il nuovo comando senza chiedere di nuovo la wake word.

Limiti onesti di questa implementazione:

- **Non c'è cancellazione acustica dell'eco (AEC).** Il filtro confronta il testo
  trascritto con quello che Amy sta pronunciando: se il frammento è contenuto nel
  testo della sintesi viene scartato. È un filtro testuale, non acustico.
- Se Amy sta pronunciando la parola «Amy» (per esempio nel saluto «Amy è attiva e
  operativa»), un'interruzione in quel preciso momento può essere scartata come
  eco. È il compromesso che evita di fermare Amy sulla propria voce.
- La latenza dipende dallo STT: con modello `small` su CPU Intel l'interruzione
  arriva in genere dopo 1–3 secondi, non all'istante.
- La registrazione non ha più una durata fissa: con il VAD attivo si ferma dopo
  circa un secondo di silenzio, quindi un indirizzo email o una frase lunga non
  vengono tagliati. Se il VAD non è disponibile, la finestra fissa è 8 secondi.
- Il rumore ambientale forte può produrre trascrizioni casuali; la wake word
  deve comunque comparire nel testo.
- **Con gli altoparlanti il barge-in è inaffidabile**: la voce di Amy arriva al
  microfono allo stesso livello della tua e può coprire «Amy». Con cuffie o un
  microfono direzionale funziona molto meglio. La cancellazione acustica vera
  richiederebbe il voice processing di Core Audio (AVAudioEngine via PyObjC),
  non ancora integrato: è la strada per un'interruzione immediata con gli
  altoparlanti.

La macchina a stati (`amy/voice/state.py`) espone lo stato reale alla dashboard:
`idle`, `wake_word_detected`, `listening`, `processing`, `speaking`,
`conversation_active`, `waiting_for_input`, `waiting_for_confirmation`,
`interrupted`, `error`, `offline`. Le transizioni non ammesse vengono registrate
nei log e corrette, non propagate in silenzio.

## 7. Privacy

- L'audio viene registrato in un file temporaneo e cancellato dopo la trascrizione.
- La trascrizione resta nella memoria locale se il comando viene eseguito.
- Il riconoscimento vocale è **locale**: `faster-whisper` non invia audio né testo a
  servizi esterni. L'unica rete è il download iniziale del modello.
- Se si configura un provider IA remoto, il **testo** della richiesta può essere
  inviato a quel provider: è una scelta dell'utente, non un comportamento nascosto.
- Il microfono è attivo durante un ascolto o un ciclo avviato esplicitamente, oppure all'avvio se `start_on_launch` è attivo.
- Il saluto di avvio non usa il microfono: è solo sintesi locale.
- Il ciclo continuo tiene il microfono aperto: la UI lo dichiara con lo stato
  «In ascolto» e con il pulsante premuto.

## 8. Limiti noti

1. Il ciclo continuo consuma CPU: trascrive anche i frammenti senza wake word e,
   con il barge-in attivo, anche quelli registrati durante la sintesi.
   L'interruzione non usa AEC: il filtro anti-eco è testuale.
2. Possibili falsi positivi su frasi che iniziano con parole simili ad «Amy».
   Osservato il 1 novembre 2026: una trascrizione rumorosa («Emi io vado da fare»)
   ha attivato il ciclo mentre Amy stava parlando: Amy sente anche i propri
   altoparlanti. Il log «Wake word rilevata» rende visibile l'evento.
   La protezione half-duplex (§5.1) riduce questo caso: i frammenti che
   contengono la voce di Amy vengono scartati, ma **non lo elimina del tutto**
   (per esempio quando Amy parla a volume basso o l'audio è heavily distorto).
3. Un solo parlante alla volta; nessuna separazione delle voci.
4. La latenza su Intel dipende dal modello: `base` è più veloce, `small` è più
   preciso ma più lento. Su questo Mac è stato scelto `small` con un prompt
   iniziale italiano, perché `base` sbagliava comandi come «apri mail». Con il ciclo attivo la rilevazione può
   arrivare alcuni secondi dopo la frase, perché ogni frammento viene prima
   registrato e poi trascritto.
5. I frammenti non si sovrappongono: una frase a cavallo tra due blocchi da 5 s può
   essere spezzata e non rilevata (osservato il 1 novembre 2026, subito dopo l'avvio
   del ciclo). Ripetere la frase risolve; una gestione con sovrapposizione costa CPU.
6. La firma ad-hoc dell'app cambia a ogni ricompilazione: macOS può chiedere di
   nuovo il permesso Microfono dopo un rebuild.
7. Non c'è ancora una wake word acustica dedicata a basso consumo.
8. Il blocco del HAL descritto in §4.1 non è causato da Amy e non può essere
   risolto dall'app: richiede un intervento sul sistema (riavvio di `coreaudiod`
   o del Mac).
9. Con la protezione half-duplex attiva, **mentre Amy parla il microfono è
   chiuso**: un comando dettato durante la risposta viene perso e va ripetuto.
