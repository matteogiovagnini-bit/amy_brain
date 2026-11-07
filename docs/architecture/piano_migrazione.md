# Piano di migrazione architetturale

**Fase 3 — piano di migrazione**
Data: **7 novembre 2026**
Baseline: commit `dab07ed`, **376 test verdi**, 57 strumenti.
Stato: **proposta da approvare**. Nessuna modifica al codice è stata eseguita.

---

## 1. Regole della migrazione

1. **Un passo alla volta.** Ogni fase è autonoma, testata e reversibile.
2. **Adapter prima, spostamenti dopo.** Prima si creano i contratti e gli adapter
   attorno al codice esistente; i file si spostano solo quando i test sono verdi.
3. **Compatibilità totale.** CLI, API HTTP, configurazione, test e app nativa
   continuano a funzionare in ogni fase.
4. **Nessuna regressione funzionale.** Se un test esistente fallisce, la fase non è
   conclusa.
5. **Nessuna dipendenza a pagamento.** Ogni nuova libreria va verificata (licenza,
   costo, compatibilità Intel/Python 3.9) e documentata.
6. **Sicurezza invariata.** A/B/C, E-stop fuori policy, path guard, shell chiusa,
   audit restano.
7. **Documentare ogni passo.** Aggiornare `STATO_PROGETTO`, `CHANGELOG`, `TEST` e i
   documenti di architettura nello stesso lavoro.
8. **Nessun commit automatico.** Le modifiche vengono commitate solo su richiesta.

---

## 2. Invarianti da preservare

- `python3 -m amy` e tutti i sottocomandi CLI.
- `/api/state`, `/api/chat`, `/api/confirm`, `/api/tools`, `/api/transcript`,
  `/api/voice/*`, `/api/robot/*`, `/api/calendar/upcoming`.
- Il formato di `~/.amy/config.json` e `~/.amy/secrets.json`.
- Il protocollo d'azione JSON e il catalogo testuale del prompt.
- Il comportamento di conferma in due fasi e il TTL.
- La dashboard e l'app Swift (self-test compreso).
- I 376 test esistenti.

---

## 3. Mappatura dei componenti

| Componente attuale | Modulo target | Azione | Dipendenze | Test esistenti |
| --- | --- | --- | --- | --- |
| `core/assistant.py` | Amy Core (`core/orchestrator.py` + facciata) | **adattare**, non riscrivere | tools, ai, memory, policy | `test_orchestrator`, `test_prompt_budget` |
| `core/prompts.py` | Core | mantenere, catalogo dinamico | registry | `test_prompt_budget` |
| `core/config.py` | Core/Infra | aggiungere `config_version` e `modules` | — | `test_config` |
| `core/system_info.py` + `macos/applescript.system_info` | Mac Control (`SystemService`) | **unificare** | — | `test_system_info` |
| `core/restart.py` | Core/Developer | mantenere | app nativa | `test_restart` |
| `ai/*` | Core/Infra (`ProviderRegistry`) | mantenere, aggiungere routing | — | `test_providers`, `test_online_presets` |
| `tools/{apps,files,shell,system,web}.py` | Mac Control | spostare/adattare | policy, path guard | `test_files`, `test_shell`, `test_battery`, `test_system_info` |
| `macos/{applescript,calendar,reminders,mail,screen}.py` | Mac Control / Personal / Vision | mantenere come servizi | TCC | `test_calendar`, `test_reminders`, `test_mail`, `test_screen` |
| `tools/{calendar,reminders,mail}_tools.py` | Personal Manager | spostare/adattare | macOS services | `test_calendar`, `test_reminders`, `test_mail` |
| `Assistant.upcoming_events` + `/api/calendar/upcoming` | Personal Manager (`agenda`) | **spostare** la logica | calendar | `test_server`, `test_calendar` |
| `memory/store.py` + `memory_tools.py` | Memory | estendere schema + adapter | SQLite | `test_memory` |
| `voice/*` | Voice Engine | mantenere, esporre stato/eventi | audio, STT, TTS | `test_voice*`, `test_conversation`, `test_recorder` |
| `tools/{opencode_tools,voice_tools,robot_tools}.py` | Developer / Voice / Robot | spostare/adattare | servizi | `test_opencode`, `test_voice*`, `test_simulator` |
| `robot/*` | Robot Control | mantenere | protocollo, MQTT | `test_protocol`, `test_simulator` |
| `security/*` | Security | mantenere, aggiungere `authorization.py` | — | `test_policy` |
| `ui/server.py` + `static/*` | UI | aggiungere `/api/modules`, pannello | Core | `test_server`, `test_ui_static` |
| `apps/AmyCore/*` | UI nativa | mantenere, aggiungere pulsanti moduli | backend | `test_native_app` |

**Legenda azioni:** mantenere = nessuna modifica sostanziale; adattare = wrapper o
interfaccia; spostare = cambio di percorso con shim; unificare = eliminare la
duplicazione.

---

## 4. Fasi

### Fase 0 — Baseline e sicurezza del lavoro (mezza giornata)

- Confermare `git status` pulito e 376 test verdi.
- Registrare commit e ambiente nell'audit.
- Creare `docs/architecture/` (questo passaggio).
- Non modificare codice.

**Criterio:** documenti creati, test verdi, nessuna modifica funzionale.

---

### Fase 1 — Contratti condivisi, senza cambiare comportamento

**Stato: completata il 7 novembre 2026** (contratti, registro, bus e 13 test; nessun modulo reale registrato).

**Obiettivo:** introdurre `shared/module.py`, `shared/events.py`, `core/modules.py`
e i test di contratto, senza registrare ancora i moduli reali.

Passi:
1. Creare `amy/shared/module.py` con `ModuleState`, `ModuleManifest`,
   `ModuleStatus`, `AmyModule`, `ModuleContext`.
2. Creare `amy/shared/events.py` con `EventBus` (coda, listener, storico).
3. Creare `amy/core/modules.py` con `ModuleRegistry` (register/start/stop/status).
4. Test: lifecycle, stato, eventi, isolamento errori, modulo disabilitato.
5. Documentare in `docs/architecture/moduli.md`.

**Criterio:** 376 test + nuovi test verdi; nessun modulo reale registrato; CLI/API
invariati.

**Rollback:** rimuovere i nuovi file; nessun impatto.

---

### Fase 2 — Adapter dei moduli esistenti

**Stato: completata il 7 novembre 2026** (otto adapter, 57 strumenti invariati, 10 test).

**Obiettivo:** avvolgere le aree esistenti in moduli senza spostare file.

Passi:
1. `modules/voice/adapter.py` → avvolge `VoiceService`, espone `status()` e
   `tools()` (`voice.speak`, `voice.stop`).
2. `modules/mac_control/adapter.py` → avvolge i tool app/file/shell/system/web e
   `screen.*`; espone `SystemService` unificato.
3. `modules/personal/adapter.py` → calendario, promemoria, mail; sposta qui
   `upcoming_events` come `agenda()`.
4. `modules/memory/adapter.py` → `MemoryStore` + tool.
5. `modules/developer/adapter.py` → OpenCode + restart + git read-only.
6. `modules/vision/adapter.py` → screen/OCR; `describe`/camera disabilitati.
7. `modules/robot/adapter.py` → link/simulatore/protocollo.
8. `modules/home/adapter.py` → scheletro spento per default.
9. `ModuleRegistry` registra gli adapter; `builtin.py` continua a funzionare come
   aggregatore di compatibilità.

**Criterio:** gli strumenti sono gli stessi 57; i test esistenti passano; ogni
modulo espone stato e manifest; nessun file spostato.

**Rollback:** rimuovere gli adapter e la registrazione; `builtin.py` resta la
fonte.

---

### Fase 3 — Stato moduli e API

**Stato: completata il 7 novembre 2026** (`/api/modules`, toggle a runtime, pannello UI, 5 test; persistenza rimandata).

**Obiettivo:** far vedere i moduli alla dashboard, senza cambiare il comportamento
degli strumenti.

Passi:
1. `StatusAggregator` compone `Assistant.status()` + `modules`.
2. `/api/modules` e `/api/modules/{name}`.
3. `POST /api/modules/{name}/enabled` con policy: disabilitare un modulo rimuove i
   suoi strumenti dal catalogo attivo e annulla le conferme pendenti.
4. Pannello UI «Moduli» con stati reali, interruttori e dettagli.
5. Test server/UI e test di contratto per abilitazione/disabilitazione.

**Criterio:** `/api/state` conserva i campi attuali e aggiunge `modules`; 376 test
+ nuovi verdi; la UI mostra stati reali; un modulo disabilitato non espone tool.

**Rollback:** rimuovere l'endpoint e il pannello; lo stato resta invariato.

---

### Fase 4 — Autorizzazioni per modulo

**Stato: completata il 7 novembre 2026** (broker, capacità, revoche, audit, API e pannello UI; 11 test).

**Obiettivo:** capacità dichiarate e applicate dal codice.

Passi:
1. `security/authorization.py`: `Capability`, `AuthorizationBroker`.
2. Ogni manifest dichiara `capabilities`; il broker verifica modulo abilitato +
   capacità + rischio.
3. La policy A/B/C resta l'ultima parola; C sempre confermato.
4. Revoca: disabilitare modulo/capacità impedisce nuove esecuzioni.
5. UI: pannello permessi e log delle decisioni.
6. Test: capability negata, modulo disabilitato, C non aggirabile, revoca.

**Criterio:** nessuna riduzione di sicurezza; test esistenti verdi; audit include
`module` e `capability`.

**Rollback:** il broker può essere disattivato con una flag di compatibilità,
tornando alla policy attuale.

---

### Fase 5 — Memoria estesa

**Obiettivo:** categorie, progetti, note, task, ricerca, verifica.

Passi:
1. Migrazione SQLite: `memory_items` (categorie, tag, confidence, verified,
   expires_at), `tasks`, `notes`.
2. Migrazione non distruttiva da `facts`; `facts` resta in lettura.
3. Strumenti: `memory.search`, `memory.update`, `memory.categories`;
   `tasks.*`, `notes.*` nel Personal Manager.
4. Prompt: includere solo i fatti rilevanti e verificati, entro un budget.
5. UI: consultazione, modifica, cancellazione, export.
6. Test: migrazione, ricerca, scadenza, nessun segreto, budget prompt.

**Criterio:** dati esistenti preservati; 376 test + nuovi verdi; memoria
consultabile e cancellabile.

**Rollback:** la migrazione crea nuove tabelle senza eliminare `facts`; si può
tornare alla lettura dei fatti.

---

### Fase 6 — Personal Manager completo

**Obiettivo:** agenda unificata, task, note, modifiche eventi.

Passi:
1. `PersonalManager.agenda()` unica per dashboard e assistente.
2. `calendar.update` (B) con conferma; ricorrenze/fusi orari documentati.
3. Task e note con priorità, scadenza, stato.
4. UI: agenda, task, note.
5. Test: update, ricorrenze, priorità, scadenze.

**Criterio:** nessuna regressione su calendario/promemoria/mail; nuovi test verdi.

---

### Fase 7 — Vision e Smart Home (opzionali, spenti per default)

**Vision**
1. Separare `vision.ocr` (già pronto) da `vision.describe` e `vision.camera`.
2. `describe`: provider visivo gratuito, solo se configurato; altrimenti dichiarare
   non disponibile.
3. `camera`: interfaccia; implementazione solo con dispositivo e permesso.
4. Test: provider assente, OCR, immagine non valida, privacy.

**Smart Home**
1. Registry dispositivi + config MQTT + credenziali da segreti.
2. Strumenti `home.devices`, `home.state`, `home.set`, `home.scene`.
3. Livelli B/C; timeout; online/offline; nessun produttore obbligatorio.
4. Test con broker simulato/mock; nessuna rete reale nei test.

**Criterio:** moduli spenti per default; nessun impatto sul resto; test verdi.

---

### Fase 8 — Developer Assistant nativo

**Obiettivo:** ridurre la dipendenza da OpenCode per le operazioni di sola lettura.

Passi:
1. `dev.status` (git, test, dipendenze), `dev.diff`, `dev.analyze` (sola lettura).
2. `dev.test` esegue la suite del progetto con timeout e output limitato.
3. OpenCode resta per le modifiche (C) e il restart.
4. UI: stato progetto, ultimo test, diff.
5. Test: comandi ammessi, timeout, output, nessuna scrittura.

**Criterio:** nessuna esecuzione arbitraria; test verdi; OpenCode invariato.

---

### Fase 9 — Dashboard e documentazione finale

1. Pannello moduli completo, log, permessi, memoria, provider.
2. Split graduale di `app.js` in moduli locali (senza bundler).
3. Aggiornare `STATO_PROGETTO`, `CHANGELOG`, `TEST`, `CONTROLLO_MAC`,
   `ARCHITETTURA`, `AGENTS` solo dove serve.
4. Creare `docs/architecture/moduli.md`,
   `sistema_autorizzazioni.md`, `comunicazione_moduli.md`,
   `docs/knowledge/stato_corrente.md`.
5. Verifica finale: compileall, 376+ test, doctor, self-test nativo, prova reale
   delle funzioni toccate.

**Criterio:** documentazione allineata al codice; nessuna affermazione non
verificata; test verdi.

---

## 5. Shim di compatibilità

| Shim | Scopo | Durata |
| --- | --- | --- |
| `tools/builtin.py` | continua a comporre il registry dai moduli | fino a Fase 4 |
| `Assistant` | facciata su `Orchestrator` | permanente (API interna) |
| `/api/state` | mantiene i campi attuali, aggiunge `modules` | permanente |
| `memory.facts` | resta leggibile dopo la migrazione | almeno una release |
| `voice.status()` | resta, alimentato dal modulo | permanente |
| `calendar.upcoming` | diventa `PersonalManager.agenda()` | fino a Fase 6 |

Nessuno shim deve diventare una seconda fonte di verità: ogni dato ha un solo
proprietario.

---

## 6. Test plan

### Esistenti (da mantenere verdi)
376 test: orchestratore, policy, schema, provider, preset gratuiti, file, shell,
web, memoria, voce, wake word, conversazione, registratore, TTS, batteria, sistema,
calendario, promemoria, mail, OpenCode, restart, screen, server, UI, app nativa.

### Nuovi (per fase)
- Contratto moduli: manifest, stato, lifecycle, disabilitazione.
- Event bus: ordine, isolamento errori, storico, thread safety.
- Registry moduli: tool posseduti, conflitti, modulo spento.
- Autorizzazioni: capacità, revoca, C non aggirabile, conferme pendenti.
- Memoria: migrazione, categorie, ricerca, scadenza, budget prompt.
- Personal: agenda, update, task, note.
- Vision: OCR, provider assente, camera negata.
- Home: registry, MQTT mock, timeout, credenziali.
- Developer: git/test/diff in sola lettura, timeout.
- UI: `/api/modules`, pannello, stati reali, accessibilità.
- Integrazione: modulo offline non blocca il Core.

### Verifica manuale (quando il codice cambia)
- `amy doctor`, `amy ask --offline`, self-test nativo.
- Prova reale della funzione toccata (voce, calendario, mail, OpenCode, screen).
- Nessuna dichiarazione di hardware robotico non provato.

---

## 7. Rischi e mitigazioni

| Rischio | Probabilità | Impatto | Mitigazione |
| --- | --- | --- | --- |
| Rottura import durante lo spostamento | media | alto | adapter + shim, test a ogni passo |
| Regressione stato/UI | media | medio | snapshot e test server/UI |
| Doppia fonte di verità | media | alto | un proprietario per dato |
| Modulo disabilitato ma tool ancora attivo | bassa | alto | registry per modulo + test |
| Autorizzazioni indebolite | bassa | critico | C invariato, test di policy, audit |
| Memoria migrata male | bassa | alto | backup, nuove tabelle, `facts` intatto |
| Provider visivo a pagamento | bassa | critico | solo gratuiti, spento per default |
| Smart Home senza hardware | alta | medio | mock, stato offline dichiarato |
| OpenCode modifiche indesiderate | media | alto | C, cartella autorizzata, diff/backup |
| Tempo/scope eccessivo | alta | medio | fasi piccole, stop dopo ogni fase |

---

## 8. Decisioni richieste prima della Fase 1

1. **Confini dei moduli**: Mail e Web stanno in Personal/Mac Control? (proposta:
   Mail in Personal, Web in Mac Control).
2. **Percorsi**: creare `amy/modules/` e `amy/shared/` come adapter, con
   spostamento fisico solo dopo? (proposta: sì).
3. **Memoria**: aggiungere `memory_items`, `tasks`, `notes` in SQLite, mantenendo
   `facts`? (proposta: sì).
4. **UI**: pannello moduli con abilitazione/disabilitazione e log? (proposta: sì).
5. **Vision**: `describe` e `camera` spenti per default? (proposta: sì).
6. **Smart Home**: scheletro ora o dopo Developer? (proposta: dopo Vision).
7. **OpenCode**: mantenere C e cartella autorizzata, senza sandbox? (proposta: sì,
   con avviso esplicito).

---

## 9. Ordine consigliato e criterio di stop

Ordine: **Fase 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9**.

Dopo ogni fase:
- eseguire `compileall` e l'intera suite;
- aggiornare i documenti;
- presentare un riepilogo con test e differenze;
- attendere l'approvazione prima della fase successiva.

La migrazione si ferma se un test esistente non passa o se una funzionalità
verificata peggiora. In quel caso si torna all'ultimo commit verde e si rivede il
passo.
