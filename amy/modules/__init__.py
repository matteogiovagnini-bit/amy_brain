"""Adapter dei moduli di Amy.

La Fase 2 avvolge i componenti esistenti in moduli senza spostare file e senza
cambiare il catalogo degli strumenti. `builtin.py` resta l'aggregatore di
compatibilità; il registro dei moduli è disponibile per la Fase 3.
"""

from .registry import build_module_registry

__all__ = ["build_module_registry"]
