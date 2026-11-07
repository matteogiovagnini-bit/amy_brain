"""Modulo Developer: analisi del progetto in sola lettura.

Gli strumenti qui esposti non modificano file: ``dev.status``, ``dev.diff`` e
``dev.analyze`` sono livello A. ``dev.test`` avvia la suite del progetto ed è
livello B. Le modifiche restano affidate a OpenCode, che è livello C.
"""

from .service import DevError, analyze, diff, run_tests, status

__all__ = ["DevError", "analyze", "diff", "run_tests", "status"]
