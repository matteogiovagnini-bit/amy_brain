"""Bus di eventi locale, in-process e thread-safe.

Non è un broker esterno: la consegna avviene in un thread dedicato con una coda
limitata, così un listener lento non blocca il chiamante. Gli errori dei listener
vengono isolati e registrati: un modulo rotto non ferma gli altri.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

_log = logging.getLogger("amy.events")

#: Topic speciale che riceve tutti gli eventi.
ALL_TOPICS = "*"


@dataclass(frozen=True)
class Event:
    topic: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    sequence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": dict(self.payload),
            "created_at": self.created_at,
            "sequence": self.sequence,
        }


class EventBus:
    """Pub/sub locale con storico circolare e chiusura ordinata."""

    def __init__(self, *, history_size: int = 200, max_queue: int = 1000) -> None:
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=max(10, max_queue))
        self._history: Deque[Event] = deque(maxlen=max(1, history_size))
        self._sequence = 0
        self._closed = False
        self._worker = threading.Thread(target=self._run, name="amy-events", daemon=True)
        self._worker.start()

    # ---------------------------------------------------------------- API
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> Callable[[], None]:
        """Registra un listener e restituisce la funzione per annullarlo."""
        if not callable(handler):
            raise TypeError("Il listener deve essere chiamabile.")
        topic = str(topic or ALL_TOPICS)
        with self._lock:
            self._subscribers.setdefault(topic, []).append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(topic, handler)

        return unsubscribe

    def unsubscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            handlers = self._subscribers.get(topic) or []
            if handler in handlers:
                handlers.remove(handler)
            if not handlers:
                self._subscribers.pop(topic, None)

    def publish(self, topic: str, payload: Optional[Dict[str, Any]] = None) -> Event:
        """Accoda un evento. Non blocca il chiamante salvo coda piena."""
        if self._closed:
            raise RuntimeError("EventBus chiuso.")
        with self._lock:
            self._sequence += 1
            event = Event(
                topic=str(topic),
                payload=dict(payload or {}),
                sequence=self._sequence,
            )
        try:
            self._queue.put(event, timeout=1.0)
        except queue.Full:
            # La UI non deve fermare il Core: si perde l'evento più vecchio.
            _log.warning("Coda eventi piena: evento %s scartato", topic)
        return event

    def flush(self, timeout: float = 2.0) -> bool:
        """Attende che gli eventi accodati siano stati consegnati."""
        done = threading.Event()

        class _Marker:
            pass

        try:
            self._queue.put(_Marker(), timeout=max(0.1, timeout))
        except queue.Full:
            return False

        # Il marker viene processato dal worker; per semplicità usiamo un
        # contatore di coda: quando la coda è vuota, il marker è stato letto.
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks <= 1:
                done.set()
                break
            time.sleep(0.01)
        return done.is_set()

    def history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        if limit is not None:
            items = items[-max(0, int(limit)):]
        return [event.to_dict() for event in items]

    def close(self, timeout: float = 2.0) -> None:
        self.flush(timeout=timeout)
        self._closed = True
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    @property
    def closed(self) -> bool:
        return self._closed

    # -------------------------------------------------------------- worker
    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if not isinstance(item, Event):
                    continue
                with self._lock:
                    self._history.append(item)
                    subscribers = {
                        topic: list(handlers)
                        for topic, handlers in self._subscribers.items()
                    }
                targets = list(subscribers.get(item.topic, [])) + list(
                    subscribers.get(ALL_TOPICS, [])
                )
                for handler in targets:
                    try:
                        handler(item)
                    except Exception:  # noqa: BLE001 - un listener non ferma gli altri
                        _log.warning(
                            "Listener di %s non riuscito", item.topic, exc_info=True
                        )
            finally:
                self._queue.task_done()
