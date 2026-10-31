"""Livelli di rischio delle azioni, come definiti dal progetto Amy."""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Livello A = ordinario, B = impatto significativo, C = sensibile/irreversibile."""

    A = "A"
    B = "B"
    C = "C"

    @property
    def label(self) -> str:
        return {
            RiskLevel.A: "ordinaria",
            RiskLevel.B: "impatto significativo",
            RiskLevel.C: "sensibile o irreversibile",
        }[self]

    def __str__(self) -> str:  # pragma: no cover - banale
        return self.value
