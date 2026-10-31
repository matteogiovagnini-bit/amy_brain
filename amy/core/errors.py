"""Errori applicativi di Amy.

Ogni errore espone un messaggio in italiano pensato per l'utente e un codice
stabile utile ai test e ai log. I dettagli tecnici non devono mai contenere
segreti: la redazione avviene nel logger e nell'audit.
"""

from __future__ import annotations


class AmyError(Exception):
    """Errore base con codice stabile e messaggio utente."""

    code = "amy_error"

    def __init__(self, message: str, *, detail: str = "", code: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code:
            self.code = code

    def to_dict(self) -> dict:
        data = {"code": self.code, "message": self.message}
        if self.detail:
            data["detail"] = self.detail
        return data


class ConfigError(AmyError):
    code = "config_error"


class AIError(AmyError):
    code = "ai_error"


class AITimeoutError(AIError):
    code = "ai_timeout"


class AIUnavailableError(AIError):
    code = "ai_unavailable"


class ToolError(AmyError):
    code = "tool_error"


class ToolValidationError(ToolError):
    code = "tool_validation"


class PermissionDeniedError(ToolError):
    code = "permission_denied"


class ConfirmationRequired(AmyError):
    code = "confirmation_required"

    def __init__(self, message: str, *, pending_id: str = "") -> None:
        super().__init__(message)
        self.pending_id = pending_id


class RobotError(AmyError):
    code = "robot_error"


class RobotProtocolError(RobotError):
    code = "robot_protocol"


class RobotSafetyError(RobotError):
    code = "robot_safety"


class VoiceError(AmyError):
    code = "voice_error"
