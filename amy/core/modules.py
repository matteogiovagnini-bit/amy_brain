"""Registro e ciclo di vita dei moduli di Amy.

Il registro è l'unico punto che conosce l'elenco dei moduli, il loro stato e gli
strumenti che possiedono. Amy Core lo interroga per lo stato e per il catalogo;
un modulo disabilitato non espone strumenti.

Questa è l'infrastruttura della Fase 1: non registra ancora i moduli reali e non
cambia il comportamento esistente.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Iterable, List, Optional

from ..shared.events import EventBus
from ..shared.module import (
    AmyModule,
    ModuleContext,
    ModuleManifest,
    ModuleState,
    ModuleStatus,
)
from .errors import AmyError

_log = logging.getLogger("amy.modules")


class ModuleError(AmyError):
    code = "module_error"


class ModuleRegistry:
    """Registro thread-safe dei moduli, con avvio, arresto e stato."""

    def __init__(self, *, events: Optional[EventBus] = None) -> None:
        self.events = events
        self._modules: Dict[str, AmyModule] = {}
        self._manifests: Dict[str, ModuleManifest] = {}
        self._statuses: Dict[str, ModuleStatus] = {}
        self._enabled: Dict[str, bool] = {}
        self._contexts: Dict[str, Optional[ModuleContext]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------- registro
    def register(self, module: AmyModule, *, enabled: Optional[bool] = None) -> None:
        manifest = getattr(module, "manifest", None)
        if not isinstance(manifest, ModuleManifest):
            raise ModuleError("Il modulo non dichiara un ModuleManifest valido.")
        name = manifest.name
        if not name:
            raise ModuleError("Il modulo ha un nome vuoto.")
        with self._lock:
            if name in self._modules:
                raise ModuleError("Modulo già registrato: %s" % name)
            active = bool(manifest.default_enabled if enabled is None else enabled)
            self._modules[name] = module
            self._manifests[name] = manifest
            self._enabled[name] = active
            self._contexts[name] = None
            self._statuses[name] = ModuleStatus(
                name=name,
                state=ModuleState.INITIALIZING if active else ModuleState.DISABLED,
                detail="in attesa di avvio" if active else "disabilitato",
                available=False,
            )
        self._publish(name)

    def unregister(self, name: str) -> None:
        with self._lock:
            if name not in self._modules:
                raise ModuleError("Modulo sconosciuto: %s" % name)
            self._modules.pop(name)
            self._manifests.pop(name, None)
            self._statuses.pop(name, None)
            self._enabled.pop(name, None)
            self._contexts.pop(name, None)

    def get(self, name: str) -> AmyModule:
        with self._lock:
            module = self._modules.get(name)
        if module is None:
            raise ModuleError("Modulo sconosciuto: %s" % name)
        return module

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._modules)

    def enabled(self, name: str) -> bool:
        with self._lock:
            return bool(self._enabled.get(name, False))

    # ---------------------------------------------------------- ciclo di vita
    def start(self, name: str, context: ModuleContext) -> ModuleStatus:
        with self._lock:
            module = self._modules.get(name)
            if module is None:
                raise ModuleError("Modulo sconosciuto: %s" % name)
            if not self._enabled.get(name, False):
                raise ModuleError("Modulo disabilitato: %s" % name)
            current = self._statuses.get(name)
            if current is not None and current.state in {
                ModuleState.READY,
                ModuleState.BUSY,
                ModuleState.DEGRADED,
            }:
                return current
            self._set_status(name, ModuleStatus(name, ModuleState.INITIALIZING, "avvio"))
        try:
            module.start(context)
        except Exception as exc:  # noqa: BLE001 - un modulo rotto non ferma gli altri
            self._set_status(name, ModuleStatus.error(name, str(exc)))
            _log.warning("Avvio del modulo %s non riuscito", name, exc_info=True)
            raise ModuleError("Avvio del modulo %s non riuscito." % name, detail=str(exc)) from exc
        with self._lock:
            self._contexts[name] = context
        try:
            reported = module.status()
        except Exception as exc:  # noqa: BLE001
            reported = ModuleStatus.error(name, "status() non riuscito: %s" % exc)
        if not isinstance(reported, ModuleStatus):
            reported = ModuleStatus.ready(name)
        self._set_status(name, reported)
        return reported

    def start_all(self, context: ModuleContext) -> Dict[str, ModuleStatus]:
        result: Dict[str, ModuleStatus] = {}
        for name in self.names():
            if not self.enabled(name):
                continue
            try:
                result[name] = self.start(name, context)
            except ModuleError as exc:
                result[name] = self.status_of(name) or ModuleStatus.error(name, str(exc))
        return result

    def stop(self, name: str) -> ModuleStatus:
        with self._lock:
            module = self._modules.get(name)
            if module is None:
                raise ModuleError("Modulo sconosciuto: %s" % name)
        try:
            module.stop()
        except Exception:  # noqa: BLE001 - lo stop non deve impedire gli altri
            _log.warning("Arresto del modulo %s non riuscito", name, exc_info=True)
        with self._lock:
            self._contexts[name] = None
        status = ModuleStatus.disabled(name)
        self._set_status(name, status)
        return status

    def stop_all(self) -> None:
        for name in self.names():
            try:
                self.stop(name)
            except ModuleError:
                continue

    def enable(self, name: str, context: Optional[ModuleContext] = None) -> ModuleStatus:
        with self._lock:
            if name not in self._modules:
                raise ModuleError("Modulo sconosciuto: %s" % name)
            self._enabled[name] = True
            self._set_status(name, ModuleStatus(name, ModuleState.INITIALIZING, "abilitato"))
        if context is not None:
            return self.start(name, context)
        return self.status_of(name) or ModuleStatus(name, ModuleState.INITIALIZING, "abilitato")

    def disable(self, name: str) -> ModuleStatus:
        with self._lock:
            if name not in self._modules:
                raise ModuleError("Modulo sconosciuto: %s" % name)
            self._enabled[name] = False
        return self.stop(name)

    # ---------------------------------------------------------------- stato
    def status_of(self, name: str) -> Optional[ModuleStatus]:
        with self._lock:
            status = self._statuses.get(name)
            return status

    def refresh(self, name: str) -> ModuleStatus:
        module = self.get(name)
        try:
            status = module.status()
        except Exception as exc:  # noqa: BLE001
            status = ModuleStatus.error(name, "status() non riuscito: %s" % exc)
        if not isinstance(status, ModuleStatus):
            status = ModuleStatus.error(name, "status() ha restituito un valore non valido")
        self._set_status(name, status)
        return status

    def statuses(self) -> List[Dict[str, Any]]:
        with self._lock:
            names = sorted(self._modules)
        result = []
        for name in names:
            with self._lock:
                manifest = self._manifests[name]
                status = self._statuses[name]
                enabled = self._enabled[name]
            if enabled and status.state in {
                ModuleState.READY,
                ModuleState.BUSY,
                ModuleState.DEGRADED,
            }:
                status = self.refresh(name)
            with self._lock:
                status = self._statuses[name]
                enabled = self._enabled[name]
            result.append(
                {
                    "manifest": manifest.to_dict(),
                    "status": status.to_dict(),
                    "enabled": bool(enabled),
                }
            )
        return result

    def snapshot(self) -> Dict[str, Any]:
        return {"modules": self.statuses()}

    # ------------------------------------------------------------- strumenti
    def tools(self) -> List[Any]:
        """Strumenti dei moduli abilitati e pronti; nessun duplicato."""
        result: List[Any] = []
        seen: Dict[str, str] = {}
        for name in self.names():
            if not self.enabled(name):
                continue
            status = self.status_of(name)
            if status is None or status.state not in {
                ModuleState.READY,
                ModuleState.BUSY,
                ModuleState.DEGRADED,
            }:
                continue
            module = self.get(name)
            try:
                tools = list(module.tools())
            except Exception:  # noqa: BLE001 - un modulo rotto non blocca il catalogo
                _log.warning("Strumenti del modulo %s non disponibili", name, exc_info=True)
                continue
            for tool in tools:
                spec = getattr(tool, "spec", None)
                tool_name = getattr(spec, "name", "") if spec is not None else ""
                if not tool_name:
                    raise ModuleError("Il modulo %s espone uno strumento senza nome." % name)
                if tool_name in seen:
                    raise ModuleError(
                        "Strumento duplicato: %s (moduli %s e %s)"
                        % (tool_name, seen[tool_name], name)
                    )
                seen[tool_name] = name
                result.append(tool)
        return result

    # ---------------------------------------------------------------- eventi
    def _set_status(self, name: str, status: ModuleStatus) -> None:
        with self._lock:
            self._statuses[name] = status
        self._publish(name)

    def _publish(self, name: str) -> None:
        if self.events is None:
            return
        with self._lock:
            status = self._statuses.get(name)
        if status is None:
            return
        try:
            self.events.publish(
                "module.status",
                {"name": name, "state": status.state.value, "detail": status.detail},
            )
        except Exception:  # noqa: BLE001 - il bus non deve fermare il registro
            _log.warning("Evento di stato del modulo %s non pubblicato", name, exc_info=True)
