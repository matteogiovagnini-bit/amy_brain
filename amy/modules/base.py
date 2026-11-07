"""Base comune agli adapter dei moduli."""

from __future__ import annotations

from typing import Any, Callable, List, Sequence

from ..shared.module import ModuleContext, ModuleManifest, ModuleState, ModuleStatus
from ..tools.registry import ToolRegistry


def collect_tools(register: Callable[[ToolRegistry], None]) -> List[Any]:
    """Costruisce gli strumenti di un gruppo senza registrarli nel registry globale."""
    registry = ToolRegistry()
    register(registry)
    return list(registry.all())


def tool_names(tools: Sequence[Any]) -> List[str]:
    return [str(getattr(getattr(tool, "spec", None), "name", "")) for tool in tools]


class BaseAdapter:
    """Adapter minimo: stato, ciclo di vita e strumenti già esistenti."""

    def __init__(self, manifest: ModuleManifest, tools: Sequence[Any]) -> None:
        self.manifest = manifest
        self._tools = list(tools)
        self._state = ModuleState.DISABLED
        self._detail = "non avviato"
        self._context: Any = None

    def start(self, context: ModuleContext) -> None:
        self._context = context
        self._state = ModuleState.READY
        self._detail = "pronto"

    def stop(self) -> None:
        self._state = ModuleState.DISABLED
        self._detail = "disabilitato"
        self._context = None

    def status(self) -> ModuleStatus:
        available = self._state in {
            ModuleState.READY,
            ModuleState.BUSY,
            ModuleState.DEGRADED,
        }
        return ModuleStatus(
            name=self.manifest.name,
            state=self._state,
            detail=self._detail,
            available=available,
        )

    def tools(self) -> Sequence[Any]:
        return list(self._tools)
