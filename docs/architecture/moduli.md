# Moduli di Amy

**Fase 1 — contratto implementato**
Data: **7 novembre 2026**
Stato: infrastruttura pronta, **non ancora collegata** a Core, strumenti e UI.
Nessun modulo reale è registrato in questa fase.

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

## 6. Cosa manca (Fase 2+)

- Adapter dei moduli reali (`voice`, `mac_control`, `personal`, `memory`,
  `developer`, `vision`, `home`, `robot`).
- Registrazione nel Core e catalogo strumenti per modulo.
- `/api/modules` e pannello UI.
- Autorizzazioni per capacità.
- Eventi collegati a voce, robot, conferme e provider.

Nessuno di questi passi è stato eseguito in Fase 1.
