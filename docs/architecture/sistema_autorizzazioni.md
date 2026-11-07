# Sistema di autorizzazioni

**Fase 4 — autorizzazioni per modulo e capacità**
Data: **7 novembre 2026**
Stato: implementato e verificato; revoche a runtime.

---

## 1. Ordine dei controlli

Per ogni azione proposta dal modello:

```text
1. lo strumento esiste nel registry attivo
2. lo strumento appartiene a un modulo registrato
3. il modulo è abilitato
4. la capacità richiesta è dichiarata dal modulo
5. la capacità non è revocata
6. PolicyEngine valuta il rischio A/B/C
7. se B/C: conferma in due fasi
8. esecuzione, attività, audit
```

Il broker **non decide le conferme**: il livello C resta sempre confermato dalla
policy, anche se modulo e capacità sono autorizzati. Il broker non può
trasformare un C in automatico.

---

## 2. Capacità

`capability_for_tool()` in `amy/security/authorization.py` mappa ogni strumento
sulla capacità dichiarata dal suo modulo:

| Strumenti | Capacità | Modulo |
| --- | --- | --- |
| `apps.*` | `mac.app` | Mac Control |
| `files.*` | `mac.file` | Mac Control |
| `shell.*` | `mac.shell.read` | Mac Control |
| `web.*` | `mac.web` | Mac Control |
| `system.*`, `time.*` | `mac.system` | Mac Control |
| `calendar.*` | `personal.calendar` | Personal |
| `reminders.*` | `personal.reminders` | Personal |
| `mail.*` | `personal.mail` | Personal |
| `memory.list` | `memory.read` | Memory |
| `memory.remember`, `memory.forget` | `memory.write` / `memory.delete` | Memory |
| `opencode.*` | `dev.execute` | Developer |
| `app.restart` | `dev.restart` | Developer |
| `screen.*` | `vision.screen` | Vision |
| `voice.*` | `voice.tts` | Voice |
| `robot.status`, `robot.ping` | `robot.read` | Robot |
| `robot.move`, `robot.mode` | `robot.move` | Robot |
| `robot.estop`, `robot.stop`, `robot.reset_estop` | `robot.estop` | Robot |
| `home.*` | `home.read` / `home.set` | Smart Home |

Ogni capacità deve essere dichiarata nel manifest del modulo; altrimenti il
broker rifiuta l'azione.

---

## 3. Revoca

- `AuthorizationBroker.revoke(capability)` blocca tutti gli strumenti di quella
  capacità.
- `restore(capability)` la riabilita.
- La revoca è **a runtime**: non viene scritta in `~/.amy/config.json`.
- Disabilitare un modulo resta il modo più ampio per fermare i suoi strumenti.
- Memory è un modulo essenziale e non può essere disabilitato; le sue capacità
  possono essere revocate, ma le funzioni di memoria del Core continuano a
  esistere (le sessioni non dipendono dagli strumenti).

API:

| Metodo | Percorso | Funzione |
| --- | --- | --- |
| GET | `/api/permissions` | capacità, modulo e stato revoca |
| POST | `/api/permissions/revoke` | `{"capability": "..."}` |
| POST | `/api/permissions/restore` | `{"capability": "..."}` |

La dashboard ha il pannello **Permessi** con interruttore Revoca/Ripristina.

---

## 4. Conferme pendenti

- Se una capacità viene revocata mentre una conferma è in sospeso, l'esecuzione
  viene rifiutata al momento dell'approvazione.
- Disabilitare un modulo annulla le conferme pendenti dei suoi strumenti.
- La conferma resta legata alla specifica operazione; un «sì» fuori contesto non
  autorizza nulla.

---

## 5. Audit

`tool_rejected`, `tool_execution_started` e `confirmation_requested` includono:

- `module`: modulo proprietario;
- `capability`: capacità richiesta;
- `risk`;
- `error_code` (`authorization_denied` per un rifiuto del broker).

Esempio osservato:

```text
tool_rejected screen.read vision vision.screen authorization_denied
```

---

## 6. Test

- mapping strumento → modulo → capacità;
- capacità revocata blocca lo strumento;
- capacità sconosciuta rifiutata;
- modulo disabilitato blocca i suoi strumenti;
- revoca e ripristino;
- il broker non cambia la policy C: `robot.move` resta con conferma;
- endpoint `/api/permissions` e revoca/ripristino via HTTP;
- pannello UI con Revoca/Ripristina.

Comandi:

```text
python3 -m unittest tests.test_authorization tests.test_server tests.test_ui_static
```

---

## 7. Limiti dichiarati

- Revoche e abilitazioni non sono persistenti al riavvio: tornano allo stato
  iniziale (tutti i moduli abilitati, nessuna capacità revocata).
- La granularità è per capacità, non per singolo strumento. Una revoca più fine
  richiederebbe un manifest per strumento.
- La revoca non è una sandbox: impedisce l'esecuzione attraverso Amy, non protegge
  da un processo esterno che agisce con i permessi dell'utente.
