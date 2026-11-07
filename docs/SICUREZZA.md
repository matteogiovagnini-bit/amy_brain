# Sicurezza

La sicurezza di Amy è implementata nel codice, non affidata al prompt del modello.
Questo documento descrive le difese attuali, i limiti e le cose che **non** sono
garantite.

Per la sicurezza hardware del robot la fonte canonica è
`../amy/docs/07_sicurezza.md`. Lì valgono E-stop fisico, safe state HOLD, watchdog e
catena di alimentazione. Qui si descrive il lato Mac.

## 1. Modello di minaccia

Amy assume che possano essere ostili o inaffidabili:

- il testo dell'utente, che può chiedere azioni pericolose;
- il modello IA, che può inventare strumenti, argomenti o esiti;
- il contenuto di file e pagine web, che può contenere prompt injection;
- un errore di configurazione, per esempio un livello C inserito tra gli
  auto-approvati;
- un percorso che tenta di uscire dalle cartelle autorizzate tramite symlink;
- un URL che punta a servizi locali o alla rete privata;
- un comando shell costruito per iniettare argomenti.

Amy **non** assume di essere al sicuro su una rete pubblica. La dashboard è pensata
per il loopback.

## 2. Livelli di rischio

| Livello | Significato | Comportamento |
| --- | --- | --- |
| A | ordinario, reversibile o in sola lettura | auto-approvato se configurato |
| B | impatto significativo | conferma, salvo allow-list esplicita per nome |
| C | sensibile o irreversibile | conferma **sempre**, anche se configurato male |

Esempi:

- A: leggere l'ora, stato sistema, stato robot, E-stop, stop.
- B: scrivere un file, chiudere un'app, cambiare modalità robot.
- C: cestinare un file, sovrascrivere una destinazione, muovere i giunti, resettare
  l'E-stop.

Il livello C non è mai auto-approvato: `PolicyEngine.evaluate()` lo intercetta prima
di guardare la configurazione.

## 3. Conferma in due fasi

1. Amy valida lo strumento e gli argomenti.
2. Calcola il rischio.
3. Se serve conferma, restituisce `confirmation_required` con:
   - strumento;
   - argomenti redatti;
   - rischio e etichetta;
   - motivo;
   - conseguenze;
   - possibilità di annullamento;
   - TTL.
4. L'utente autorizza o annulla.
5. Solo dopo l'autorizzazione lo strumento viene eseguito.

In CLI il livello C richiede di digitare esattamente `CONFERMO`. In un terminale non
interattivo l'operazione viene negata. Nella dashboard la conferma è un dialogo
dedicato.

La richiesta di conferma vive in memoria e non è persistita su disco. Se Amy si
riavvia, il pending decade.

## 4. Percorsi e file

`PathGuard`:

- risolve il percorso e i symlink prima di controllare;
- richiede che il risultato sia dentro una delle `security.allowed_roots`;
- nega nomi e cartelle sensibili: `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`,
  keychain, cookie, `.env`, `.pem`, `.key`, `.p12`, `.pfx`, chiavi `id_rsa*` e
  `id_ed25519*`, `secrets.json`, credenziali;
- nega qualsiasi componente che inizia con `.`;
- impone `security.max_file_bytes` in lettura e scrittura;
- verifica la dimensione prima di leggere o scrivere.

Comportamenti aggiuntivi:

- `files.write` crea un backup del file esistente in `~/.amy/backups`;
- la scrittura usa un file temporaneo e `os.replace`, con `fsync`;
- `files.trash` sposta nel cestino Amy, non elimina definitivamente;
- `files.move` richiede rischio C se la destinazione esiste;
- `files.read` rifiuta i file binari e tronca il testo oltre il limite.

Limiti:

- le radici autorizzate sono una scelta dell'utente: se include `~`, la protezione
  resta affidata alla deny-list;
- un file sensibile con nome non previsto dalla deny-list può essere accessibile se
  si trova in una radice autorizzata;
- il backup non è una garanzia contro ogni errore umano: va verificato.

## 5. Shell

`shell.run` non accetta stringhe arbitrarie. Accetta un enum chiuso:

- `disk_usage`, `list_directory`;
- `git_status`, `git_diff`, `git_log`;
- `python_version`, `uptime`, `date`, `whoami`, `sw_vers`, `processes`.

I comandi sono avviati come lista di argomenti, senza `shell=True`, con `cwd`
validato dal path guard, timeout e output limitato. I comandi Git richiedono un
percorso esplicito dentro le radici.

Non esistono strumenti per installare pacchetti, modificare permessi, eseguire
script o lanciare comandi con pipe/redirezione.

## 5.1 Calendario e Automazione

`calendar.create` scrive un evento reale in Calendar.app tramite `osascript`.
Misure applicate:

- livello di rischio **B**: richiede la conferma dell'utente prima di scrivere;
- testi escapati per AppleScript, date costruite per componenti (nessuna stringa
  di shell, nessuna interpolazione libera);
- calendario di destinazione scelto per nome, con `calendar.default_name`
  configurabile e nessuna scrittura nei calendari di sistema (festività,
  compleanni, suggerimenti);
- risultato verificabile: UID dell'evento, calendario, inizio e fine;
- il primo uso richiede il permesso **Automazione** per Calendar in Impostazioni
  di Sistema → Privacy e Sicurezza → Automazione. Se manca, l'errore lo dice.

`calendar.list` e `calendar.events` sono di livello A e non modificano nulla.
`mail.accounts`, `mail.mailboxes`, `mail.list` e `mail.search` sono di livello A e
leggono solo metadati (mittente, oggetto, data). `mail.read` è di livello **B**:
il corpo può essere inviato al provider IA configurato, quindi richiede conferma.
`mail.send` è di livello **C**: crea e invia un'email e non può essere annullato.
La conferma mostra destinatari, oggetto e corpo; gli indirizzi sono validati e
non sono ammessi ritorni a capo. Nessuno strumento di posta sposta o cancella
messaggi.
`calendar.delete` è di livello **C**: richiede sempre una conferma esplicita e non
può essere auto-approvato. La conferma può essere data a voce («sì»/«no»), ma
questo cambia solo il canale della risposta, non il requisito: la domanda viene
pronunciata e la conferma resta visibile anche nella dashboard.

Il barge-in (dire «Amy» mentre parla) interrompe solo la sintesi: non annulla una
conferma in sospeso e non autorizza nulla. La conferma resta legata alla specifica
operazione e scade con le regole già descritte.

Lo stesso schema vale per Promemoria:

- `reminders.lists` e `reminders.list` sono di livello A;
- `reminders.create` e `reminders.complete` sono di livello B;
- `reminders.delete` è di livello C e richiede sempre conferma;
- i testi sono escapati e le date costruite per componenti, come per il calendario.

## 5.2 Agente esterno OpenCode

`opencode.run` avvia la CLI gratuita `opencode2` con una lista di argomenti
(nessuna shell) nella cartella di progetto. Misure:

- livello **C**: richiede sempre una conferma esplicita;
- nessun flag `--auto`: OpenCode applica le proprie regole di permesso;
- la cartella deve stare nelle radici autorizzate, altrimenti viene rifiutata;
- timeout finito e output troncato;
- sessione persistente per cartella, salvata in `~/.amy/opencode_sessions.json`.

**OpenCode lavora con i permessi dell'utente**: può creare, modificare o
cancellare file ed eseguire comandi. La conferma di Amy non è una sandbox.
Controlla la richiesta e usa Git o i backup del progetto.

`app.restart` è di livello **C** e riavvia l'app nativa. La riapertura non dipende
da OpenCode: viene lanciato un helper fisso e staccato (`start_new_session`), che
attende l'uscita della vecchia app, riapre il bundle e verifica `/api/health`. Se
il riavvio fallisce, il log è in `~/.amy/restart.log` e Amy va riaperta a mano.

## 5.3 Schermo e OCR

`screen.capture` e `screen.read` sono di livello **B**: uno screenshot può
contenere password, messaggi o documenti aperti. Il primo uso richiede il permesso
**Registrazione schermo** in Impostazioni di Sistema → Privacy e Sicurezza.

- la cattura usa `screencapture`, senza shell;
- l'OCR usa Vision in locale, tramite un helper Swift compilato sul Mac;
- l'immagine resta in `~/.amy/screenshots` e non viene inviata in rete;
- il **testo** riconosciuto può essere inviato al provider IA configurato: con un
  provider online è un dato che lascia il Mac.

## 5.4 Autorizzazioni per modulo e capacità

`AuthorizationBroker` (`amy/security/authorization.py`) aggiunge un controllo
prima della policy:

1. lo strumento appartiene a un modulo registrato;
2. il modulo è abilitato;
3. la capacità richiesta è dichiarata dal manifest;
4. la capacità non è revocata.

Solo dopo interviene `PolicyEngine` con A/B/C. Il broker **non** decide le
conferme e non può rendere automatico un livello C. Una capacità revocata o un
modulo disabilitato impediscono l'esecuzione con `authorization_denied`; l'audit
registra `module` e `capability`.

Revoche e toggle sono a runtime, non persistenti. Non sono una sandbox: fermano
le azioni richieste attraverso Amy, non un processo esterno con i permessi
dell'utente.

## 6. Web e prompt injection

`web.fetch`:

- accetta solo `http` e `https`;
- risolve l'host e rifiuta loopback, link-local, multicast, reserved e indirizzi
  privati;
- ricontrolla i redirect;
- limita download e testo;
- non esegue JavaScript;
- tratta il contenuto come dato non attendibile.

Il prompt di sistema dice esplicitamente al modello di non seguire istruzioni
contenute in pagine o file. Questa è una difesa in profondità, non l'unica: la policy
nel codice resta il confine.

Rischio residuo: un attacco di DNS rebinding potrebbe cambiare la risoluzione tra il
controllo e la richiesta. Non è stato implementato un resolver pinned.

## 7. Segreti

- Le chiavi API non stanno nella configurazione versionata.
- Si leggono da variabili d'ambiente o da `~/.amy/secrets.json`.
- `secrets.json` deve avere permessi `0600`; permessi più aperti causano errore.
- Log, audit, memoria e dashboard redigono i valori sensibili.
- La dashboard non mostra chiavi API.
- Nessun segreto viene inviato al modello nel prompt.

La redazione è euristica: nomi di campo come `api_key`, `token`, `password`,
`secret`, `authorization` e simili vengono oscurati. Un segreto inserito in un campo
con nome innocuo potrebbe non essere riconosciuto.

## 8. Dashboard

- Bind predefinito `127.0.0.1`.
- Bind non-loopback bloccato salvo `ui.allow_remote=true`.
- Nessuna autenticazione: anche con il flag, l'esposizione remota è sconsigliata.
- Nessun CDN, nessuna risorsa esterna.
- CSP con `default-src 'self'`, `script-src 'self'`, `frame-ancestors 'none'`.
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`.
- Il client usa `textContent` e costruzione DOM, mai `innerHTML`.
- Il server limita la dimensione del corpo delle richieste e blocca il path traversal
  sui file statici.
- `GET /api/calendar/upcoming` è di sola lettura: esegue esclusivamente
  `calendar.events`, il cui livello di rischio viene verificato prima dell'uso.
  Se lo strumento non fosse più di livello A la lettura viene bloccata. Da questo
  endpoint non può partire `calendar.create` (B) né `calendar.delete` (C), e la
  finestra è limitata a 14 giorni. Non introduce autenticazione, nuove porte o
  dati remoti.

Limiti: il server non ha CSRF token, rate limiting o login. È adatto al loopback e a
un uso personale, non a Internet.

## 9. Robot

- Solo comandi di alto livello: niente GPIO, PWM o servo diretti.
- `robot.move` è livello C e richiede sempre conferma.
- `robot.estop` e `robot.stop` sono livello A e non aspettano conferme.
- Il simulatore parte in `TEST`, non calibrato, e dichiara sempre
  `simulated: true` e `physical_motion: false`.
- `READY` è rifiutato senza calibrazione.
- Limiti per giunto, velocità, accelerazione e deadline sono validati; i valori fuori
  limite vengono rifiutati, non tagliati in silenzio (salvo clamp espliciti di
  velocità/accelerazione).
- Il watchdog arresta il movimento se manca l'heartbeat del Pi.
- Deduplicazione per `req_id` e controllo sequenza per destinatario.
- L'E-stop software latches e richiede un reset esplicito.

**L'E-stop fisico è l'unico arresto garantito.** Il software non può garantire che un
servo non si muova, che un bus sia integro o che l'alimentazione sia stata tolta.

## 10. Audit

`~/.amy/audit.jsonl` è append-only e contiene:

- creazione sessione;
- richiesta di conferma, approvazione, rifiuto, scadenza;
- inizio e fine esecuzione strumento;
- strumenti rifiutati per schema o nome;
- errori IA;
- azioni robot;
- E-stop dalla dashboard.

Gli argomenti sono redatti e troncati. L'audit non sostituisce i log applicativi e
non è firmato o immutabile a livello di filesystem: un utente con accesso alla
macchina può modificarlo.

## 11. Cosa non è garantito

- Sicurezza su hardware robotico reale.
- Correttezza del link MQTT.
- Resistenza a un modello IA compromesso che propone continuamente azioni.
- Isolamento multi-utente: Amy è pensata per un utente sulla sua macchina.
- Protezione da malware locale con gli stessi permessi dell'utente.
- Cancellazione sicura dei dati (il cestino è recuperabile).
- Anonimizzazione del contenuto inviato a un provider remoto se configurato.
- Disponibilità continua o ripristino automatico.

## 12. Regole per chi sviluppa

1. Non aggiungere un percorso che aggiri `PolicyEngine`.
2. Non rendere C auto-approvabile.
3. Non mettere E-stop dietro una conferma.
4. Non usare `shell=True`.
5. Non allargare le radici o la deny-list senza test.
6. Non inserire segreti nei test, nei log o nella documentazione.
7. Non dichiarare verificato ciò che non lo è.
8. Aggiungere un test per ogni nuova azione pericolosa.
