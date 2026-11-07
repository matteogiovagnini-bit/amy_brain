"""Servizio del Personal Manager: agenda unica per dashboard e assistente."""

from __future__ import annotations

from typing import Any, Callable, Dict

from ...tools.calendar_tools import collect_upcoming


class PersonalManager:
    """Agenda e futuro punto di accesso unico per calendario, task e note."""

    def __init__(self, registry: Any, context_factory: Callable[[], Any]) -> None:
        self.registry = registry
        self._context_factory = context_factory

    def agenda(self, *, days: int = 7, limit: int = 8) -> Dict[str, Any]:
        return collect_upcoming(
            self.registry,
            self._context_factory(),
            days=max(1, min(int(days), 14)),
            limit=max(1, min(int(limit), 20)),
        )
