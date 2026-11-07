# Comunicazione tra moduli

**Fase 1 — bus di eventi implementato**
Data: **7 novembre 2026**
Stato: `EventBus` disponibile in `amy/shared/events.py`, **non ancora collegato**
a Core, moduli e dashboard.

---

## 1. Perché un bus locale

Oggi la dashboard interroga lo stato e i moduli si parlano tramite chiamate
dirette. Un bus locale permette di:

- notificare cambi di stato senza polling stretto;
- disaccoppiare chi emette un evento da chi lo consuma;
- isolare un listener rotto dagli altri;
- mantenere uno storico breve per la UI e la diagnostica.

Non è un broker esterno: processo singolo, coda in memoria, nessuna rete.

---

## 2. Implementazione

`EventBus`:

- `subscribe(topic, handler)` → restituisce `unsubscribe()`;
- `unsubscribe(topic, handler)`;
- `publish(topic, payload)` → accoda un `Event` e restituisce l'evento;
- `flush(timeout)` → attende la consegna degli eventi accodati;
- `history(limit=None)` → ultimi eventi (storico circolare);
- `close()` → chiusura ordinata;
- wildcard `*` per tutti i topic.

Consegna in un thread dedicato (`amy-events`), coda limitata, errori dei listener
registrati e non propagati. La coda piena scarta l'evento con un warning: la UI non
deve fermare il Core.

---

## 3. Topic proposti

| Topic | Payload | Emesso da |
| --- | --- | --- |
| `core.turn.started` | `turn_id`, `session_id`, `text` | Core |
| `core.turn.finished` | `turn_id`, `status`, `tools` | Core |
| `module.status` | `name`, `state`, `detail` | ModuleRegistry |
| `tool.started` | `turn_id`, `tool`, `risk` | Registry |
| `tool.finished` | `turn_id`, `tool`, `ok`, `duration_ms` | Registry |
| `confirmation.requested` | `pending_id`, `tool`, `risk` | Core |
| `confirmation.resolved` | `pending_id`, `approved` | Core |
| `voice.state` | `state`, `reason` | Voice |
| `voice.transcript` | `text`, `final` | Voice |
| `robot.event` | `type`, `payload` | Robot |
| `memory.changed` | `category`, `key` | Memory |
| `provider.changed` | `provider`, `model`, `available` | AI |

Nomi e payload sono una proposta: vanno confermati quando i moduli reali vengono
collegati (Fase 2-3).

---

## 4. Regole

1. Un evento descrive un fatto già avvenuto, non un comando.
2. Il payload non contiene segreti, token o contenuti non redatti.
3. Un listener non deve bloccare: se serve lavoro lungo, accoda a sua volta.
4. Un errore di un listener non interrompe gli altri.
5. Lo storico è limitato e non è una memoria permanente.
6. La UI può usare polling o SSE; il bus non impone un trasporto.

---

## 5. Test

`tests/test_events.py` copre:

- consegna per topic e storico;
- wildcard;
- errore di un listener isolato;
- unsubscribe;
- storico limitato;
- pubblicazione concorrente da più thread.

---

## 6. Prossimi passi

- Collegare `module.status` al registro reale (Fase 2).
- Collegare `voice.state` alla macchina a stati vocale.
- Collegare `tool.started/finished` al registry.
- Valutare `/api/events` in polling per la dashboard (Fase 3).
- Valutare SSE solo se il polling non basta.
