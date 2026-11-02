# Controllo del Mac

Amy espone 35 strumenti. Non sono comandi generici: ognuno ha uno schema JSON
rigoroso, un livello di rischio e un comportamento verificabile. Questo documento
elenca il catalogo effettivo, raggruppato per dominio.

Per installazione, provider IA e configurazione vedi
[CONFIGURAZIONE.md](CONFIGURAZIONE.md). Per le regole di sicurezza vedi
[SICUREZZA.md](SICUREZZA.md).

## 1. Elenco rapido

```bash
python3 -m amy tools
```

Mostra nome, rischio e descrizione di ogni strumento registrato. La dashboard espone
lo stesso catalogo su `GET /api/tools`.

## 2. Sistema

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `system.info` | A | Versione macOS, architettura, CPU, RAM, disco, utente |
| `system.battery` | A | Batteria del Mac: percentuale, carica o scarica, tempo residuo |
| `system.processes` | A | Processi ordinati per CPU o memoria |
| `system.settings` | A | Apre il pannello di Impostazioni di Sistema pertinente |
| `time.now` | A | Data e ora locali |

Esempi:

```text
Stato del sistema
Quanto è carica la batteria del Mac?
Quali processi usano più CPU?
Che ore sono?
```

`system.battery` legge `pmset -g batt`, un comando di sola lettura: non cambia
nulla e non richiede permessi. Se il Mac non ha una batteria integrata, lo dice
con chiarezza invece di restituire un valore inventato. È la batteria **del
computer**: quella del robot si legge con `robot.status`.

`system.settings` è pensato per guidare l'utente sui permessi (microfono, accessibilità,
automazione). Non modifica impostazioni al posto suo.

## 3. Applicazioni macOS

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `apps.list` | A | Elenca le applicazioni installate, con ricerca per nome |
| `apps.running` | A | Verifica se un'app è in esecuzione |
| `apps.frontmost` | A | Nome dell'app in primo piano |
| `apps.open` | A | Apre un'app installata |
| `apps.focus` | A | Porta in primo piano un'app già in esecuzione |
| `apps.quit` | B | Chiede la chiusura di un'app: può perdere modifiche non salvate |

`apps.quit` è livello B perché una chiusura può distruggere stato non salvato. Non
forza la chiusura e non usa `kill`.

L'integrazione usa AppleScript e le API di macOS. La prima volta il sistema può
chiedere il permesso **Automazione**; se l'utente lo nega, lo strumento fallisce con
un errore e non aggira il permesso.

## 4. File

Tutte le operazioni sono confinate in `security.allowed_roots` (default:
`~/Progetti`, `~/Documents`, `~/Desktop`, `~/Downloads`).

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `files.list` | A | Elenca file e cartelle |
| `files.read` | A | Legge un file di testo entro il limite |
| `files.search` | A | Cerca file per nome nelle radici |
| `files.diff` | A | Differenze unificate tra due file di testo |
| `files.mkdir` | A | Crea una cartella |
| `files.write` | B | Scrive o sostituisce un file, con backup |
| `files.move` | B/C | Sposta; se la destinazione esiste diventa C |
| `files.trash` | C | Sposta nel cestino recuperabile di Amy |

Dettagli importanti:

- i percorsi sensibili (`.ssh`, `.gnupg`, `.aws`, `.env`, chiavi, `secrets.json`,
  credenziali) sono negati anche dentro una radice autorizzata;
- i symlink vengono risolti prima del controllo: un link che esce dalle radici è
  negato;
- `files.write` crea un backup in `~/.amy/backups` se il file esiste;
- `files.trash` **non cancella definitivamente**: sposta in
  `~/.amy/backups/trash/`;
- la lettura di file binari viene rifiutata;
- la dimensione massima è `security.max_file_bytes` (default 1 MiB).

Esempi:

```text
Elenca i file in ~/Progetti/amy_brain
Leggi il file ~/Progetti/amy_brain/README.md
Cerca i file robot
```

La scrittura, la creazione di cartelle e le richieste articolate richiedono il
modello IA completo: l'interprete offline copre solo un sottoinsieme di comandi.

## 5. Shell

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `shell.run` | A | Esegue un comando di sola lettura da un enum chiuso |

Comandi ammessi: `disk_usage`, `list_directory`, `git_status`, `git_diff`,
`git_log`, `python_version`, `uptime`, `date`, `whoami`, `sw_vers`, `processes`.

Regole:

- nessuna stringa di shell arbitraria;
- nessun `shell=True`;
- argomenti come lista;
- `git_*` richiede un percorso esplicito dentro le radici;
- timeout `security.shell_timeout_s` (default 20 s);
- output limitato.

Amy **non** è un terminale. Non può installare pacchetti, cambiare permessi, eseguire
script o usare pipe e redirezioni.

## 6. Web

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `web.open` | A | Apre un URL http/https nel browser predefinito |
| `web.search` | A | Apre una ricerca DuckDuckGo nel browser |
| `web.fetch` | A | Legge il testo di una pagina pubblica |

`web.fetch`:

- accetta solo `http` e `https`;
- risolve l'host e blocca loopback, link-local, multicast, reserved e reti private;
- ricontrolla i redirect;
- non esegue JavaScript;
- limita dimensione e lunghezza del testo;
- tratta il contenuto come **dato**, non come istruzione.

Il contenuto di una pagina non può cambiare la policy: il modello non ha il potere di
eseguire comandi trovati online. Resta un rischio residuo di DNS rebinding, descritto
in [SICUREZZA.md](SICUREZZA.md).

## 7. Memoria

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `memory.remember` | A | Salva un fatto o una preferenza duratura |
| `memory.list` | A | Elenca i fatti salvati |
| `memory.forget` | A | Elimina un fatto |

Esempi:

```text
Ricorda che la città è Roma
Cosa sai di me?
Dimentica la città
```

La memoria è locale, in SQLite. I fatti vengono iniettati nel prompt entro
`memory.max_facts_in_prompt`. Non vengono inviati a servizi esterni se non come parte
del testo della richiesta al provider configurato.

## 8. Voce

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `voice.speak` | A | Pronuncia un testo con la voce italiana |
| `voice.stop` | A | Interrompe la sintesi in corso |

Dettagli e limiti in [VOCE.md](VOCE.md).

## 9. Robot

| Strumento | Rischio | Cosa fa |
| --- | --- | --- |
| `robot.status` | A | Stato, modalità, batteria, E-stop, heartbeat, giunti |
| `robot.ping` | A | Verifica raggiungibilità e RTT |
| `robot.estop` | A | E-stop software immediato, senza conferma |
| `robot.stop` | A | Arresto controllato, safe state HOLD |
| `robot.mode` | B | Modalità TEST, IDLE o READY |
| `robot.reset_estop` | C | Azzera il latch dopo verifica dell'area |
| `robot.move` | C | Movimento di gambe o testa, sempre con conferma |

`robot.move` e `robot.reset_estop` non sono mai automatici. `robot.estop` e
`robot.stop` non vengono mai messi in attesa di conferma.

Dettagli in [ROBOTICA.md](ROBOTICA.md).

## 10. Livelli di rischio in pratica

| Livello | Significato | Comportamento |
| --- | --- | --- |
| A | ordinario, reversibile o in lettura | auto-approvato se configurato |
| B | impatto significativo | conferma, salvo allow-list per nome |
| C | sensibile o irreversibile | conferma sempre |

Configurazione predefinita: `security.auto_approve_levels = ["A"]` e
`security.auto_approve_tools = []`. Il livello C viene intercettato prima di
guardare la configurazione.

## 11. Come si autorizza un'azione

CLI interattiva:

```text
Amy propone: files.write su ~/Progetti/nota.txt (livello B: impatto significativo)
Scrivi CONFERMO per autorizzare:
```

Solo `CONFERMO` esatto autorizza. In un terminale non interattivo l'azione viene
negata. La dashboard mostra un dialogo con strumento, argomenti redatti, motivo,
conseguenze e possibilità di annullamento.

La conferma ha una scadenza (`security.confirmation_ttl_s`, default 300 s). Un
pending scaduto non viene eseguito.

## 12. Esempi utili

```bash
# Stato del sistema
python3 -m amy ask "stato del sistema" --offline
python3 -m amy ask "che ore sono?" --offline

# Batteria del Mac
python3 -m amy ask "quanto è carica la batteria del mac?" --offline

# File nelle radici autorizzate
python3 -m amy ask "elenca i file in ~/Progetti" --offline

# Memoria
python3 -m amy memory set città Roma
python3 -m amy memory list

# Voce
python3 -m amy voice speak "Ciao"
```

## 13. Limiti del controllo Mac

- Non controlla il sistema a livello di kernel o amministratore.
- Non installa software, non modifica permessi, non esegue script arbitrari.
- Non modifica lo stato energetico del Mac: la batteria viene solo letta.
- Non legge fuori dalle radici autorizzate.
- Non cancella definitivamente file.
- Non aggira i permessi di macOS: se l'utente nega Microfono o Automazione, la
  funzione non è disponibile.
- Non è un agente sempre attivo: esegue un'azione per turno.
- Le app vengono aperte e chiuse tramite macOS, non tramite accesso diretto alla
  memoria dei processi.
