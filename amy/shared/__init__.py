"""Contratti condivisi tra Amy Core e i moduli.

Questo package non dipende da `core`, `tools` o `voice`: contiene solo
interfacce, stati ed eventi. Serve a evitare import circolari durante la
migrazione.
"""

from .events import Event, EventBus
from .module import AmyModule, ModuleContext, ModuleManifest, ModuleState, ModuleStatus

__all__ = [
    "Event",
    "EventBus",
    "AmyModule",
    "ModuleContext",
    "ModuleManifest",
    "ModuleState",
    "ModuleStatus",
]
