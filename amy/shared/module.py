"""Contratto dei moduli di Amy.

Un modulo dichiara ciò che sa fare, il proprio stato e gli strumenti che possiede.
Amy Core lo avvia, lo ferma e ne aggrega lo stato; non conosce le sue
implementazioni interne.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Sequence, runtime_checkable


class ModuleState(str, Enum):
    DISABLED = "disabled"
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass(frozen=True)
class ModuleManifest:
    """Identità e capacità dichiarate di un modulo."""

    name: str
    title: str
    version: str = "0.1.0"
    description: str = ""
    default_enabled: bool = False
    capabilities: Sequence[str] = ()
    requires: Sequence[str] = ()
    tools: Sequence[str] = ()
    optional: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "version": self.version,
            "description": self.description,
            "default_enabled": bool(self.default_enabled),
            "capabilities": list(self.capabilities),
            "requires": list(self.requires),
            "tools": list(self.tools),
            "optional": bool(self.optional),
        }


@dataclass
class ModuleStatus:
    """Stato reale di un modulo, mostrato alla dashboard."""

    name: str
    state: ModuleState
    detail: str = ""
    available: bool = False
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "detail": self.detail,
            "available": bool(self.available),
            "data": dict(self.data),
        }

    @classmethod
    def disabled(cls, name: str, detail: str = "disabilitato") -> "ModuleStatus":
        return cls(name=name, state=ModuleState.DISABLED, detail=detail)

    @classmethod
    def ready(cls, name: str, detail: str = "") -> "ModuleStatus":
        return cls(name=name, state=ModuleState.READY, detail=detail, available=True)

    @classmethod
    def error(cls, name: str, detail: str) -> "ModuleStatus":
        return cls(name=name, state=ModuleState.ERROR, detail=detail, available=False)


@dataclass
class ModuleContext:
    """Dipendenze condivise passate a un modulo all'avvio.

    I campi sono volutamente generici per non creare dipendenze circolari tra
    `shared` e i package applicativi.
    """

    config: Any
    events: Any
    logger: Any = None
    data_dir: Optional[Path] = None
    path_guard: Any = None
    audit: Any = None
    memory: Any = None
    providers: Any = None
    secrets: Any = None


@runtime_checkable
class AmyModule(Protocol):
    """Interfaccia minima che ogni modulo deve rispettare."""

    manifest: ModuleManifest

    def start(self, context: ModuleContext) -> None:
        ...

    def stop(self) -> None:
        ...

    def status(self) -> ModuleStatus:
        ...

    def tools(self) -> Sequence[Any]:
        ...
