"""Autorizzazioni per modulo e capacità.

La policy A/B/C resta l'ultima parola sulla conferma. Questo broker aggiunge un
controllo **prima** della policy:

1. lo strumento appartiene a un modulo registrato;
2. il modulo è abilitato;
3. la capacità richiesta non è stata revocata.

Un modulo o una capacità revocata non esegue nulla. Il livello C non viene mai
trasformato in automatico: il broker non decide le conferme, le lascia alla
policy esistente.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from ..core.errors import AmyError
from ..core.modules import ModuleRegistry
from ..shared.module import ModuleManifest


class AuthorizationError(AmyError):
    code = "authorization_error"


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    module: str = ""
    capability: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "module": self.module,
            "capability": self.capability,
            "reason": self.reason,
        }


def capability_for_tool(tool_name: str) -> str:
    """Mappa uno strumento sulla capacità dichiarata dal suo modulo."""
    name = str(tool_name or "")
    if name.startswith("apps."):
        return "mac.app"
    if name.startswith("files."):
        return "mac.file"
    if name.startswith("shell."):
        return "mac.shell.read"
    if name.startswith("web."):
        return "mac.web"
    if name.startswith("system.") or name.startswith("time."):
        return "mac.system"
    if name.startswith("calendar."):
        return "personal.calendar"
    if name.startswith("reminders."):
        return "personal.reminders"
    if name.startswith("mail."):
        return "personal.mail"
    if name in {"memory.list", "memory.search", "memory.categories"}:
        return "memory.read"
    if name == "memory.forget":
        return "memory.delete"
    if name.startswith("memory."):
        return "memory.write"
    if name.startswith("opencode."):
        return "dev.execute"
    if name == "app.restart":
        return "dev.restart"
    if name.startswith("screen."):
        return "vision.screen"
    if name.startswith("voice."):
        return "voice.tts"
    if name in {"robot.status", "robot.ping"}:
        return "robot.read"
    if name == "robot.move" or name == "robot.mode":
        return "robot.move"
    if name in {"robot.estop", "robot.stop", "robot.reset_estop"}:
        return "robot.estop"
    if name.startswith("home."):
        return "home.set" if name in {"home.set", "home.scene"} else "home.read"
    return ""


class AuthorizationBroker:
    """Controlla modulo, capacità e revoche prima dell'esecuzione."""

    def __init__(self, modules: ModuleRegistry) -> None:
        self.modules = modules
        self._revoked: Set[str] = set()
        self._lock = threading.RLock()

    # ------------------------------------------------------------- controlli
    def check(self, tool_name: str, risk: Any = None) -> AuthorizationDecision:
        manifest = self.modules.owner_of(tool_name)
        if manifest is None:
            return AuthorizationDecision(
                False,
                reason="Strumento non associato a un modulo.",
            )
        if not self.modules.enabled(manifest.name):
            return AuthorizationDecision(
                False,
                module=manifest.name,
                reason="Il modulo %s è disabilitato." % manifest.name,
            )
        capability = capability_for_tool(tool_name)
        if not capability:
            return AuthorizationDecision(
                False,
                module=manifest.name,
                reason="Capacità sconosciuta per lo strumento %s." % tool_name,
            )
        if capability not in set(manifest.capabilities):
            return AuthorizationDecision(
                False,
                module=manifest.name,
                capability=capability,
                reason="Il modulo %s non dichiara la capacità %s."
                % (manifest.name, capability),
            )
        with self._lock:
            revoked = capability in self._revoked
        if revoked:
            return AuthorizationDecision(
                False,
                module=manifest.name,
                capability=capability,
                reason="Capacità revocata: %s." % capability,
            )
        return AuthorizationDecision(True, module=manifest.name, capability=capability)

    # --------------------------------------------------------------- revoche
    def capabilities(self) -> List[Dict[str, Any]]:
        result = []
        seen = set()
        for name in self.modules.names():
            manifest = self.modules.manifest_of(name)
            if manifest is None:
                continue
            for capability in manifest.capabilities:
                if capability in seen:
                    continue
                seen.add(capability)
                with self._lock:
                    revoked = capability in self._revoked
                result.append(
                    {
                        "capability": capability,
                        "module": manifest.name,
                        "title": manifest.title,
                        "revoked": revoked,
                    }
                )
        return sorted(result, key=lambda item: (item["module"], item["capability"]))

    def revoke(self, capability: str) -> Dict[str, Any]:
        value = str(capability or "").strip()
        if not value:
            raise AuthorizationError("Capacità mancante.")
        known = {item["capability"] for item in self.capabilities()}
        if value not in known:
            raise AuthorizationError("Capacità sconosciuta: %s" % value)
        with self._lock:
            self._revoked.add(value)
        return self.snapshot()

    def restore(self, capability: str) -> Dict[str, Any]:
        value = str(capability or "").strip()
        with self._lock:
            self._revoked.discard(value)
        return self.snapshot()

    def is_revoked(self, capability: str) -> bool:
        with self._lock:
            return capability in self._revoked

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            revoked = sorted(self._revoked)
        return {
            "revoked": revoked,
            "capabilities": self.capabilities(),
        }

    def describe(self, tool_name: str) -> Dict[str, str]:
        manifest = self.modules.owner_of(tool_name)
        return {
            "module": manifest.name if manifest else "",
            "capability": capability_for_tool(tool_name),
        }
