"""Policy di autorizzazione e protezione dei percorsi.

La policy è indipendente dal modello linguistico: il LLM può *proporre*
un'azione, ma solo questa classe decide se è ammessa e se serve conferma.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.errors import PermissionDeniedError
from .risk import RiskLevel


@dataclass
class ToolDecision:
    risk: RiskLevel
    requires_confirmation: bool
    reason: str
    consequences: str = ""
    undo: str = ""
    auto_approved: bool = False


@dataclass
class ConfirmationRequest:
    """Richiesta mostrata all'utente prima di un'azione B o C."""

    pending_id: str
    tool: str
    args: Dict[str, Any]
    risk: RiskLevel
    reason: str
    consequences: str
    undo: str
    session_id: str = ""
    created_at: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pending_id": self.pending_id,
            "tool": self.tool,
            "args": self.args,
            "risk": self.risk.value,
            "risk_label": self.risk.label,
            "reason": self.reason,
            "consequences": self.consequences,
            "undo": self.undo,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "extra": self.extra,
        }


SENSITIVE_DIR_NAMES = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    "keychains",
    "cookies",
}

SENSITIVE_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "known_hosts",
    "secrets.json",
    "credentials",
    "credentials.json",
    "*.keychain",
    "*.keychain-db",
    "login.keychain*",
]


class PathGuard:
    """Confina le operazioni su file nelle radici autorizzate."""

    def __init__(self, roots: List[Path], *, max_file_bytes: int = 1_048_576) -> None:
        self.roots = [root.expanduser().resolve() for root in roots]
        self.max_file_bytes = max_file_bytes

    def _sensitive(self, path: Path) -> bool:
        lowered = [part.lower() for part in path.parts]
        if any(part in SENSITIVE_DIR_NAMES for part in lowered):
            return True
        if path.name.startswith("."):
            return True
        return any(fnmatch.fnmatch(path.name.lower(), pattern.lower()) for pattern in SENSITIVE_FILE_PATTERNS)

    def resolve(self, raw: str, *, must_exist: bool = False) -> Path:
        if not isinstance(raw, str) or not raw.strip():
            raise PermissionDeniedError("Percorso mancante o non valido.")
        candidate = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if self._sensitive(resolved):
            raise PermissionDeniedError(
                "Accesso negato a un file o una cartella sensibile.",
                detail=str(resolved),
            )
        if not any(self._is_within(resolved, root) for root in self.roots):
            raise PermissionDeniedError(
                "Il percorso è fuori dalle cartelle autorizzate.",
                detail="%s — radici ammesse: %s" % (resolved, ", ".join(str(r) for r in self.roots)),
            )
        if must_exist and not resolved.exists():
            raise PermissionDeniedError("Il percorso non esiste.", detail=str(resolved))
        return resolved

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def check_size(self, size: int) -> None:
        if size > self.max_file_bytes:
            raise PermissionDeniedError(
                "Il file supera il limite configurato.",
                detail="%d byte > %d byte" % (size, self.max_file_bytes),
            )


class PolicyEngine:
    """Valuta rischio e conferma per ogni strumento."""

    def __init__(
        self,
        *,
        auto_approve_levels: Optional[List[str]] = None,
        auto_approve_tools: Optional[List[str]] = None,
    ) -> None:
        self.auto_approve_levels = {str(level).upper() for level in (auto_approve_levels or ["A"])}
        self.auto_approve_tools = set(auto_approve_tools or [])

    def evaluate(self, tool_name: str, risk: RiskLevel, *, reason: str, consequences: str = "", undo: str = "") -> ToolDecision:
        # Il livello C non è mai automatico, nemmeno se inserito per errore
        # in auto_approve_levels: la conferma esplicita è un requisito di sicurezza.
        if risk == RiskLevel.C:
            return ToolDecision(
                risk=risk,
                requires_confirmation=True,
                reason=reason,
                consequences=consequences,
                undo=undo,
            )
        auto_level = risk.value in self.auto_approve_levels
        auto_tool = tool_name in self.auto_approve_tools
        if risk == RiskLevel.A and auto_level:
            return ToolDecision(
                risk=risk,
                requires_confirmation=False,
                reason=reason,
                consequences=consequences,
                undo=undo,
                auto_approved=True,
            )
        if risk == RiskLevel.B and auto_tool:
            return ToolDecision(
                risk=risk,
                requires_confirmation=False,
                reason=reason,
                consequences=consequences,
                undo=undo,
                auto_approved=True,
            )
        return ToolDecision(
            risk=risk,
            requires_confirmation=True,
            reason=reason,
            consequences=consequences,
            undo=undo,
        )
