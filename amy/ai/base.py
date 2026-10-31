"""Interfaccia comune dei provider linguistici."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class AIProvider:
    name = "base"
    model = ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:  # pragma: no cover - interfaccia
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        return {"provider": self.name, "model": self.model, "available": False}


def normalize_messages(messages: List[Any]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for message in messages:
        if isinstance(message, ChatMessage):
            normalized.append(message.to_dict())
        elif isinstance(message, dict) and "role" in message and "content" in message:
            normalized.append({"role": str(message["role"]), "content": str(message["content"])})
        else:
            raise ValueError("Messaggio non valido per il provider IA.")
    return normalized
