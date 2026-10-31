# Voce

Amy separa tre funzioni che spesso vengono confuse: **sintesi vocale (TTS)**,
**riconoscimento vocale (STT)** e **wake word**. In questa macchina solo la prima è
operativa; le altre due sono implementate ma non utilizzabili senza installare
dipendenze di sistema.

## 1. Stato reale

| Funzione | Stato | Dettaglio |
| --- | --- | --- |
| TTS macOS | **Verificato** | Comando `say`, voce italiana `Alice`, sintesi su file riuscita (58.276 byte) |
| Interruzione TTS | **Implementato** | `voice.speak` con `block=False`, `voice.stop` termina il processo |
| STT | **Non operativo qui** | `whisper-cli` assente e modello non configurato |
| Registratore | **Non operativo qui** | `ffmpeg` e `sox` assenti |
| Wake word | **Implementato, testuale** | Rileva «Amy» nella trascrizione, non è keyword spotting acustico |
| Ciclo vocale continuo | **Implementato, non verificato** | Richiede registratore e STT funzionanti |

`amy voice status` espone questa situazione senza mascherarla:

```json
{
  "enabled": false,
  "tts": {"available": true, "engine": "say", "voice": "Alice", "rate": 185},
  "stt": {"available": false, "engine": "whisper.cpp", "model_present": false},
  "recorder": {"available": false, "engine": "ffmpeg"},
  "ready_for_voice_commands": false
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
- Nella dashboard il pulsante di stop voce chiama `/api/voice/stop`.
- Il ciclo vocale esegue `tts.stop()` quando rileva la wake word, per simulare il
  barge-in.

Elenco delle voci italiane disponibili:

```bash
say -v '?' | grep 'it_IT'
```

Se la voce configurata non esiste, `say` fallisce e Amy riporta l'errore: non
sostituisce silenziosamente la voce.

## 3. Riconoscimento vocale

Amy supporta tre adattatori, scelti da `voice.stt.engine`:

| Valore | Motore | Requisiti |
| --- | --- | --- |
| `faster-whisper` | Python locale | pacchetto `faster_whisper`, modello scaricato |
| `whisper` | CLI OpenAI Whisper | comando `whisper` nel PATH |
| `whisper-cli` | whisper.cpp | comando `whisper-cli` e modello GGML locale |

Configurazione predefinita (whisper.cpp):

```json
{
  "voice": {
    "stt": {
      "engine": "whisper-cli",
      "command": "whisper-cli",
      "model": "",
      "language": "it"
    }
  }
}
```

Il modello **non** viene scaricato automaticamente: un percorso vuoto rende lo STT
non disponibile e `amy doctor` lo segnala come `ATTENZIONE`, non come `OK`.

### Installazione possibile (non eseguita in questa verifica)

Le istruzioni dipendono dall'ambiente dell'utente. Amy non le esegue da sola e non
installa pacchetti.

- whisper.cpp: compilare il progetto, scaricare un modello GGML italiano o
  multilingua, impostare `voice.stt.command` e `voice.stt.model` con percorsi
  assoluti.
- OpenAI Whisper CLI: installare il pacchetto Python e verificare che `whisper` sia
  nel PATH.
- faster-whisper: installare il pacchetto e verificare l'import.

Dopo l'installazione:

```bash
python3 -m amy voice status
python3 -m amy voice listen --seconds 5
```

Se lo STT non è disponibile, `voice listen` restituisce un errore esplicito. Non
inventa una trascrizione.

## 4. Registratore

Due motori:

- `ffmpeg` (default) con input `avfoundation`, dispositivo `:0`, mono 16 kHz;
- `sox` con input di default.

Configurazione:

```json
{
  "voice": {
    "recorder": {
      "engine": "ffmpeg",
      "device": ":0",
      "seconds": 5
    }
  }
}
```

La durata è limitata tra 1 e 30 secondi. La prima registrazione richiede il permesso
**Microfono** in Impostazioni di Sistema. Se il file è vuoto o il comando fallisce,
Amy riporta l'errore.

Il dispositivo `:0` è quello predefinito di macOS. Per scegliere un microfono
specifico:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

Poi impostare `voice.recorder.device` con l'indice corretto.

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
      "sensitivity": 0.5
    }
  }
}
```

Varianti accettate:

- sensibilità ≥ 0,5: `amy`, `ehi amy`, `hey amy`, `ok amy`;
- sensibilità ≥ 0,8: anche `ami`, `ammy`, `emmi` (errori tipici di trascrizione).

Due modalità d'uso:

- «Amy, che ore sono?» → estrae direttamente il comando;
- «Amy» da sola → ascolta un secondo frammento e lo usa come comando.

Limite dichiarato: **non è un motore audio dedicato**. Consuma STT su tutto l'audio
ascoltato e può attivarsi su frasi somiglianti. Per un rilevamento a basso consumo
servirebbe un filtro acustico (per esempio openWakeWord) davanti allo STT, non
ancora integrato.

## 6. Ciclo vocale continuo

```bash
python3 -m amy voice loop
python3 -m amy voice loop --execute
```

- Senza `--execute` trascrive e mostra i comandi, senza eseguirli.
- Con `--execute` passa il testo all'assistente e pronuncia la risposta, ma **non**
  autorizza automaticamente azioni che richiedono conferma.
- `Ctrl-C` termina il ciclo.
- Il ciclo parte solo da questo comando esplicito: Amy non apre il microfono in
  background all'insaputa dell'utente.

Se mancano registratore o STT, il ciclo si rifiuta di partire con un errore chiaro.

## 7. Privacy

- L'audio viene registrato in un file temporaneo e cancellato dopo la trascrizione.
- La trascrizione resta nella memoria locale se il comando viene eseguito.
- Nessun audio viene inviato a servizi cloud dal codice attuale.
- Se si configura un provider IA remoto, il **testo** della richiesta può essere
  inviato a quel provider: è una scelta dell'utente, non un comportamento nascosto.
- Il microfono è attivo solo durante un ascolto o un ciclo avviato esplicitamente.

## 8. Cosa manca per considerare la voce completa

1. Installare e verificare `ffmpeg` o `sox`.
2. Installare e verificare un motore STT locale con modello italiano.
3. Provare con microfono reale, rumore ambiente e parlanti diversi.
4. Misurare latenza e qualità della trascrizione italiana.
5. Verificare l'interruzione durante una risposta lunga.
6. Valutare una wake word acustica dedicata.
7. Ripetere la verifica e aggiornare [STATO_PROGETTO.md](STATO_PROGETTO.md).

Nessuna di queste voci è stata completata in questo ambiente.
