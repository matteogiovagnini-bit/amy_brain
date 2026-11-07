# Moduli di Amy

**Fase 1-2 — contratti e adapter implementati**
Data: **7 novembre 2026**
Stato: contratti e otto adapter pronti; **non ancora collegati** a Core e UI.
`builtin.py` resta l'aggregatore di compatibilità con i 75 strumenti.

---

## 1. File

| File | Contenuto |
| --- | --- |
| `amy/shared/module.py` | `ModuleState`, `ModuleManifest`, `ModuleStatus`, `ModuleContext`, `AmyModule` |
| `amy/shared/events.py` | `Event`, `EventBus` |
| `amy/core/modules.py` | `ModuleRegistry`, `ModuleError` |
| `tests/test_modules.py` | 7 test di contratto e registro |
| `tests/test_events.py` | 6 test del bus |

`amy/shared/` non importa `core`, `tools` o `voice`: evita dipendenze circolari.

---

## 2. Contratto

```python
class AmyModule(Protocol):
    manifest: ModuleManifest
    def start(self, context: ModuleContext) -> None: ...
    def stop(self) -> None: ...
    def status(self) -> ModuleStatus: ...
    def tools(self) -> Sequence[Any]: ...
```

### ModuleManifest

Campi: `name`, `title`, `version`, `description`, `default_enabled`,
`capabilities`, `requires`, `tools`, `optional`.

Il manifest è l'identità pubblica del modulo: nome univoco, capacità dichiarate,
strumenti posseduti, dipendenze. `ModuleRegistry` rifiuta duplicati e strumenti
duplicati.

### ModuleStatus

Campi: `name`, `state`, `detail`, `available`, `data`.

Stati: `disabled`, `initializing`, `ready`, `busy`, `degraded`, `offline`, `error`.
Uno stato `offline` o `error` non blocca gli altri moduli.

### ModuleContext

Dipendenze condivise: `config`, `events`, `logger`, `data_dir`, `path_guard`,
`audit`, `memory`, `providers`, `secrets`. Un modulo riceve solo ciò che gli serve.

---

## 3. Ciclo di vita

```text
DISABLED ──enable──► INITIALIZING ──ok──► READY ──uso──► BUSY ──► READY
     ▲                    │                 │                  │
     └──────disable───────┴──errore──► ERROR / DEGRADED / OFFLINE
```

Regole applicate dal registro:

- un modulo disabilitato non viene avviato e non espone strumenti;
- un errore di avvio imposta `ERROR` e non ferma gli altri;
- `stop()` porta a `DISABLED`;
- `status()` del modulo può riportare `DEGRADED`/`OFFLINE` con un dettaglio;
- il registro pubblica `module.status` a ogni cambio.

---

## 4. API del registro

| Metodo | Funzione |
| --- | --- |
| `register(module, enabled=None)` | registra un modulo, rifiuta duplicati |
| `unregister(name)` | rimuove un modulo (dopo lo stop) |
| `start(name, context)` | avvia un modulo |
| `start_all(context)` | avvia tutti gli abilitati, isolando gli errori |
| `stop(name)` / `stop_all()` | arresta |
| `enable(name, context=None)` / `disable(name)` | abilita/disabilita |
| `status_of(name)` / `statuses()` / `snapshot()` | stato per la UI |
| `tools()` | strumenti dei soli moduli pronti, senza duplicati |

`statuses()` restituisce `{"manifest", "status", "enabled"}` per ogni modulo.
`snapshot()` restituisce `{"modules": [...]}`.

---

## 5. Test

- registrazione e avvio;
- duplicati di modulo e di strumento;
- errore di avvio isolato;
- modulo disabilitato senza strumenti;
- enable/disable;
- evento `module.status`;
- bus: consegna, wildcard, errori isolati, unsubscribe, storico, concorrenza.

Comando:

```bash
python3 -m unittest tests.test_modules tests.test_events -v
```

---

## 6. Adapter (Fase 2)

`amy/modules/` contiene un package per modulo, con un adapter che avvolge il codice
esistente senza spostarlo:

| Modulo | File | Strumenti | Default |
| --- | --- | --- | --- |
| Voice | `modules/voice/adapter.py` | `voice.speak`, `voice.stop` | attivo |
| Mac Control | `modules/mac_control/adapter.py` | app, file, shell, sistema, web, `time.now` (25) | attivo |
| Personal | `modules/personal/adapter.py` | calendario, promemoria, mail, task, note (25) | attivo |
| Memory | `modules/memory/adapter.py` | `memory.remember/list/forget/search/update/categories` (6) | attivo |
| Developer | `modules/developer/adapter.py` | OpenCode + `app.restart` (3) | spento |
| Vision | `modules/vision/adapter.py` | `screen.capture/read`, `vision.capture` (3) | attivo; telecamera spenta |
| Home | `modules/home/adapter.py` | `home.devices/state/set/scene` (4) | spento per default |
| Robot | `modules/robot/adapter.py` | 7 strumenti robot | attivo |

`build_module_registry()` in `amy/modules/registry.py` crea i registri; non li
avvia. Il test `tests/test_module_adapters.py` verifica che l'unione degli
strumenti dei moduli coincida esattamente con i 75 del registry esistente.

Note:

- `time.now` è stato spostato in `system.py` per coerenza; nome e comportamento
  sono invariati.
- `app.restart` appartiene al Developer, non a Mac Control.
- Developer è `DEGRADED` se OpenCode è disattivato, `OFFLINE` se il binario manca.
- Robot è `DEGRADED` se non riceve un link; con il simulatore è `READY`.
- Home è vuoto e spento: nessun dispositivo o broker in questa fase.

## 7. Collegamento a Core e UI (Fase 3)

`Assistant` crea il registro con gli otto adapter, lo avvia e lo espone:

- `Assistant.modules` — registro dei moduli;
- `Assistant.status()["modules"]` — manifest, stato e enabled;
- `Assistant.set_module_enabled(name, enabled)` — abilita/disabilita e aggiorna il
  catalogo strumenti attivo;
- Memory ha `optional=False`: il tentativo di disabilitarlo produce un errore 400.

API:

| Metodo | Percorso | Funzione |
| --- | --- | --- |
| GET | `/api/modules` | elenco con manifest e stato |
| GET | `/api/modules/{name}` | dettaglio |
| POST | `/api/modules/{name}/enabled` | `{"enabled": true|false}` |

UI: pannello «Moduli» con stato, dettaglio, strumenti e interruttore; polling ogni
30 s e aggiornamento dopo ogni modifica.

Limite dichiarato: l'abilitazione è **a runtime**. Al riavvio i moduli tornano
abilitati; la persistenza in configurazione è rimandata alla fase successiva.

## 8. Cosa manca (Fase 4+)

- Adapter dei moduli reali (`voice`, `mac_control`, `personal`, `memory`,
  `developer`, `vision`, `home`, `robot`).
- Registrazione nel Core e catalogo strumenti per modulo.
- `/api/modules` e pannello UI.
- Autorizzazioni per capacità.
- Eventi collegati a voce, robot, conferme e provider.

Nessuno di questi passi è stato eseguito in Fase 1.
