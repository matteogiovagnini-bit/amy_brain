# Robotica

Amy Brain è il livello **L2**: decide, chiede conferma e invia comandi di alto
livello. Non è il firmware e non controlla direttamente servi, GPIO o PWM. La fonte
canonica per protocollo, elettronica, pinout, firmware e prove hardware è il
repository gemello `../amy/`.

**Documenti canonici da leggere prima di toccare il robot:**

- [`../amy/docs/06_protocollo_mqtt.md`](../../amy/docs/06_protocollo_mqtt.md) — specifica
  MQTT v1;
- [`../amy/docs/07_sicurezza.md`](../../amy/docs/07_sicurezza.md) — sicurezza fisica,
  E-stop a tre livelli, piano di prove.

Questo documento descrive solo il lato Amy Brain e non sostituisce quelle fonti.

## 1. Stato reale

| Elemento | Stato |
| --- | --- |
| Simulatore locale | Implementato e coperto da test |
| Movimento fisico | **Non verificato**: nessun robot collegato |
| Link MQTT | **Sperimentale e non verificato** su broker/robot reale |
| Calibrazione meccanica | Non eseguita; il simulatore parte non calibrato |
| E-stop fisico | Non testato in questo ambiente |
| Watchdog reale | Implementato nel simulatore; non verificato su hardware |

Nessun risultato di questa repository dimostra che il robot fisico si muova in modo
sicuro.

## 2. Confini di responsabilità

Amy Brain può:

- leggere stato, heartbeat e batteria;
- inviare un obiettivo di posizione per giunto;
- chiedere un arresto controllato o un E-stop software;
- chiedere l'azzeramento di un latch dopo conferma esplicita;
- impostare la modalità nel simulatore.

Amy Brain **non può**:

- scrivere GPIO, PWM o registro dei servo;
- inviare coppie, correnti o tensioni;
- bypassare limiti, watchdog o E-stop del firmware;
- dichiarare completato un movimento senza un esito verificato.

La catena di sicurezza del robot reale (E-stop fisico in serie, enable hardware,
watchdog firmware) appartiene al repository canonico. Il software non può sostituirla.

## 3. Protocollo implementato

`amy/robot/protocol.py` implementa il sottoinsieme usato dal cervello Mac:

- envelope JSON a 8 campi: `v`, `type`, `req_id`, `seq`, `ts`, `src`, `dst`,
  `payload`, senza campi aggiuntivi;
- versione `1`;
- sorgenti ammesse: `amy-pi`, `amy-esp32-l`, `amy-esp32-t`;
- `req_id` di 26 caratteri Crockford base32, ordinabile per tempo;
- `seq` monotono per stream;
- dimensione massima pacchetto 3.072 byte;
- validazione dei tipi di messaggio e dei ruoli.

I nomi dei giunti sono:

```text
left_ankle_pitch   left_knee_pitch   left_hip_pitch
right_ankle_pitch  right_knee_pitch  right_hip_pitch
head_pan           head_tilt
```

I comandi di movimento usano `motion.target` per le gambe e `motion.head` per la
testa. Un dispositivo diverso dal Pi non può inviare comandi di movimento o
supervisione in v1.

Gli ACK/NACK sono correlati per `req_id`. Un ACK significa **accettazione**, non
completamento: il completamento richiede `motion.result`.

Per topic, QoS, retained, payload completi e semantica dettagliata fare riferimento
alla specifica canonica. Non duplicarla qui.

## 4. Limiti del simulatore

I limiti predefiniti sono **dimostrativi**, non la geometria reale:

| Giunto | Min | Max | Velocità max | Accelerazione max |
| --- | --- | --- | --- | --- |
| `left_ankle_pitch` | −25° | 25° | 30°/s | 60°/s² |
| `left_knee_pitch` | 0° | 90° | 30°/s | 60°/s² |
| `left_hip_pitch` | −35° | 35° | 30°/s | 60°/s² |
| `right_ankle_pitch` | −25° | 25° | 30°/s | 60°/s² |
| `right_knee_pitch` | 0° | 90° | 30°/s | 60°/s² |
| `right_hip_pitch` | −35° | 35° | 30°/s | 60°/s² |
| `head_pan` | −60° | 60° | 30°/s | 60°/s² |
| `head_tilt` | −20° | 40° | 30°/s | 60°/s² |

`zero_offset_deg` è `None` per tutti i giunti: il simulatore dichiara
`calibrated: false`. Questi valori servono a testare la logica, non a descrivere il
robot.

Un comando viene rifiutato (NACK) se:

- una posizione è fuori limite;
- `limits_version` non corrisponde;
- la traiettoria non entra nella `deadline_ms`;
- il robot è in modalità IDLE, SAFE o ESTOP;
- READY è richiesto senza calibrazione;
- c'è già un movimento in corso;
- la batteria è ≤ 5%;
- l'E-stop o un guasto sono latched;
- ci sono giunti duplicati o più di otto giunti.

La **posizione** non viene mai tagliata in silenzio: un valore fuori limite viene
rifiutato. Velocità e accelerazione, invece, vengono riportate al massimo consentito
e il risultato segnala il clamp nel campo `clamped`.

## 5. Modalità

| Modalità | Significato |
| --- | --- |
| `TEST` | Movimento solo simulato, nessun attuatore fisico |
| `IDLE` | Fermo; non accetta nuovi movimenti finché non torna in TEST o READY |
| `READY` | Accetta movimenti; richiede calibrazione completa |
| `SAFE` | Stato dopo watchdog o guasto |
| `ESTOP` | E-stop software latched |

Il simulatore parte in `TEST` e non calibrato. `set_mode("READY")` viene rifiutato
finché `zero_offset_deg` non è impostato. Solo i test chiamano
`simulation_calibrate()`, che è un espediente di test e **non** una calibrazione
reale.

## 6. Sicurezza nel simulatore

- **E-stop software:** latch immediato, modalità `ESTOP`, target portati alla
  posizione corrente, nessun movimento successivo. Non richiede conferma.
- **Stop controllato:** porta in `HOLD`, non riprende da solo.
- **Reset E-stop:** richiede `operator_ack=true`, è livello C, non riprende alcun
  movimento e riporta in `TEST`.
- **Watchdog:** se il Pi non invia heartbeat per `robot.simulator.watchdog_timeout_s`
  (default 5 s) durante un movimento, il simulatore arresta, latches il guasto e va
  in `SAFE`.
- **Deduplicazione:** lo stesso `req_id` non viene eseguito due volte; viene
  restituito l'esito precedente.
- **Sequenza:** `seq` per mittente/canale viene controllato.
- **Batteria:** sotto il 5% i movimenti vengono rifiutati.
- **Trasparenza:** ogni esito simulato dichiara `simulated: true` e
  `physical_motion: false`.

L'E-stop software **non** è l'E-stop fisico. Non toglie alimentazione, non apre il
rail e non garantisce che un servo non si muova. L'unico arresto garantito è quello
hardware descritto in `../amy/docs/07_sicurezza.md`.

## 7. Collegamento

### Simulato (predefinito)

```json
{
  "robot": {
    "transport": "simulated"
  }
}
```

In-process, senza rete. Il link aggiorna l'heartbeat prima di ogni comando. È il
default proprio per evitare che una demo venga scambiata per hardware reale.

### MQTT (sperimentale)

```json
{
  "robot": {
    "transport": "mqtt",
    "host": "amy-pi.local",
    "port": 1883,
    "username": "amy-pi",
    "password_env": "AMY_MQTT_PASSWORD",
    "tls": false,
    "timeout_s": 3.0
  }
}
```

La password si legge dalla variabile d'ambiente indicata o da
`~/.amy/secrets.json`. Non va scritta nella configurazione versionata.

Stato: **sperimentale**. Non è stato connesso a un broker reale né a un Raspberry Pi.
Inoltre il collegamento diretto Mac → broker è una deviazione consapevole
dall'architettura canonica, in cui il Pi è l'autorità MQTT. Va trattato come prova di
laboratorio.

Limiti noti del link MQTT:

- `robot.mode` non è supportato: il protocollo v1 non definisce un cambio modalità per
  il nodo reale; la modalità è gestita dal dispatcher sul Pi.
- Un ACK non è un completamento verificato.
- `estop()` invia `motion.stop` con motivo `estop_soft`: non è l'E-stop fisico.
- Non è stato verificato il comportamento in caso di rete instabile o riconnessione.

## 8. Comandi CLI

```bash
python3 -m amy robot status
python3 -m amy robot ping
python3 -m amy robot stop --reason manutenzione
python3 -m amy robot estop --reason operatore
python3 -m amy robot reset --confirm
python3 -m amy robot mode test --confirm
python3 -m amy robot move head_pan=10 --speed 10 --deadline 2000
```

`robot move`:

- richiede la parola `CONFERMO` se non si passa `--confirm`;
- valida i nomi dei giunti e i limiti prima di inviare;
- non mescola testa e gambe nello stesso comando;
- in modalità simulata riporta esplicitamente che nessun attuatore è stato mosso.

`robot reset` e `robot mode` sono livello B/C e richiedono `--confirm` in CLI. Non
sono mai automatici tramite il modello.

## 9. Strumenti esposti al modello

Vedi la sezione robot di [CONTROLLO_MAC.md](CONTROLLO_MAC.md). In sintesi:

- `robot.status`, `robot.ping`: lettura;
- `robot.estop`, `robot.stop`: sicurezza, mai in attesa di conferma;
- `robot.mode`: livello B;
- `robot.reset_estop`, `robot.move`: livello C, sempre conferma.

Amy non esegue un movimento fisico solo perché il modello lo propone: serve la
conferma dell'utente e il robot deve essere raggiungibile e in modalità compatibile.

## 10. Cosa manca per dichiarare il robot verificato

1. Broker MQTT di laboratorio e dispatcher sul Raspberry Pi.
2. Collegamento di un nodo ESP32 reale.
3. Verifica di ACK/NACK e `motion.result`.
4. Verifica del watchdog con heartbeat reale.
5. Calibrazione meccanica e conferma dei limiti reali.
6. Prova dell'E-stop fisico sotto carico.
7. Prova di perdita Wi-Fi, perdita alimentazione e blocco firmware.
8. Registrazione dei risultati in [TEST.md](TEST.md) e nel repository canonico.

Fino ad allora, ogni affermazione sul movimento fisico va considerata non verificata.
