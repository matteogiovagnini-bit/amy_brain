"""Macchina a stati della voce di Amy.

Un unico punto di verità per lo stato vocale, condiviso da ciclo di ascolto,
backend HTTP e dashboard. Le transizioni sono dichiarate: uno stato incoerente
viene registrato nei log e corretto, non propagato in silenzio.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..core.logging_setup import get_logger

_log = get_logger("voice.state")


class VoiceState(str, Enum):
    IDLE = "idle"
    WAKE_WORD_DETECTED = "wake_word_detected"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    CONVERSATION_ACTIVE = "conversation_active"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    OFFLINE = "offline"


#: Transizioni ammesse. La macchina è volutamente permissiva sulle vie di
#: ritorno (IDLE, ERROR, OFFLINE) ma impedisce salti privi di senso, per esempio
#: da PROCESSING direttamente a LISTENING senza passare dalla sintesi.
ALLOWED: Dict[VoiceState, Set[VoiceState]] = {
    VoiceState.IDLE: {
        VoiceState.WAKE_WORD_DETECTED,
        VoiceState.LISTENING,
        VoiceState.SPEAKING,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
        VoiceState.OFFLINE,
    },
    VoiceState.WAKE_WORD_DETECTED: {
        VoiceState.LISTENING,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.ERROR,
        VoiceState.IDLE,
    },
    VoiceState.LISTENING: {
        VoiceState.PROCESSING,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.WAITING_FOR_INPUT,
        VoiceState.INTERRUPTED,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.PROCESSING: {
        VoiceState.SPEAKING,
        VoiceState.WAITING_FOR_CONFIRMATION,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.WAITING_FOR_INPUT,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
    },
    VoiceState.SPEAKING: {
        VoiceState.INTERRUPTED,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.WAITING_FOR_INPUT,
        VoiceState.WAITING_FOR_CONFIRMATION,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.CONVERSATION_ACTIVE: {
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.WAITING_FOR_INPUT,
        VoiceState.WAITING_FOR_CONFIRMATION,
        VoiceState.INTERRUPTED,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.WAITING_FOR_INPUT: {
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.WAITING_FOR_CONFIRMATION,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.INTERRUPTED,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.WAITING_FOR_CONFIRMATION: {
        VoiceState.PROCESSING,
        VoiceState.SPEAKING,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.WAITING_FOR_INPUT,
        VoiceState.INTERRUPTED,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.INTERRUPTED: {
        VoiceState.LISTENING,
        VoiceState.CONVERSATION_ACTIVE,
        VoiceState.IDLE,
        VoiceState.ERROR,
    },
    VoiceState.ERROR: {
        VoiceState.IDLE,
        VoiceState.OFFLINE,
        VoiceState.LISTENING,
    },
    VoiceState.OFFLINE: {
        VoiceState.IDLE,
        VoiceState.LISTENING,
    },
}


class VoiceStateMachine:
    """Stato vocale thread-safe con listener per la dashboard."""

    def __init__(self, initial: VoiceState = VoiceState.IDLE) -> None:
        self._state = initial
        self._reason = ""
        self._lock = threading.Lock()
        self._listeners: List[Callable[[VoiceState, str], None]] = []

    @property
    def state(self) -> VoiceState:
        with self._lock:
            return self._state

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def subscribe(self, listener: Callable[[VoiceState, str], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def can_transition(self, target: VoiceState) -> bool:
        with self._lock:
            return target == self._state or target in ALLOWED.get(self._state, set())

    def set(self, target: VoiceState, reason: str = "") -> bool:
        """Imposta lo stato; restituisce False se la transizione non era ammessa."""
        with self._lock:
            previous = self._state
            allowed = target == previous or target in ALLOWED.get(previous, set())
            if not allowed:
                _log.warning(
                    "Transizione vocale non prevista: %s → %s (%s)",
                    previous.value,
                    target.value,
                    reason or "senza motivo",
                )
            self._state = target
            self._reason = reason
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(target, reason)
            except Exception:  # noqa: BLE001 - un listener non deve rompere la voce
                _log.warning("Listener dello stato vocale non riuscito", exc_info=True)
        return allowed

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"state": self._state.value, "reason": self._reason}
