"""Adapter del modulo Telegram."""

from __future__ import annotations

from typing import Any, Optional

from ...shared.module import ModuleManifest, ModuleState, ModuleStatus
from ..base import BaseAdapter


class TelegramAdapter(BaseAdapter):
    def __init__(self, service: Optional[Any] = None) -> None:
        super().__init__(
            ModuleManifest(
                name="telegram",
                title="Telegram",
                version="0.1.0",
                description="Chat e note vocali da smartphone tramite Bot API.",
                default_enabled=False,
                capabilities=("telegram.chat", "telegram.voice"),
                requires=("telegram_token",),
                tools=(),
                optional=True,
            ),
            [],
        )
        self.service = service

    def status(self) -> ModuleStatus:
        base = super().status()
        if self.service is None:
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "servizio Telegram non collegato"
            return base
        try:
            data = self.service.status()
        except Exception as exc:  # noqa: BLE001 - lo stato non deve rompere il Core
            base.state = ModuleState.ERROR
            base.available = False
            base.detail = "stato Telegram non disponibile: %s" % exc
            return base
        state = str(data.get("state", "disabled"))
        if not data.get("enabled"):
            base.state = ModuleState.DISABLED
            base.available = False
            base.detail = "disattivato: configura telegram.enabled"
        elif data.get("error"):
            base.state = ModuleState.ERROR
            base.available = False
            base.detail = str(data.get("error"))[:200]
        elif data.get("connected"):
            base.state = ModuleState.READY
            base.available = True
            base.detail = "collegato come @%s" % data.get("username", "")
        elif state in {"starting", "running"}:
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "connessione a Telegram in corso"
        else:
            base.state = ModuleState.DEGRADED
            base.available = False
            base.detail = "in attesa di token e allowlist"
        base.data = {
            "username": data.get("username", ""),
            "allowed_users": data.get("allowed_users", 0),
            "voice_replies": bool(data.get("voice_replies")),
            "running": bool(data.get("running")),
        }
        return base
